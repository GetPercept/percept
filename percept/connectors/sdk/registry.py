"""Connector registry — manages installed connectors."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .base import BaseConnector, ConnectorMetadata, GraphEvent


STATE_FILE = Path.home() / ".config" / "percept-connectors" / "state.json"


class ConnectorRegistry:
    """Manages installed connectors."""

    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}
        self._state = self._load_state()

    # --- State persistence ---

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"last_sync": {}, "errors": {}}

    def _save_state(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self._state, indent=2, default=str))

    # --- Registry operations ---

    def register(self, connector: BaseConnector):
        """Register a connector instance."""
        self._connectors[connector.name] = connector
        # Restore last sync time from persisted state
        if connector.name in self._state.get("last_sync", {}):
            ts = self._state["last_sync"][connector.name]
            if ts:
                connector._last_sync = datetime.fromisoformat(ts)

    def list_connectors(self) -> list[ConnectorMetadata]:
        """Return metadata for all registered connectors."""
        results = []
        for c in self._connectors.values():
            meta = c.get_metadata()
            if c.name in self._state.get("errors", {}):
                meta.error = self._state["errors"][c.name]
                meta.healthy = False
            results.append(meta)
        return results

    def get_connector(self, name: str) -> BaseConnector:
        """Get a connector by name."""
        if name not in self._connectors:
            raise KeyError(f"Connector '{name}' not found. Available: {list(self._connectors.keys())}")
        return self._connectors[name]

    def sync_one(self, name: str, since: Optional[datetime] = None) -> list[GraphEvent]:
        """Sync a single connector."""
        connector = self.get_connector(name)
        try:
            events = connector.sync(since=since)
            self._state.setdefault("last_sync", {})[name] = datetime.now(timezone.utc).isoformat()
            self._state.get("errors", {}).pop(name, None)
            self._save_state()
            return events
        except Exception as e:
            self._state.setdefault("errors", {})[name] = str(e)
            self._save_state()
            raise

    def sync_all(self, since: Optional[datetime] = None) -> list[GraphEvent]:
        """Sync all connectors. Graceful degradation — failures don't stop others."""
        all_events: list[GraphEvent] = []
        errors: dict[str, str] = {}

        for name, connector in self._connectors.items():
            try:
                events = connector.sync(since=since)
                all_events.extend(events)
                self._state.setdefault("last_sync", {})[name] = datetime.now(timezone.utc).isoformat()
                self._state.get("errors", {}).pop(name, None)
            except Exception as e:
                errors[name] = str(e)
                self._state.setdefault("errors", {})[name] = str(e)

        self._save_state()

        if errors:
            err_summary = "; ".join(f"{k}: {v}" for k, v in errors.items())
            print(f"⚠️  Sync errors: {err_summary}")

        return all_events

    def status(self) -> dict:
        """Return status overview."""
        return {
            "connectors": len(self._connectors),
            "registered": list(self._connectors.keys()),
            "last_sync": self._state.get("last_sync", {}),
            "errors": self._state.get("errors", {}),
        }
