"""Daily memory files ingester — extracts events and temporal data from memory/YYYY-MM-DD.md."""
from __future__ import annotations

import re
from pathlib import Path

from .base import BaseIngester


class DailyIngester(BaseIngester):
    source_name = "daily"

    def ingest(self, path: Path) -> dict:
        """Ingest a directory of daily files."""
        if not path.is_dir():
            return self.stats

        daily_files = sorted(path.glob("2026-*.md"))
        for f in daily_files:
            self._ingest_file(f)

        return self.stats

    def _ingest_file(self, path: Path):
        content = self.read_file(path)
        if not content:
            return

        # Extract date from filename
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        if not date_match:
            return
        date = date_match.group(1)

        # Create a Document node for this daily file
        doc = self.add_node(f"Daily: {date}", "Document", {
            "path": str(path),
            "type": "daily_log",
            "date": date,
        })

        # Extract mentioned entities and create MENTIONED_IN edges
        self._extract_mentions(content, doc, date)

        # Extract events (lines with timestamps or significant actions)
        self._extract_events(content, doc, date)

    def _extract_mentions(self, content: str, doc, date: str):
        """Find known entity names mentioned in the daily file."""
        known_entities = [
            "David", "VectorCare", "HealthSafe", "ClawDoor", "Spendabot",
            "SafeCollect", "Polymarket", "Robinhood", "Percept", "Polyclaw",
            "Stripe", "Railway", "Reddit", "LinkedIn", "Discord",
            "Ilya", "Butler", "OpenClaw",
        ]
        content_lower = content.lower()
        for entity_name in known_entities:
            if entity_name.lower() in content_lower:
                existing = self.db.find_node(entity_name)
                if existing:
                    self.add_edge(existing, doc, "MENTIONED_IN", {"date": date}, valid_from=date)

    def _extract_events(self, content: str, doc, date: str):
        """Extract significant events from daily logs."""
        # Look for header-level events
        event_patterns = [
            (r"(?:deployed|launched|shipped|released)\s+(.+?)(?:\n|$)", "deployment"),
            (r"(?:bought|sold|traded)\s+(.+?)(?:\n|$)", "trade"),
            (r"(?:decision|decided|chose)\s*:?\s*(.+?)(?:\n|$)", "decision"),
            (r"(?:bug|error|fix|broke)\s*:?\s*(.+?)(?:\n|$)", "incident"),
        ]

        for pattern, event_type in event_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches[:3]:  # Limit per type
                event_name = match.strip()[:100]
                if len(event_name) > 10:  # Skip tiny matches
                    event = self.add_node(f"{date}: {event_name}", "Event", {
                        "type": event_type,
                        "date": date,
                        "detail": event_name,
                    })
                    self.add_edge(event, doc, "MENTIONED_IN", valid_from=date)
