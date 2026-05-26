from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Sequence, Tuple

import cv2
import numpy as np

from .alert_engine import EngineState, Severity
from .body_metrics import BodyMetrics
from .face_metrics import FaceMetrics
from .presence import PresenceState


COLOR_OK = (110, 220, 110)
COLOR_WARN = (60, 200, 230)
COLOR_CRIT = (90, 90, 240)
COLOR_INFO = (220, 180, 80)
COLOR_PANEL_BG = (16, 16, 16)
COLOR_PANEL_BORDER = (90, 90, 90)
COLOR_TEXT = (230, 230, 230)
COLOR_DIM = (155, 155, 155)
COLOR_DOT_OK = (110, 220, 110)


SEVERITY_COLOR = {
    Severity.OK: COLOR_OK,
    Severity.VIG1: COLOR_CRIT,
    Severity.VIG2: COLOR_WARN,
    Severity.VIG3: COLOR_INFO,
}

SEVERITY_LABEL = {
    Severity.OK: "OK",
    Severity.VIG1: "CRITICO",
    Severity.VIG2: "ATENCAO",
    Severity.VIG3: "INFORMATIVO",
}


FACE_DOT_INDICES: Tuple[int, ...] = (
    10,
    151,
    9,
    1,
    4,
    33,
    133,
    263,
    362,
    159,
    145,
    386,
    374,
    61,
    291,
    17,
    199,
)


@dataclass
class HudPayload:
    severity: Severity
    face: FaceMetrics
    body: BodyMetrics
    presence: PresenceState
    blink_rate: float
    fps: float
    session_start: datetime
    counts: Dict[Severity, int]
    ear_min_recent: Optional[float] = None
    mar_max_recent: Optional[float] = None
    debug_visible: bool = False


def _text(
    image: np.ndarray,
    text: str,
    org: Tuple[int, int],
    scale: float = 0.45,
    color: Tuple[int, int, int] = COLOR_TEXT,
    thickness: int = 1,
) -> None:
    cv2.putText(image, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def _panel(image: np.ndarray, x: int, y: int, w: int, h: int, alpha: float = 0.50) -> None:
    overlay = image.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), COLOR_PANEL_BG, -1)
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
    cv2.rectangle(image, (x, y), (x + w, y + h), COLOR_PANEL_BORDER, 1)


def draw_face_dots(image: np.ndarray, face: FaceMetrics, severity: Severity) -> None:
    if not face.detected or face.landmarks is None:
        return
    color = SEVERITY_COLOR.get(severity, COLOR_DOT_OK)
    if face.eye_polylines is not None:
        left, right = face.eye_polylines
        cv2.polylines(image, [left], isClosed=True, color=color, thickness=1, lineType=cv2.LINE_AA)
        cv2.polylines(image, [right], isClosed=True, color=color, thickness=1, lineType=cv2.LINE_AA)
    if face.mouth_polyline is not None:
        cv2.polylines(image, [face.mouth_polyline], isClosed=True, color=color, thickness=1, lineType=cv2.LINE_AA)
    for idx in FACE_DOT_INDICES:
        if idx >= len(face.landmarks):
            continue
        x, y = face.landmarks[idx]
        cv2.circle(image, (int(x), int(y)), 2, color, -1, cv2.LINE_AA)


def draw_body_dots(image: np.ndarray, body: BodyMetrics, severity: Severity) -> None:
    if not body.detected:
        return
    color = SEVERITY_COLOR.get(severity, COLOR_DOT_OK)
    if body.shoulder_left_xy and body.shoulder_right_xy:
        left = tuple(int(v) for v in body.shoulder_left_xy)
        right = tuple(int(v) for v in body.shoulder_right_xy)
        cv2.circle(image, left, 4, color, -1, cv2.LINE_AA)
        cv2.circle(image, right, 4, color, -1, cv2.LINE_AA)


def _status_panel(image: np.ndarray, severity: Severity) -> None:
    color = SEVERITY_COLOR.get(severity, COLOR_OK)
    label = SEVERITY_LABEL.get(severity, "OK")
    _panel(image, 12, 12, 180, 44)
    _text(image, "STATUS", (22, 28), scale=0.4, color=COLOR_DIM)
    _text(image, label, (22, 48), scale=0.7, color=color, thickness=2)


def _session_panel(image: np.ndarray, payload: HudPayload) -> None:
    w = image.shape[1]
    elapsed = datetime.now() - payload.session_start
    secs = int(elapsed.total_seconds())
    timer = f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
    panel_w = 170
    x = w - panel_w - 12
    _panel(image, x, 12, panel_w, 44)
    _text(image, "SESSAO", (x + 10, 28), scale=0.4, color=COLOR_DIM)
    _text(image, timer, (x + 10, 48), scale=0.55, color=COLOR_TEXT, thickness=2)
    _text(image, f"{payload.fps:4.1f} FPS", (x + 100, 48), scale=0.45, color=COLOR_DIM)


