"""Signal and SignalBuffer — the universal event format."""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from percept.initiatives.config import SIGNALS_DB


@dataclass
class Signal:
    source: str          # "gmail", "github", "oura", "calendar"
    signal_type: str     # "new_email", "pr_merged", "low_readiness"
    entity: str          # What entity this is about
    data: dict           # Signal-specific payload
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    urgency: float = 0.5       # 0-1
    confidence: float = 1.0    # 0-1
    signal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Signal:
        d = dict(d)
        if isinstance(d.get("timestamp"), str):
            d["timestamp"] = datetime.fromisoformat(d["timestamp"])
        if isinstance(d.get("data"), str):
            d["data"] = json.loads(d["data"])
        return cls(**d)

    @classmethod
    def from_json(cls, raw: str) -> Signal:
        return cls.from_dict(json.loads(raw))


class SignalBuffer:
    """Rolling window of recent signals backed by SQLite."""

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or SIGNALS_DB)
        self._persistent_conn = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    data TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    urgency REAL DEFAULT 0.5,
                    confidence REAL DEFAULT 1.0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_source_type
                ON signals(source, signal_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_timestamp
                ON signals(timestamp)
            """)

    def _conn(self) -> sqlite3.Connection:
        if self._persistent_conn:
            return self._persistent_conn
        return sqlite3.connect(self.db_path)

    def add(self, signal: Signal):
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO signals
                   (signal_id, source, signal_type, entity, data, timestamp, urgency, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal.signal_id,
                    signal.source,
                    signal.signal_type,
                    signal.entity,
                    json.dumps(signal.data),
                    signal.timestamp.isoformat(),
                    signal.urgency,
                    signal.confidence,
                ),
            )

    def query(
        self,
        source: Optional[str] = None,
        signal_type: Optional[str] = None,
        since_minutes: Optional[int] = None,
        limit: int = 1000,
    ) -> list[Signal]:
        clauses = []
        params: list = []
        if source and source != "*":
            clauses.append("source = ?")
            params.append(source)
        if signal_type and signal_type != "*":
            clauses.append("signal_type = ?")
            params.append(signal_type)
        if since_minutes is not None:
            cutoff = datetime.now(timezone.utc).isoformat()
            # SQLite datetime comparison works on ISO strings
            clauses.append("timestamp >= datetime(?, ?)")
            params.extend([cutoff, f"-{since_minutes} minutes"])
        where = " AND ".join(clauses) if clauses else "1=1"
        sql = f"SELECT signal_id, source, signal_type, entity, data, timestamp, urgency, confidence FROM signals WHERE {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()

        signals = []
        for row in rows:
            signals.append(Signal(
                signal_id=row[0],
                source=row[1],
                signal_type=row[2],
                entity=row[3],
                data=json.loads(row[4]),
                timestamp=datetime.fromisoformat(row[5]),
                urgency=row[6],
                confidence=row[7],
            ))
        return signals

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]

    def prune(self, older_than_minutes: int = 1440):
        """Remove signals older than the given window."""
        cutoff = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM signals WHERE timestamp < datetime(?, ?)",
                (cutoff, f"-{older_than_minutes} minutes"),
            )

    def clear(self):
        with self._conn() as conn:
            conn.execute("DELETE FROM signals")
