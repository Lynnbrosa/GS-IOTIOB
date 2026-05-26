from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import configure_logging
from src.capture import WebcamCapture
from src.config import (
    CALIBRATION_PATH,
    AppConfig,
    load_calibration,
    save_calibration,
)
from src.face_metrics import FaceMetricsExtractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calibracao inicial de thresholds com baseline de 30 segundos",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="duracao da janela de calibracao em segundos",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="caminho de saida do JSON",
    )
    parser.add_argument(
        "--camera-index",
        type=int,
        default=None,
        help="indice da webcam",
    )
    parser.add_argument(
        "--operator-id",
        type=str,
        default=None,
        help="identificador do operador",
    )
    return parser.parse_args()


def collect_baseline(duration: float, camera_index: int) -> dict:
    logger = logging.getLogger("mcvs.calibrate")
    config = AppConfig()
    if camera_index is not None:
        config.capture.camera_index = camera_index

    capture = WebcamCapture(config.capture)
    capture.open()
    extractor = FaceMetricsExtractor()

    ear_samples = []
    mar_samples = []
    yaw_samples = []
    pitch_samples = []

    window_name = "Calibracao MCVS"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    deadline = time.time() + duration

    try:
        while time.time() < deadline:
            frame = capture.read()
            if frame is None:
                continue

            metrics = extractor.process(frame.image)
            if metrics.detected:
                ear_samples.append(metrics.ear_mean)
                mar_samples.append(metrics.mar)
                yaw_samples.append(metrics.yaw_deg)
                pitch_samples.append(metrics.pitch_deg)

            remaining = max(0.0, deadline - time.time())
            cv2.putText(
                frame.image,
                f"Olhe para a camera por {remaining:5.1f}s",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (235, 235, 235),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame.image,
                f"amostras: {len(ear_samples)}",
                (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (160, 160, 160),
                1,
                cv2.LINE_AA,
            )
            cv2.imshow(window_name, frame.image)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                logger.info("calibracao cancelada pelo usuario")
                break
    finally:
        extractor.close()
        capture.release()
        cv2.destroyAllWindows()

    if not ear_samples:
        raise RuntimeError("nenhuma amostra coletada. verifique iluminacao e camera")

    ear_baseline = float(np.median(ear_samples))
    mar_baseline = float(np.median(mar_samples))
    yaw_baseline = float(np.median(np.abs(yaw_samples)))
    pitch_baseline = float(np.median(np.abs(pitch_samples)))

    return {
        "ear_baseline": ear_baseline,
        "mar_baseline": mar_baseline,
        "yaw_baseline_abs": yaw_baseline,
        "pitch_baseline_abs": pitch_baseline,
        "sample_count": len(ear_samples),
    }


def derive_config(baseline: dict, operator_id: str | None) -> AppConfig:
    config = AppConfig()
    ear_b = baseline["ear_baseline"]
    config.face.ear_microsleep = max(0.10, ear_b * 0.55)
    config.face.ear_blink_threshold = max(0.16, ear_b * 0.72)

    mar_b = baseline["mar_baseline"]
    config.face.mar_yawn = max(0.40, mar_b + 0.30)

    yaw_b = baseline["yaw_baseline_abs"]
    pitch_b = baseline["pitch_baseline_abs"]
    config.face.yaw_distraction_deg = max(15.0, yaw_b + 25.0)
    config.face.pitch_distraction_deg = max(15.0, pitch_b + 25.0)

    if operator_id:
        config.operator_id = operator_id

    return config


def main() -> int:
    configure_logging()
    args = parse_args()
    baseline = collect_baseline(args.duration, args.camera_index)
    config = derive_config(baseline, args.operator_id)
    target = args.output or CALIBRATION_PATH
    saved = save_calibration(config, target)
    print(saved)
    print(f"ear_microsleep={config.face.ear_microsleep:.3f}")
    print(f"ear_blink={config.face.ear_blink_threshold:.3f}")
    print(f"mar_yawn={config.face.mar_yawn:.3f}")
    print(f"yaw_distraction_deg={config.face.yaw_distraction_deg:.1f}")
    print(f"pitch_distraction_deg={config.face.pitch_distraction_deg:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
