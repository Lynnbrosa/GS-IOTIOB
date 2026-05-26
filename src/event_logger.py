from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

logger = logging.getLogger("mcvs.logger")


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  severity TEXT NOT NULL,
  event_type TEXT NOT NULL,
  duration_seconds REAL,
  metric_value REAL,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  start_time TEXT NOT NULL,
  end_time TEXT,
  operator_id TEXT,
  total_frames INTEGER,
  total_events INTEGER
);
"""


def _iso_utc(ts: Optional[float] = None) -> str:
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


class EventLogger:
    def __init__(self, db_path: Path, operator_id: str = "operator_01"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(SCHEMA)
        self._operator_id = operator_id
        self._session_id: Optional[int] = None
        self._total_frames = 0
        self._total_events = 0

    def start_session(self) -> int:
        cur = self._conn.execute(
            "INSERT INTO session (start_time, operator_id, total_frames, total_events) VALUES (?, ?, 0, 0)",
            (_iso_utc(), self._operator_id),
        )
        self._conn.commit()
        self._session_id = cur.lastrowid
        logger.info("sessao iniciada id=%s db=%s", self._session_id, self.db_path)
        return self._session_id

    def log_event(
        self,
        severity: str,
        event_type: str,
        duration_seconds: Optional[float],
        metric_value: Optional[float],
        notes: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO events (timestamp, severity, event_type, duration_seconds, metric_value, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                _iso_utc(timestamp),
                severity,
                event_type,
                duration_seconds,
                metric_value,
                notes,
            ),
        )
        self._conn.commit()
        self._total_events += 1
        return cur.lastrowid

    def increment_frames(self, count: int = 1) -> None:
        self._total_frames += count

    def end_session(self) -> None:
        if self._session_id is None:
            return
        self._conn.execute(
            "UPDATE session SET end_time = ?, total_frames = ?, total_events = ? WHERE id = ?",
            (_iso_utc(), self._total_frames, self._total_events, self._session_id),
        )
        self._conn.commit()
        logger.info(
            "sessao encerrada id=%s frames=%s eventos=%s",
            self._session_id,
            self._total_frames,
            self._total_events,
        )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "EventLogger":
        self.start_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_session()
        self.close()


def load_events(db_path: Path) -> Tuple[List[dict], dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    events_rows = conn.execute(
        "SELECT timestamp, severity, event_type, duration_seconds, metric_value, notes FROM events ORDER BY id"
    ).fetchall()
    session_row = conn.execute(
        "SELECT start_time, end_time, operator_id, total_frames, total_events FROM session ORDER BY id LIMIT 1"
    ).fetchone()
    conn.close()

    events = [dict(r) for r in events_rows]
    session = dict(session_row) if session_row else {}
    return events, session
