from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

from . import PROJECT_ROOT

logger = logging.getLogger("mcvs.models")

MODELS_DIR = PROJECT_ROOT / "data" / "models"

FACE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)
POSE_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)


def _download(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    logger.info("baixando modelo %s", url)
    tmp = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
        out.write(resp.read())
    tmp.replace(target)
    logger.info("modelo salvo em %s", target)
    return target


def ensure_face_model() -> Path:
    target = MODELS_DIR / "face_landmarker.task"
    if not target.exists():
        _download(FACE_LANDMARKER_URL, target)
    return target


def ensure_pose_model() -> Path:
    target = MODELS_DIR / "pose_landmarker_lite.task"
    if not target.exists():
        _download(POSE_LANDMARKER_URL, target)
    return target
