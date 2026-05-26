from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

import numpy as np


class MovingMedian:
    def __init__(self, window: int = 5):
        self.window = max(1, window)
        self._buf: Deque[float] = deque(maxlen=self.window)

    def push(self, value: float) -> float:
        self._buf.append(value)
        if not self._buf:
            return value
        return float(np.median(self._buf))

    def reset(self) -> None:
        self._buf.clear()


class MovingMean:
    def __init__(self, window: int = 5):
        self.window = max(1, window)
        self._buf: Deque[float] = deque(maxlen=self.window)

    def push(self, value: float) -> float:
        self._buf.append(value)
        if not self._buf:
            return value
        return float(np.mean(self._buf))

    def reset(self) -> None:
        self._buf.clear()


@dataclass
class BlinkEvent:
    timestamp: float


class BlinkCounter:
    def __init__(self, ear_threshold: float, min_frames: int = 2, window_seconds: float = 60.0):
        self.threshold = ear_threshold
        self.min_frames = max(1, min_frames)
        self.window_seconds = window_seconds
        self._below_count = 0
        self._events: Deque[BlinkEvent] = deque()
        self._last_ear: float = 1.0

    def update(self, timestamp: float, ear_value: float) -> bool:
        blink_just_finished = False

        if ear_value < self.threshold:
            self._below_count += 1
        else:
            if self._below_count >= self.min_frames:
                self._events.append(BlinkEvent(timestamp=timestamp))
                blink_just_finished = True
            self._below_count = 0

        cutoff = timestamp - self.window_seconds
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

        self._last_ear = ear_value
        return blink_just_finished

    def rate_per_minute(self, now_ts: float) -> float:
        cutoff = now_ts - self.window_seconds
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()
        if self.window_seconds <= 0:
            return 0.0
        return len(self._events) * (60.0 / self.window_seconds)

    def event_count(self) -> int:
        return len(self._events)


@dataclass
class FpsCounter:
    window: int = 30
    _times: Deque[float] = None

    def __post_init__(self):
        self._times = deque(maxlen=self.window)

    def tick(self, timestamp: float) -> None:
        self._times.append(timestamp)

    def fps(self) -> float:
        if len(self._times) < 2:
            return 0.0
        span = self._times[-1] - self._times[0]
        if span <= 0:
            return 0.0
        return (len(self._times) - 1) / span


class RecentExtreme:
    def __init__(self, window_seconds: float = 5.0):
        self.window_seconds = window_seconds
        self._samples: Deque[Tuple[float, float]] = deque()

    def push(self, timestamp: float, value: float) -> None:
        self._samples.append((timestamp, value))
        cutoff = timestamp - self.window_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def min(self) -> Optional[float]:
        if not self._samples:
            return None
        return min(v for _, v in self._samples)

    def max(self) -> Optional[float]:
        if not self._samples:
            return None
        return max(v for _, v in self._samples)
