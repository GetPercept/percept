"""Simple interval-based sync scheduler."""

from __future__ import annotations

import time
import signal
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from .registry import ConnectorRegistry
from .base import GraphEvent


class SyncScheduler:
    """Interval-based sync scheduler for connectors."""

    def __init__(
        self,
        registry: ConnectorRegistry,
        interval_seconds: int = 300,
        on_events: Optional[Callable[[list[GraphEvent]], None]] = None,
    ):
        self.registry = registry
        self.interval = interval_seconds
        self.on_events = on_events or self._default_handler
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def _default_handler(events: list[GraphEvent]):
        if events:
            print(f"📥 Received {len(events)} graph events")
            for e in events[:5]:
                kind = "node" if e.node else "edge"
                name = e.node.name if e.node else (e.edge.relation if e.edge else "?")
                print(f"   {e.event_type}: {kind} — {name} (from {e.source})")
            if len(events) > 5:
                print(f"   ... and {len(events) - 5} more")

    def run_once(self, connector_name: Optional[str] = None) -> list[GraphEvent]:
        """Run a single sync cycle."""
        if connector_name:
            return self.registry.sync_one(connector_name)
        return self.registry.sync_all()

    def start(self, connector_name: Optional[str] = None):
        """Start the scheduler loop (blocking)."""
        self._running = True
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        signal.signal(signal.SIGTERM, lambda *_: self.stop())

        target = connector_name or "all connectors"
        print(f"🔄 Scheduler started — syncing {target} every {self.interval}s")

        while self._running:
            try:
                events = self.run_once(connector_name)
                self.on_events(events)
            except Exception as e:
                print(f"❌ Sync error: {e}")

            # Sleep in small increments so we can stop quickly
            for _ in range(self.interval):
                if not self._running:
                    break
                time.sleep(1)

        print("🛑 Scheduler stopped")

    def start_background(self, connector_name: Optional[str] = None):
        """Start scheduler in a background thread."""
        self._thread = threading.Thread(
            target=self.start,
            args=(connector_name,),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Stop the scheduler."""
        self._running = False
