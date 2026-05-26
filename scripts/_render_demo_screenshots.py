from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.alert_engine import Severity
from src.body_metrics import BodyMetrics
from src.face_metrics import FaceMetrics
from src.overlay import HudPayload, render_hud
from src.presence import PresenceState


def synthetic_frame(width: int = 1024, height: int = 720) -> np.ndarray:
    img = np.full((height, width, 3), 22, dtype=np.uint8)
    for y in range(0, height, 40):
        cv2.line(img, (0, y), (width, y), (30, 30, 30), 1)
    for x in range(0, width, 40):
        cv2.line(img, (x, 0), (x, height), (30, 30, 30), 1)

    cv2.ellipse(img, (width // 2, height // 2 - 30), (140, 180), 0, 0, 360, (180, 180, 195), -1)
    cv2.circle(img, (width // 2 - 55, height // 2 - 60), 18, (40, 40, 40), -1)
    cv2.circle(img, (width // 2 + 55, height // 2 - 60), 18, (40, 40, 40), -1)
    cv2.ellipse(img, (width // 2, height // 2 + 60), (45, 18), 0, 0, 360, (60, 60, 60), 2)

    cv2.rectangle(img, (width // 2 - 220, height // 2 + 200), (width // 2 + 220, height), (90, 110, 140), -1)
    return img


def _synthetic_landmarks(width: int, height: int) -> list:
    cx, cy = width // 2, height // 2
    pts = [(0.0, 0.0)] * 478
    pts[10] = (cx, cy - 180)
    pts[151] = (cx, cy - 140)
    pts[9] = (cx, cy - 80)
    pts[1] = (cx, cy - 30)
    pts[4] = (cx, cy)
    pts[33] = (cx - 75, cy - 55)
    pts[133] = (cx - 25, cy - 55)
    pts[263] = (cx + 75, cy - 55)
    pts[362] = (cx + 25, cy - 55)
    pts[159] = (cx - 50, cy - 70)
    pts[145] = (cx - 50, cy - 40)
    pts[386] = (cx + 50, cy - 70)
    pts[374] = (cx + 50, cy - 40)
    pts[61] = (cx - 35, cy + 60)
    pts[291] = (cx + 35, cy + 60)
    pts[17] = (cx, cy + 80)
    pts[199] = (cx, cy + 130)
    return pts


def render_state(name: str, severity: Severity, face: FaceMetrics, body: BodyMetrics, presence: PresenceState, blink_rate: float, counts: dict, out_path: Path, debug: bool = False, ear_min: float | None = None, mar_max: float | None = None) -> None:
    img = synthetic_frame()
    width, height = img.shape[1], img.shape[0]

    if face.detected:
        cx, cy = width // 2, height // 2
        face.landmarks = _synthetic_landmarks(width, height)
        left_eye = np.array(
            [[cx - 75, cy - 60], [cx - 65, cy - 70], [cx - 45, cy - 70], [cx - 35, cy - 60], [cx - 45, cy - 50], [cx - 65, cy - 50]],
            dtype=np.int32,
        )
        right_eye = np.array(
            [[cx + 35, cy - 60], [cx + 45, cy - 70], [cx + 65, cy - 70], [cx + 75, cy - 60], [cx + 65, cy - 50], [cx + 45, cy - 50]],
            dtype=np.int32,
        )
        mouth = np.array(
            [[cx - 40, cy + 55], [cx - 20, cy + 50], [cx + 20, cy + 50], [cx + 40, cy + 55], [cx + 20, cy + 70], [cx - 20, cy + 70]],
            dtype=np.int32,
        )
        face.eye_polylines = (left_eye, right_eye)
        face.mouth_polyline = mouth

    payload = HudPayload(
        severity=severity,
        face=face,
        body=body,
        presence=presence,
        blink_rate=blink_rate,
        fps=18.4,
        session_start=datetime.now() - timedelta(minutes=12, seconds=33),
        counts=counts,
        ear_min_recent=ear_min,
        mar_max_recent=mar_max,
        debug_visible=debug,
    )
    rendered = render_hud(img, payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), rendered)
    print(out_path)


def main() -> int:
    out_dir = PROJECT_ROOT / "outputs" / "screenshots"

    body_ok = BodyMetrics(detected=True, shoulder_tilt_deg=2.4, forward_head_ratio=0.12,
                          visibility_score=0.94,
                          shoulder_left_xy=(380, 540), shoulder_right_xy=(640, 540),
                          ear_left_xy=(420, 360), ear_right_xy=(600, 360),
                          shoulders_reliable=True, ears_reliable=True)

    render_state(
        "ok",
        Severity.OK,
        FaceMetrics(detected=True, ear_mean=0.302, mar=0.18, yaw_deg=3.1, pitch_deg=-1.4),
        body_ok,
        PresenceState(face_present=True, absence_seconds=0.0, last_seen_timestamp=0.0),
        blink_rate=15.4,
        counts={Severity.VIG1: 0, Severity.VIG2: 0, Severity.VIG3: 0},
        out_path=out_dir / "01-estado-ok.png",
        debug=True,
        ear_min=0.282,
        mar_max=0.21,
    )

    render_state(
        "yawn",
        Severity.VIG2,
        FaceMetrics(detected=True, ear_mean=0.288, mar=0.72, yaw_deg=4.1, pitch_deg=-2.2),
        body_ok,
        PresenceState(face_present=True, absence_seconds=0.0, last_seen_timestamp=0.0),
        blink_rate=11.0,
        counts={Severity.VIG1: 0, Severity.VIG2: 1, Severity.VIG3: 0},
        out_path=out_dir / "02-estado-vig2-bocejo.png",
        debug=True,
        ear_min=0.278,
        mar_max=0.72,
    )

    render_state(
        "distract",
        Severity.VIG2,
        FaceMetrics(detected=True, ear_mean=0.295, mar=0.21, yaw_deg=38.6, pitch_deg=4.1),
        body_ok,
        PresenceState(face_present=True, absence_seconds=0.0, last_seen_timestamp=0.0),
        blink_rate=12.2,
        counts={Severity.VIG1: 0, Severity.VIG2: 2, Severity.VIG3: 0},
        out_path=out_dir / "03-estado-vig2-distracao.png",
        debug=True,
        ear_min=0.279,
        mar_max=0.24,
    )

    render_state(
        "micro",
        Severity.VIG1,
        FaceMetrics(detected=True, ear_mean=0.108, mar=0.20, yaw_deg=-2.3, pitch_deg=8.0),
        body_ok,
        PresenceState(face_present=True, absence_seconds=0.0, last_seen_timestamp=0.0),
        blink_rate=9.4,
        counts={Severity.VIG1: 1, Severity.VIG2: 2, Severity.VIG3: 1},
        out_path=out_dir / "04-estado-vig1-microsono.png",
        debug=True,
        ear_min=0.108,
        mar_max=0.22,
    )

    render_state(
        "absence",
        Severity.VIG1,
        FaceMetrics(detected=False),
        BodyMetrics(detected=False),
        PresenceState(face_present=False, absence_seconds=11.4, last_seen_timestamp=0.0),
        blink_rate=8.6,
        counts={Severity.VIG1: 2, Severity.VIG2: 2, Severity.VIG3: 1},
        out_path=out_dir / "05-estado-vig1-ausencia.png",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
