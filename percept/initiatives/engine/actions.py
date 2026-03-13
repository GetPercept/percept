"""Action executors — notify, draft, escalate, execute, log."""
from __future__ import annotations

import json
import sqlite3
import re
from datetime import datetime, timezone
from typing import Optional

from percept.initiatives.config import HISTORY_DB
from percept.initiatives.engine.rules import Action


class ActionHistory:
    """Tracks fired actions in SQLite."""

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or HISTORY_DB)
        self._persistent_conn = None
        if self.db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:")
        self._init_db()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_name TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    target TEXT,
                    rendered_message TEXT,
                    context TEXT,
                    timestamp TEXT NOT NULL,
                    status TEXT DEFAULT 'fired'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_rule
                ON history(rule_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_timestamp
                ON history(timestamp)
            """)

    def _conn(self) -> sqlite3.Connection:
        if self._persistent_conn:
            return self._persistent_conn
        return sqlite3.connect(self.db_path)

    def record(self, rule_name: str, action: Action, rendered: str, context: dict, status: str = "fired"):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO history (rule_name, action_type, target, rendered_message, context, timestamp, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule_name,
                    action.action_type,
                    action.target,
                    rendered,
                    json.dumps(context),
                    datetime.now(timezone.utc).isoformat(),
                    status,
                ),
            )

    def recent(self, limit: int = 20, rule_name: Optional[str] = None) -> list[dict]:
        with self._conn() as conn:
            if rule_name:
                rows = conn.execute(
                    "SELECT id, rule_name, action_type, target, rendered_message, timestamp, status FROM history WHERE rule_name = ? ORDER BY timestamp DESC LIMIT ?",
                    (rule_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, rule_name, action_type, target, rendered_message, timestamp, status FROM history ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [
            {
                "id": r[0], "rule_name": r[1], "action_type": r[2],
                "target": r[3], "message": r[4], "timestamp": r[5], "status": r[6],
            }
            for r in rows
        ]


def render_template(template: str, context: dict) -> str:
    """Render a message template with {variable} placeholders."""
    def replacer(match):
        key = match.group(1)
        return str(context.get(key, f"{{{key}}}"))
    return re.sub(r"\{(\w+)\}", replacer, template)


def fire_action(rule_name: str, action: Action, context: dict, history: ActionHistory, dry_run: bool = False) -> str:
    """
    Execute an action. Returns the rendered message.
    In dry_run mode, logs but doesn't execute side effects.
    """
    rendered = render_template(action.template, context)
    status = "dry_run" if dry_run else "fired"

    if action.action_type == "notify":
        # In production, this would send to iMessage/Slack/etc via OpenClaw
        if not dry_run:
            print(f"[NOTIFY] → {action.target or 'default'}: {rendered}")
    elif action.action_type == "escalate":
        if not dry_run:
            print(f"[ESCALATE] ⚠️ {action.target or 'default'}: {rendered}")
    elif action.action_type == "execute":
        if action.require_approval:
            status = "pending_approval"
            if not dry_run:
                print(f"[EXECUTE/PENDING] 🔒 Needs approval: {rendered}")
        else:
            if not dry_run:
                print(f"[EXECUTE] ⚡ {rendered}")
    elif action.action_type == "draft":
        if not dry_run:
            print(f"[DRAFT] 📝 {rendered}")
    elif action.action_type == "log":
        if not dry_run:
            print(f"[LOG] 📋 {rendered}")
    else:
        if not dry_run:
            print(f"[{action.action_type.upper()}] {rendered}")

    history.record(rule_name, action, rendered, context, status)
    return rendered
