from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from .config import (
    FACE_MESH_LEFT_EYE,
    FACE_MESH_MOUTH,
    FACE_MESH_OUTER_LIPS,
    FACE_MESH_POSE_LANDMARKS,
    FACE_MESH_RIGHT_EYE,
)
from .model_loader import ensure_face_model

logger = logging.getLogger("mcvs.face")

Landmarks = List[Tuple[float, float]]


@dataclass
class FaceMetrics:
    detected: bool
    ear_left: float = 0.0
    ear_right: float = 0.0
    ear_mean: float = 0.0
    mar: float = 0.0
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    landmarks: Optional[Landmarks] = None
    eye_polylines: Optional[Tuple[np.ndarray, np.ndarray]] = None
    mouth_polyline: Optional[np.ndarray] = None


HEAD_MODEL_POINTS = np.array(
    [
        (0.0, 0.0, 0.0),
        (0.0, -63.6, -12.5),
        (-43.3, 32.7, -26.0),
        (43.3, 32.7, -26.0),
        (-28.9, -28.9, -24.1),
        (28.9, -28.9, -24.1),
    ],
    dtype=np.float64,
)


def _eye_aspect_ratio(points: Sequence[Tuple[float, float]]) -> float:
    p1, p2, p3, p4, p5, p6 = points
    vertical_a = math.dist(p2, p6)
    vertical_b = math.dist(p3, p5)
    horizontal = math.dist(p1, p4)
    if horizontal < 1e-6:
        return 0.0
    return (vertical_a + vertical_b) / (2.0 * horizontal)


def _mouth_aspect_ratio(points: Sequence[Tuple[float, float]]) -> float:
    if len(points) < 10:
        return 0.0
    p1 = points[0]
    p2 = points[1]
    p3 = points[2]
    p4 = points[3]
    p5 = points[4]
    p6 = points[5]
    p7 = points[6]
    p8 = points[7]
    vertical_a = math.dist(p2, p8)
    vertical_b = math.dist(p3, p7)
    vertical_c = math.dist(p5, p6)
    horizontal = math.dist(p1, p4)
    if horizontal < 1e-6:
        return 0.0
    return (vertical_a + vertical_b + vertical_c) / (3.0 * horizontal)


def _select(landmarks: Landmarks, indices: Sequence[int]) -> List[Tuple[float, float]]:
    return [landmarks[i] for i in indices]


def _solve_head_pose(
    landmarks: Landmarks, frame_shape: Tuple[int, int]
) -> Tuple[float, float, float]:
    h, w = frame_shape
    image_points = np.array(
        [landmarks[idx] for idx in FACE_MESH_POSE_LANDMARKS],
        dtype=np.float64,
    )

    focal_length = float(w)
    center = (w / 2.0, h / 2.0)
    camera_matrix = np.array(
        [
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1.0],
        ],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    ok, rvec, _tvec = cv2.solvePnP(
        HEAD_MODEL_POINTS,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return 0.0, 0.0, 0.0

    rotation_matrix, _ = cv2.Rodrigues(rvec)
    proj = np.hstack((rotation_matrix, np.zeros((3, 1))))
    _, _, _, _, _, _, euler = cv2.decomposeProjectionMatrix(proj)
    euler_flat = np.asarray(euler).flatten()
    pitch, yaw, roll = float(euler_flat[0]), float(euler_flat[1]), float(euler_flat[2])

    pitch = _wrap_around_zero(pitch)
    yaw = _wrap_around_zero(yaw)
    roll = _wrap_around_zero(roll)
    return yaw, pitch, roll


def _wrap_around_zero(angle: float) -> float:
    while angle > 180.0:
        angle -= 360.0
    while angle < -180.0:
        angle += 360.0
    if angle > 90.0:
        angle = 180.0 - angle
    elif angle < -90.0:
        angle = -180.0 - angle
    return angle


class FaceMetricsExtractor:
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

        model_path = ensure_face_model()
        base_opts = mp_python.BaseOptions(model_asset_path=str(model_path))
        options = mp_vision.FaceLandmarkerOptions(
            base_options=base_opts,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
        self._mp_image_cls = mp.Image
        self._mp_image_format = mp.ImageFormat.SRGB

    def process(self, bgr_frame: np.ndarray) -> FaceMetrics:
        self._ensure_landmarker()
        h, w = bgr_frame.shape[:2]
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        mp_image = self._mp_image_cls(image_format=self._mp_image_format, data=rgb)

        self._ts_ms += 1
        result = self._landmarker.detect_for_video(mp_image, self._ts_ms)

        if not result.face_landmarks:
            return FaceMetrics(detected=False)

        landmarks_proto = result.face_landmarks[0]
        pts: Landmarks = [(lm.x * w, lm.y * h) for lm in landmarks_proto]

        ear_l = _eye_aspect_ratio(_select(pts, FACE_MESH_LEFT_EYE))
        ear_r = _eye_aspect_ratio(_select(pts, FACE_MESH_RIGHT_EYE))
        ear_mean = (ear_l + ear_r) / 2.0
        mar = _mouth_aspect_ratio(_select(pts, FACE_MESH_MOUTH))

        try:
            yaw, pitch, roll = _solve_head_pose(pts, (h, w))
        except cv2.error as exc:
            logger.debug("solvePnP falhou: %s", exc)
            yaw, pitch, roll = 0.0, 0.0, 0.0

        left_eye_pts = np.array(_select(pts, FACE_MESH_LEFT_EYE), dtype=np.int32)
        right_eye_pts = np.array(_select(pts, FACE_MESH_RIGHT_EYE), dtype=np.int32)
        outer_lips_indices = (61, 39, 0, 269, 291, 405, 17, 181)
        mouth_pts = np.array(
            [pts[i] for i in outer_lips_indices],
            dtype=np.int32,
        )

        return FaceMetrics(
            detected=True,
            ear_left=ear_l,
            ear_right=ear_r,
            ear_mean=ear_mean,
            mar=mar,
            yaw_deg=yaw,
            pitch_deg=pitch,
            roll_deg=roll,
            landmarks=pts,
            eye_polylines=(left_eye_pts, right_eye_pts),
            mouth_polyline=mouth_pts,
        )

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None
