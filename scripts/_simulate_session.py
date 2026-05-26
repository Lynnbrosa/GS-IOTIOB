from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.alert_engine import AlertEngine
from src.body_metrics import BodyMetrics
from src.config import AppConfig
from src.event_logger import EventLogger
from src.face_metrics import FaceMetrics
from src.presence import PresenceState


def fake_face(ear: float, mar: float = 0.1, yaw: float = 0.0, pitch: float = 0.0) -> FaceMetrics:
    return FaceMetrics(detected=True, ear_mean=ear, mar=mar, yaw_deg=yaw, pitch_deg=pitch)


def fake_body(tilt: float = 1.0, fhr: float = 0.05) -> BodyMetrics:
    return BodyMetrics(detected=True, shoulder_tilt_deg=tilt, forward_head_ratio=fhr)


def main() -> int:
    db_path = PROJECT_ROOT / "data" / "logs" / "session_simulated.db"
    if db_path.exists():
        db_path.unlink()
    config = AppConfig()
    engine = AlertEngine(config)

    logger = EventLogger(db_path, operator_id="operator_demo")
    logger.start_session()

    t = time.time()
    scenarios = []

    for i in range(60):
        scenarios.append((t + i * 0.1, fake_face(ear=0.30), fake_body(), True, 0.0, 14.0))

    for i in range(40):
        scenarios.append((t + 6.0 + i * 0.05, fake_face(ear=0.10), fake_body(), True, 0.0, 14.0))

    for i in range(55):
        scenarios.append((t + 10.0 + i * 0.1, fake_face(ear=0.30, mar=0.75), fake_body(), True, 0.0, 14.0))

    for i in range(70):
        scenarios.append((t + 18.0 + i * 0.1, fake_face(ear=0.30, yaw=35.0), fake_body(), True, 0.0, 14.0))

    for i in range(110):
        scenarios.append(
            (t + 28.0 + i * 0.1, fake_face(ear=0.30), fake_body(tilt=12.0, fhr=0.30), True, 0.0, 14.0)
        )

    for i in range(120):
        scenarios.append(
            (
                t + 42.0 + i * 0.1,
                FaceMetrics(detected=False),
                BodyMetrics(detected=False),
                False,
                i * 0.1,
                14.0,
            )
        )

    for ts, face, body, present, absence, blink in scenarios:
        presence = PresenceState(face_present=present, absence_seconds=absence, last_seen_timestamp=ts)
        events = engine.evaluate(ts, face, body, presence, blink)
        for evt in events:
            logger.log_event(
                severity=evt.severity.value,
                event_type=evt.event_type.value,
                duration_seconds=evt.duration_seconds,
                metric_value=evt.metric_value,
                notes=evt.notes,
                timestamp=evt.timestamp,
            )
        logger.increment_frames()

    logger.end_session()
    logger.close()
    print(db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
