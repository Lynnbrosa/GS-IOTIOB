from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PresenceState:
    face_present: bool
    absence_seconds: float
    last_seen_timestamp: Optional[float]


class PresenceTracker:
    def __init__(self):
        self._last_seen: Optional[float] = None
        self._absence_start: Optional[float] = None

    def update(self, now_ts: float, face_detected: bool) -> PresenceState:
        if face_detected:
            self._last_seen = now_ts
            self._absence_start = None
            return PresenceState(
                face_present=True,
                absence_seconds=0.0,
                last_seen_timestamp=now_ts,
            )

        if self._absence_start is None:
            self._absence_start = now_ts
        absence = max(0.0, now_ts - self._absence_start)
        return PresenceState(
            face_present=False,
            absence_seconds=absence,
            last_seen_timestamp=self._last_seen,
        )

    def reset(self) -> None:
        self._last_seen = None
        self._absence_start = None