def _counters_panel(image: np.ndarray, payload: HudPayload) -> None:
    h = image.shape[0]
    w = image.shape[1]
    panel_w = 180
    panel_h = 50
    x = w - panel_w - 12
    y = h - panel_h - 12
    _panel(image, x, y, panel_w, panel_h)
    _text(image, "EVENTOS", (x + 10, y + 16), scale=0.4, color=COLOR_DIM)
    c = payload.counts
    _text(image, f"V1 {c.get(Severity.VIG1, 0):2d}", (x + 10, y + 38), scale=0.5, color=COLOR_CRIT)
    _text(image, f"V2 {c.get(Severity.VIG2, 0):2d}", (x + 65, y + 38), scale=0.5, color=COLOR_WARN)
    _text(image, f"V3 {c.get(Severity.VIG3, 0):2d}", (x + 120, y + 38), scale=0.5, color=COLOR_INFO)


def _presence_pill(image: np.ndarray, payload: HudPayload) -> None:
    h = image.shape[0]
    x, y = 12, h - 32
    label = "PRESENTE" if payload.presence.face_present else f"AUSENTE {payload.presence.absence_seconds:.0f}s"
    color = COLOR_OK if payload.presence.face_present else COLOR_CRIT
    _panel(image, x, y, 140, 22, alpha=0.5)
    _text(image, label, (x + 10, y + 16), scale=0.45, color=color)


def _debug_panel(image: np.ndarray, payload: HudPayload) -> None:
    h = image.shape[0]
    rows = []
    if payload.face.detected:
        rows.append(f"EAR    {payload.face.ear_mean:5.3f}")
    else:
        rows.append("EAR    ----")
    if payload.ear_min_recent is not None:
        rows.append(f"EARmin {payload.ear_min_recent:5.3f}")
    else:
        rows.append("EARmin ----")
    if payload.face.detected:
        rows.append(f"MAR    {payload.face.mar:5.3f}")
    else:
        rows.append("MAR    ----")
    if payload.mar_max_recent is not None:
        rows.append(f"MARmax {payload.mar_max_recent:5.3f}")
    else:
        rows.append("MARmax ----")
    if payload.face.detected:
        rows.append(f"yaw  {payload.face.yaw_deg:5.1f}")
        rows.append(f"pitch{payload.face.pitch_deg:5.1f}")
    else:
        rows.append("yaw  ----")
        rows.append("pitch----")
    rows.append(f"blink/min {payload.blink_rate:4.1f}")
    if payload.body.detected:
        rows.append(f"tilt  {payload.body.shoulder_tilt_deg:5.1f}")
        rows.append(f"bvis  {payload.body.visibility_score:4.2f}")
    else:
        rows.append("tilt  ----")
        rows.append("bvis  ----")

    panel_w = 170
    line_h = 16
    panel_h = 14 + line_h * len(rows) + 6
    y = h - panel_h - 44
    x = 12
    _panel(image, x, y, panel_w, panel_h)
    _text(image, "DEBUG", (x + 10, y + 16), scale=0.4, color=COLOR_DIM)
    for i, row in enumerate(rows):
        _text(image, row, (x + 10, y + 32 + i * line_h), scale=0.42, color=COLOR_TEXT)


def _frame_corners(image: np.ndarray, severity: Severity) -> None:
    h, w = image.shape[:2]
    color = SEVERITY_COLOR.get(severity, COLOR_OK)
    length = 24
    thickness = 2
    pad = 6
    cv2.line(image, (pad, pad), (pad + length, pad), color, thickness, cv2.LINE_AA)
    cv2.line(image, (pad, pad), (pad, pad + length), color, thickness, cv2.LINE_AA)
    cv2.line(image, (w - pad - length, pad), (w - pad, pad), color, thickness, cv2.LINE_AA)
    cv2.line(image, (w - pad, pad), (w - pad, pad + length), color, thickness, cv2.LINE_AA)
    cv2.line(image, (pad, h - pad - length), (pad, h - pad), color, thickness, cv2.LINE_AA)
    cv2.line(image, (pad, h - pad), (pad + length, h - pad), color, thickness, cv2.LINE_AA)
    cv2.line(image, (w - pad - length, h - pad), (w - pad, h - pad), color, thickness, cv2.LINE_AA)
    cv2.line(image, (w - pad, h - pad - length), (w - pad, h - pad), color, thickness, cv2.LINE_AA)


def render_hud(image: np.ndarray, payload: HudPayload) -> np.ndarray:
    _frame_corners(image, payload.severity)
    draw_face_dots(image, payload.face, payload.severity)
    draw_body_dots(image, payload.body, payload.severity)

    _status_panel(image, payload.severity)
    _session_panel(image, payload)
    _counters_panel(image, payload)
    _presence_pill(image, payload)

    if payload.debug_visible:
        _debug_panel(image, payload)
    return image
