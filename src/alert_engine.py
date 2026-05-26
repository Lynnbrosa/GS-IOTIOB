from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .body_metrics import BodyMetrics
from .config import AppConfig
from .face_metrics import FaceMetrics
from .presence import PresenceState

logger = logging.getLogger("mcvs.engine")


class Severity(str, Enum):
    OK = "OK"
    VIG1 = "VIG-1"
    VIG2 = "VIG-2"
    VIG3 = "VIG-3"


class EventType(str, Enum):
    MICROSLEEP = "microsleep"
    YAWN = "yawn"
    DISTRACTION = "distraction"
    BLINK_ANOMALY = "blink_anomaly"
    POSTURE = "posture"
    ABSENCE_SHORT = "absence_short"
    ABSENCE_LONG = "absence_long"


SEVERITY_RANK = {
    Severity.OK: 0,
    Severity.VIG3: 1,
    Severity.VIG2: 2,
    Severity.VIG1: 3,
}


@dataclass
class Event:
    severity: Severity
    event_type: EventType
    duration_seconds: float
    metric_value: Optional[float]
    notes: Optional[str] = None
    timestamp: Optional[float] = None


@dataclass
class _Sustain:
    started_at: Optional[float] = None
    last_value: float = 0.0
    cooldown_until: float = 0.0
    fired: bool = False

    def reset(self) -> None:
        self.started_at = None
        self.last_value = 0.0
        self.fired = False


@dataclass
class EngineState:
    current_severity: Severity = Severity.OK
    event_counts: Dict[Severity, int] = field(
        default_factory=lambda: {Severity.VIG1: 0, Severity.VIG2: 0, Severity.VIG3: 0}
    )
    last_event_type: Optional[EventType] = None
    last_event_timestamp: Optional[float] = None


class AlertEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.state = EngineState()

        self._microsleep = _Sustain()
        self._yawn = _Sustain()
        self._distraction = _Sustain()
        self._posture = _Sustain()
        self._absence_short = _Sustain()
        self._absence_long = _Sustain()
        self._blink_anomaly = _Sustain()

    def evaluate(
        self,
        timestamp: float,
        face: FaceMetrics,
        body: BodyMetrics,
        presence: PresenceState,
        blink_rate: float,
    ) -> List[Event]:
        events: List[Event] = []

        events.extend(self._check_absence(timestamp, presence))

        if face.detected:
            events.extend(self._check_microsleep(timestamp, face))
            events.extend(self._check_yawn(timestamp, face))
            events.extend(self._check_distraction(timestamp, face))
            events.extend(self._check_blink_anomaly(timestamp, blink_rate))
        else:
            self._microsleep.reset()
            self._yawn.reset()
            self._distraction.reset()

        if body.detected:
            events.extend(self._check_posture(timestamp, body))
        else:
            self._posture.reset()

        self.state.current_severity = self._derive_current_severity(
            timestamp, presence, face, body, blink_rate
        )

        for evt in events:
            evt.timestamp = timestamp
            self.state.event_counts[evt.severity] = self.state.event_counts.get(evt.severity, 0) + 1
            self.state.last_event_type = evt.event_type
            self.state.last_event_timestamp = timestamp

        return events

    def _maybe_emit(
        self,
        tracker: _Sustain,
        timestamp: float,
        triggered: bool,
        duration_required: float,
        severity: Severity,
        event_type: EventType,
        metric_value: float,
        notes: Optional[str] = None,
    ) -> Optional[Event]:
        cooldown = self.config.hysteresis.cooldown_seconds

        if not triggered:
            if tracker.fired and timestamp >= tracker.cooldown_until:
                tracker.reset()
            elif not tracker.fired:
                tracker.started_at = None
            return None

        if tracker.fired:
            tracker.last_value = metric_value
            return None

        if tracker.started_at is None:
            tracker.started_at = timestamp
            tracker.last_value = metric_value
            return None

        elapsed = timestamp - tracker.started_at
        if elapsed >= duration_required:
            tracker.fired = True
            tracker.cooldown_until = timestamp + cooldown
            return Event(
                severity=severity,
                event_type=event_type,
                duration_seconds=elapsed,
                metric_value=metric_value,
                notes=notes,
            )

        tracker.last_value = metric_value
        return None

    def _check_microsleep(self, ts: float, face: FaceMetrics) -> List[Event]:
        triggered = face.ear_mean < self.config.face.ear_microsleep
        event = self._maybe_emit(
            self._microsleep,
            ts,
            triggered,
            self.config.face.ear_microsleep_duration_s,
            Severity.VIG1,
            EventType.MICROSLEEP,
            face.ear_mean,
            notes=f"EAR={face.ear_mean:.3f}",
        )
        return [event] if event else []

    def _check_yawn(self, ts: float, face: FaceMetrics) -> List[Event]:
        triggered = face.mar > self.config.face.mar_yawn
        event = self._maybe_emit(
            self._yawn,
            ts,
            triggered,
            self.config.face.mar_yawn_duration_s,
            Severity.VIG2,
            EventType.YAWN,
            face.mar,
            notes=f"MAR={face.mar:.3f}",
        )
        return [event] if event else []

    def _check_distraction(self, ts: float, face: FaceMetrics) -> List[Event]:
        yaw_abs = abs(face.yaw_deg)
        pitch_abs = abs(face.pitch_deg)
        triggered = (
            yaw_abs > self.config.face.yaw_distraction_deg
            or pitch_abs > self.config.face.pitch_distraction_deg
        )
        metric = max(yaw_abs, pitch_abs)
        event = self._maybe_emit(
            self._distraction,
            ts,
            triggered,
            self.config.face.distraction_duration_s,
            Severity.VIG2,
            EventType.DISTRACTION,
            metric,
            notes=f"yaw={face.yaw_deg:.1f} pitch={face.pitch_deg:.1f}",
        )
        return [event] if event else []

    def _check_blink_anomaly(self, ts: float, blink_rate: float) -> List[Event]:
        cfg = self.config.face
        triggered = blink_rate < cfg.blink_rate_min or blink_rate > cfg.blink_rate_max
        event = self._maybe_emit(
            self._blink_anomaly,
            ts,
            triggered,
            cfg.blink_anomaly_window_s,
            Severity.VIG2,
            EventType.BLINK_ANOMALY,
            blink_rate,
            notes=f"blink_rate={blink_rate:.1f}/min",
        )
        return [event] if event else []

    def _check_posture(self, ts: float, body: BodyMetrics) -> List[Event]:
        cfg = self.config.body
        triggered = (
            body.shoulder_tilt_deg > cfg.shoulder_tilt_deg
            or body.forward_head_ratio > cfg.forward_head_ratio
        )
        metric = max(body.shoulder_tilt_deg, body.forward_head_ratio * 100.0)
        event = self._maybe_emit(
            self._posture,
            ts,
            triggered,
            cfg.posture_duration_s,
            Severity.VIG3,
            EventType.POSTURE,
            metric,
            notes=(
                f"tilt={body.shoulder_tilt_deg:.1f} "
                f"fhr={body.forward_head_ratio:.2f}"
            ),
        )
        return [event] if event else []

    def _check_absence(self, ts: float, presence: PresenceState) -> List[Event]:
        cfg = self.config.presence
        events: List[Event] = []

        long_triggered = (
            not presence.face_present
            and presence.absence_seconds >= cfg.long_absence_min_s
        )
        long_event = self._maybe_emit(
            self._absence_long,
            ts,
            long_triggered,
            0.0,
            Severity.VIG1,
            EventType.ABSENCE_LONG,
            presence.absence_seconds,
            notes=f"absence={presence.absence_seconds:.1f}s",
        )
        if long_event:
            events.append(long_event)

        short_triggered = (
            not presence.face_present
            and cfg.short_absence_min_s <= presence.absence_seconds < cfg.long_absence_min_s
        )
        short_event = self._maybe_emit(
            self._absence_short,
            ts,
            short_triggered,
            0.0,
            Severity.VIG3,
            EventType.ABSENCE_SHORT,
            presence.absence_seconds,
            notes=f"absence={presence.absence_seconds:.1f}s",
        )
        if short_event:
            events.append(short_event)

        return events

    def _derive_current_severity(
        self,
        ts: float,
        presence: PresenceState,
        face: FaceMetrics,
        body: BodyMetrics,
        blink_rate: float,
    ) -> Severity:
        if not presence.face_present and presence.absence_seconds >= self.config.presence.long_absence_min_s:
            return Severity.VIG1

        if face.detected and face.ear_mean < self.config.face.ear_microsleep and self._microsleep.fired:
            return Severity.VIG1

        if (face.detected and self._yawn.fired) or self._distraction.fired or self._blink_anomaly.fired:
            return Severity.VIG2

        if not presence.face_present and presence.absence_seconds >= self.config.presence.short_absence_min_s:
            return Severity.VIG3

        if body.detected and self._posture.fired:
            return Severity.VIG3

        return Severity.OK
