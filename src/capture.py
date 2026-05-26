from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional

import cv2
import numpy as np

from .config import CaptureConfig

logger = logging.getLogger("mcvs.capture")


@dataclass
class Frame:
    image: np.ndarray
    timestamp: float
    index: int


class WebcamCapture:
    def __init__(self, config: CaptureConfig):
        self.config = config
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame_index = 0
        self._last_timestamp = 0.0

    def open(self) -> None:
        indices: Iterable[int] = (self.config.camera_index, *self.config.fallback_indices)
        backends = []
        if hasattr(cv2, "CAP_MSMF"):
            backends.append(("MSMF", cv2.CAP_MSMF))
        if hasattr(cv2, "CAP_DSHOW"):
            backends.append(("DSHOW", cv2.CAP_DSHOW))
        backends.append(("ANY", cv2.CAP_ANY))

        tried = []
        for idx in indices:
            for name, backend in backends:
                tag = f"idx={idx} backend={name}"
                if tag in tried:
                    continue
                tried.append(tag)
                cap = cv2.VideoCapture(idx, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                ok, _frame = cap.read()
                if not ok:
                    cap.release()
                    logger.debug("abriu %s mas read falhou", tag)
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
                cap.set(cv2.CAP_PROP_FPS, self.config.fps_target)
                self._cap = cap
                logger.info("webcam aberta %s", tag)
                return
        raise RuntimeError(
            "nenhuma webcam funcional. tentativas: "
            + ", ".join(tried)
            + ". verifique Configuracoes do Windows -> Privacidade -> Camera "
            + "e se nenhum outro app (Teams, Zoom, navegador) esta usando a webcam"
        )

    def read(self) -> Optional[Frame]:
        if self._cap is None:
            raise RuntimeError("capture nao foi aberto. chame open() primeiro")
        ok, image = self._cap.read()
        if not ok or image is None:
            logger.warning("frame nao lido. tentando recuperar")
            time.sleep(0.05)
            ok, image = self._cap.read()
            if not ok or image is None:
                return None

        image = cv2.flip(image, 1)
        ts = time.time()
        self._frame_index += 1
        self._last_timestamp = ts
        return Frame(image=image, timestamp=ts, index=self._frame_index)

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("webcam liberada")

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()


class VideoWriter:
    def __init__(self, path: str, width: int, height: int, fps: float = 20.0):
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
        self._path = path
        if not self._writer.isOpened():
            raise RuntimeError(f"nao foi possivel abrir VideoWriter em {path}")

    def write(self, frame: np.ndarray) -> None:
        self._writer.write(frame)

    def release(self) -> None:
        self._writer.release()
        logger.info("video salvo em %s", self._path)
