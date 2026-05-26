from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from . import PROJECT_ROOT

CALIBRATION_PATH = PROJECT_ROOT / "data" / "calibration.json"


@dataclass
class CaptureConfig:
    width: int = 640
    height: int = 480
    fps_target: int = 30
    camera_index: int = 0
    fallback_indices: tuple = (0, 1, 2)


@dataclass
class FaceThresholds:
    ear_microsleep: float = 0.15
    ear_microsleep_duration_s: float = 1.5
    ear_blink_threshold: float = 0.21
    ear_blink_min_frames: int = 2

    mar_yawn: float = 0.60
    mar_yawn_duration_s: float = 4.0

    yaw_distraction_deg: float = 30.0
    pitch_distraction_deg: float = 30.0
    distraction_duration_s: float = 5.0

    blink_rate_min: float = 8.0
    blink_rate_max: float = 25.0
    blink_anomaly_window_s: float = 120.0


@dataclass
class BodyThresholds:
    shoulder_tilt_deg: float = 8.0
    forward_head_ratio: float = 0.25
    posture_duration_s: float = 10.0


@dataclass
class PresenceThresholds:
    short_absence_min_s: float = 3.0
    long_absence_min_s: float = 10.0


@dataclass
class HysteresisConfig:
    cooldown_seconds: float = 6.0
    smoothing_window: int = 5


@dataclass
class AppConfig:
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    face: FaceThresholds = field(default_factory=FaceThresholds)
    body: BodyThresholds = field(default_factory=BodyThresholds)
    presence: PresenceThresholds = field(default_factory=PresenceThresholds)
    hysteresis: HysteresisConfig = field(default_factory=HysteresisConfig)
    operator_id: str = "operator_01"

    def to_dict(self) -> dict:
        return {
            "capture": asdict(self.capture),
            "face": asdict(self.face),
            "body": asdict(self.body),
            "presence": asdict(self.presence),
            "hysteresis": asdict(self.hysteresis),
            "operator_id": self.operator_id,
        }


def load_calibration(path: Optional[Path] = None) -> AppConfig:
    target = path or CALIBRATION_PATH
    base = AppConfig()
    if not target.exists():
        return base

    with target.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    face_data = data.get("face", {})
    for key, value in face_data.items():
        if hasattr(base.face, key):
            setattr(base.face, key, value)

    body_data = data.get("body", {})
    for key, value in body_data.items():
        if hasattr(base.body, key):
            setattr(base.body, key, value)

    operator = data.get("operator_id")
    if operator:
        base.operator_id = operator

    return base


def save_calibration(config: AppConfig, path: Optional[Path] = None) -> Path:
    target = path or CALIBRATION_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(config.to_dict(), fh, indent=2)
    return target


FACE_MESH_LEFT_EYE = (33, 160, 158, 133, 153, 144)
FACE_MESH_RIGHT_EYE = (362, 385, 387, 263, 373, 380)
FACE_MESH_MOUTH = (61, 81, 311, 291, 178, 14, 402, 17, 0, 13)
FACE_MESH_OUTER_LIPS = (61, 0, 17, 291, 13, 14)
FACE_MESH_POSE_LANDMARKS = (1, 152, 33, 263, 61, 291)

POSE_LEFT_SHOULDER = 11
POSE_RIGHT_SHOULDER = 12
POSE_LEFT_EAR = 7
POSE_RIGHT_EAR = 8
POSE_NOSE = 0
POSE_LEFT_HIP = 23
POSE_RIGHT_HIP = 24
