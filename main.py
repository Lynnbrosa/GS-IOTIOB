from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

from src import LOG_DIR, configure_logging
from src.alert_engine import AlertEngine, Severity
from src.body_metrics import BodyMetricsExtractor
from src.capture import VideoWriter, WebcamCapture
from src.config import AppConfig, load_calibration
from src.event_logger import EventLogger
from src.face_metrics import FaceMetricsExtractor
from src.overlay import HudPayload, render_hud
from src.presence import PresenceTracker
from src.stats import BlinkCounter, FpsCounter, MovingMedian, RecentExtreme


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mcvs",
        description="OrbittAPI Mission Control Vigilance System",
    )
    parser.add_argument(
        "--calibration",
        type=Path,
        default=None,
        help="caminho para arquivo de calibracao JSON",
    )
    parser.add_argument(
        "--record",
        type=Path,
        default=None,
        help="caminho para salvar video MP4 da sessao",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="executar sem janela. util para servidores",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="encerra a sessao apos N segundos. omitir para rodar ate ESC",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=None,
        help="indice da webcam. sobrescreve config",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="caminho do SQLite. default usa data/logs/session_TIMESTAMP.db",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="log em nivel DEBUG",
    )
    return parser.parse_args(argv)


def default_db_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return LOG_DIR / f"session_{stamp}.db"


def run(args: argparse.Namespace) -> int:
    logger = configure_logging(level=logging.DEBUG if args.verbose else logging.INFO)

    config: AppConfig = load_calibration(args.calibration)
    if args.camera_index is not None:
        config.capture.camera_index = args.camera_index

    db_path = args.db or default_db_path()
    print(db_path)

    capture = WebcamCapture(config.capture)
    capture.open()

    face_extractor = FaceMetricsExtractor()
    body_extractor = BodyMetricsExtractor()
    presence_tracker = PresenceTracker()
    engine = AlertEngine(config)
    fps_counter = FpsCounter()

    ear_smoother = MovingMedian(window=config.hysteresis.smoothing_window)
    mar_smoother = MovingMedian(window=config.hysteresis.smoothing_window)
    yaw_smoother = MovingMedian(window=config.hysteresis.smoothing_window)
    pitch_smoother = MovingMedian(window=config.hysteresis.smoothing_window)

    blink_counter = BlinkCounter(
        ear_threshold=config.face.ear_blink_threshold,
        min_frames=config.face.ear_blink_min_frames,
        window_seconds=60.0,
    )
    ear_extreme = RecentExtreme(window_seconds=5.0)
    mar_extreme = RecentExtreme(window_seconds=5.0)

    session_start = datetime.now()

    writer: Optional[VideoWriter] = None
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        writer = VideoWriter(
            str(args.record),
            config.capture.width,
            config.capture.height,
            fps=20.0,
        )

    event_logger = EventLogger(db_path, operator_id=config.operator_id)
    event_logger.start_session()

    window_name = "OrbittAPI Mission Control Vigilance System"
    if not args.headless:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    deadline = None
    if args.duration:
        deadline = time.time() + args.duration

    debug_visible = False

    try:
        while True:
            if deadline and time.time() >= deadline:
                logger.info("duracao limite atingida")
                break

            frame = capture.read()
            if frame is None:
                logger.warning("frame nulo. encerrando")
                break

            fps_counter.tick(frame.timestamp)
            event_logger.increment_frames()

            face_metrics = face_extractor.process(frame.image)
            body_metrics = body_extractor.process(frame.image)
            presence_state = presence_tracker.update(frame.timestamp, face_metrics.detected)

            if face_metrics.detected:
                face_metrics.ear_mean = ear_smoother.push(face_metrics.ear_mean)
                face_metrics.mar = mar_smoother.push(face_metrics.mar)
                face_metrics.yaw_deg = yaw_smoother.push(face_metrics.yaw_deg)
                face_metrics.pitch_deg = pitch_smoother.push(face_metrics.pitch_deg)
                blink_counter.update(frame.timestamp, face_metrics.ear_mean)
                ear_extreme.push(frame.timestamp, face_metrics.ear_mean)
                mar_extreme.push(frame.timestamp, face_metrics.mar)

            blink_rate = blink_counter.rate_per_minute(frame.timestamp)
            ear_min_recent = ear_extreme.min()
            mar_max_recent = mar_extreme.max()

            events = engine.evaluate(
                frame.timestamp,
                face_metrics,
                body_metrics,
                presence_state,
                blink_rate,
            )

            for evt in events:
                event_logger.log_event(
                    severity=evt.severity.value,
                    event_type=evt.event_type.value,
                    duration_seconds=evt.duration_seconds,
                    metric_value=evt.metric_value,
                    notes=evt.notes,
                    timestamp=evt.timestamp,
                )
                logger.info(
                    "evento %s/%s duration=%.2fs metric=%.3f",
                    evt.severity.value,
                    evt.event_type.value,
                    evt.duration_seconds,
                    evt.metric_value if evt.metric_value is not None else 0.0,
                )

            payload = HudPayload(
                severity=engine.state.current_severity,
                face=face_metrics,
                body=body_metrics,
                presence=presence_state,
                blink_rate=blink_rate,
                fps=fps_counter.fps(),
                session_start=session_start,
                counts=engine.state.event_counts,
                ear_min_recent=ear_min_recent,
                mar_max_recent=mar_max_recent,
                debug_visible=debug_visible,
            )

            rendered = render_hud(frame.image, payload)

            if writer is not None:
                writer.write(rendered)

            if not args.headless:
                cv2.imshow(window_name, rendered)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord("q"):
                    logger.info("encerrando por tecla")
                    break
                if key == ord("d"):
                    debug_visible = not debug_visible

    except KeyboardInterrupt:
        logger.info("interrupcao do usuario")
    finally:
        if writer is not None:
            writer.release()
        if not args.headless:
            cv2.destroyAllWindows()
        face_extractor.close()
        body_extractor.close()
        capture.release()
        event_logger.end_session()
        event_logger.close()

    return 0


def main() -> int:
    args = parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
