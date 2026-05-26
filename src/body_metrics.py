from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from .config import (
    POSE_LEFT_EAR,
    POSE_LEFT_HIP,
    POSE_LEFT_SHOULDER,
    POSE_RIGHT_EAR,
    POSE_RIGHT_HIP,
    POSE_RIGHT_SHOULDER,
)
from .model_loader import ensure_pose_model

logger = logging.getLogger("mcvs.body")


MIN_VISIBILITY = 0.65


@dataclass
class BodyMetrics:
    detected: bool
    shoulder_tilt_deg: float = 0.0
    forward_head_ratio: float = 0.0
    torso_angle_deg: float = 0.0
    visibility_score: float = 0.0
    shoulder_left_xy: Optional[Tuple[float, float]] = None
    shoulder_right_xy: Optional[Tuple[float, float]] = None
    ear_left_xy: Optional[Tuple[float, float]] = None
    ear_right_xy: Optional[Tuple[float, float]] = None
    shoulders_reliable: bool = False
    ears_reliable: bool = False


def _shoulder_tilt(left: Tuple[float, float], right: Tuple[float, float]) -> float:
    dx = abs(right[0] - left[0])
    dy = right[1] - left[1]
    if dx < 1e-6:
        return 90.0
    return math.degrees(math.atan2(dy, dx))


def _forward_head_ratio(
    ear_xy: Tuple[float, float],
    shoulder_xy: Tuple[float, float],
    shoulder_span: float,
) -> float:
    if shoulder_span < 1e-6:
        return 0.0
    horizontal_offset = ear_xy[0] - shoulder_xy[0]
    return abs(horizontal_offset) / shoulder_span


def _torso_angle(shoulders_mid: Tuple[float, float], hips_mid: Tuple[float, float]) -> float:
    dx = shoulders_mid[0] - hips_mid[0]
    dy = shoulders_mid[1] - hips_mid[1]
    if abs(dy) < 1e-6:
        return 90.0
    return math.degrees(math.atan2(dx, -dy))


class BodyMetricsExtractor:
    def __init__(self):
        self._landmarker = None
        self._mp_image_cls = None
        self._mp_image_format = None
        self._ts_ms = 0

    def _ensure_landmarker(self):
        if self._landmarker is not None:
            return
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        model_path = ensure_pose_model()
        base_opts = mp_python.BaseOptions(model_asset_path=str(model_path))
        options = mp_vision.PoseLandmarkerOptions(
            base_options=base_opts,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            output_segmentation_masks=False,
            min_pose_detection_confidence=0.6,
            min_pose_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._mp_image_cls = mp.Image
        self._mp_image_format = mp.ImageFormat.SRGB

    def process(self, bgr_frame: np.ndarray) -> BodyMetrics:
        self._ensure_landmarker()
        h, w = bgr_frame.shape[:2]
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        mp_image = self._mp_image_cls(image_format=self._mp_image_format, data=rgb)

        self._ts_ms += 1
        result = self._landmarker.detect_for_video(mp_image, self._ts_ms)

        if not result.pose_landmarks:
            return BodyMetrics(detected=False)

        lm = result.pose_landmarks[0]

        vis_l_sh = lm[POSE_LEFT_SHOULDER].visibility
        vis_r_sh = lm[POSE_RIGHT_SHOULDER].visibility
        vis_l_ear = lm[POSE_LEFT_EAR].visibility
        vis_r_ear = lm[POSE_RIGHT_EAR].visibility
        vis_l_hip = lm[POSE_LEFT_HIP].visibility
        vis_r_hip = lm[POSE_RIGHT_HIP].visibility

        shoulders_reliable = vis_l_sh >= MIN_VISIBILITY and vis_r_sh >= MIN_VISIBILITY
        ears_reliable = vis_l_ear >= MIN_VISIBILITY and vis_r_ear >= MIN_VISIBILITY
        hips_reliable = vis_l_hip >= MIN_VISIBILITY and vis_r_hip >= MIN_VISIBILITY

        avg_visibility = (vis_l_sh + vis_r_sh + vis_l_ear + vis_r_ear) / 4.0

        left_shoulder = (lm[POSE_LEFT_SHOULDER].x * w, lm[POSE_LEFT_SHOULDER].y * h)
        right_shoulder = (lm[POSE_RIGHT_SHOULDER].x * w, lm[POSE_RIGHT_SHOULDER].y * h)
        left_ear = (lm[POSE_LEFT_EAR].x * w, lm[POSE_LEFT_EAR].y * h)
        right_ear = (lm[POSE_RIGHT_EAR].x * w, lm[POSE_RIGHT_EAR].y * h)

        tilt = 0.0
        fhr = 0.0
        torso = 0.0

        if shoulders_reliable:
            tilt = _shoulder_tilt(left_shoulder, right_shoulder)
            shoulder_span = math.dist(left_shoulder, right_shoulder)
            if ears_reliable and shoulder_span > 1e-6:
                ratio_left = _forward_head_ratio(left_ear, left_shoulder, shoulder_span)
                ratio_right = _forward_head_ratio(right_ear, right_shoulder, shoulder_span)
                fhr = max(ratio_left, ratio_right)

            if hips_reliable:
                left_hip = (lm[POSE_LEFT_HIP].x * w, lm[POSE_LEFT_HIP].y * h)
                right_hip = (lm[POSE_RIGHT_HIP].x * w, lm[POSE_RIGHT_HIP].y * h)
                shoulders_mid = (
                    (left_shoulder[0] + right_shoulder[0]) / 2.0,
                    (left_shoulder[1] + right_shoulder[1]) / 2.0,
                )
                hips_mid = (
                    (left_hip[0] + right_hip[0]) / 2.0,
                    (left_hip[1] + right_hip[1]) / 2.0,
                )
                torso = _torso_angle(shoulders_mid, hips_mid)

        return BodyMetrics(
            detected=shoulders_reliable,
            shoulder_tilt_deg=abs(tilt),
            forward_head_ratio=fhr,
            torso_angle_deg=abs(torso),
            visibility_score=avg_visibility,
            shoulder_left_xy=left_shoulder if shoulders_reliable else None,
            shoulder_right_xy=right_shoulder if shoulders_reliable else None,
            ear_left_xy=left_ear if ears_reliable else None,
            ear_right_xy=right_ear if ears_reliable else None,
            shoulders_reliable=shoulders_reliable,
            ears_reliable=ears_reliable,
        )

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
