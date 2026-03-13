"""decisions.md ingester — extracts decision nodes with context and alternatives."""
from __future__ import annotations

import re
from pathlib import Path

from .base import BaseIngester


class DecisionsIngester(BaseIngester):
    source_name = "decisions.md"

    def ingest(self, path: Path) -> dict:
        content = self.read_file(path)
        if not content:
            return self.stats

        david = self.add_node("David", "Person")
        decisions = self._parse_decisions(content)

        for decision in decisions:
            concept = self.add_node(decision["title"], "Concept", {
                "decision": True,
                "alternatives": decision.get("alternatives", ""),
                "why": decision.get("why", ""),
                "trade_offs": decision.get("trade_offs", ""),
                "date": decision.get("date", ""),
            })
            self.add_edge(david, concept, "DECIDED", {
                "date": decision.get("date", ""),
                "context": decision.get("why", "")[:200],
            }, valid_from=self._parse_date(decision.get("date", "")))

            # Link to mentioned projects/concepts
            self._link_mentions(decision, concept)

        return self.stats

    def _parse_decisions(self, content: str) -> list[dict]:
        decisions = []
        blocks = re.split(r"\n## ", content)

        for block in blocks[1:]:  # Skip header
            lines = block.strip().split("\n")
            if not lines:
                continue

            title_line = lines[0].strip()
            # Extract date from title
            date_match = re.search(r"\(([A-Z][a-z]+ \d+, \d{4})\)", title_line)
            date = date_match.group(1) if date_match else ""
            title = re.sub(r"\s*\([^)]+\)\s*$", "", title_line).strip()

            body = "\n".join(lines[1:])

            decision = {"title": title, "date": date}

            # Extract fields
            for field_name, key in [("Decision", "decision"), ("Alternatives", "alternatives"),
                                     ("Why", "why"), ("Trade-offs", "trade_offs"),
                                     ("Triggered by", "triggered_by")]:
                m = re.search(rf"\*\*{field_name}:\*\*\s*(.+?)(?=\n\*\*|\Z)", body, re.DOTALL)
                if m:
                    decision[key] = m.group(1).strip()

            decisions.append(decision)

        return decisions

    def _parse_date(self, date_str: str) -> str | None:
        """Convert 'Mar 11, 2026' to '2026-03-11'."""
        if not date_str:
            return None
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str, "%b %d, %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _link_mentions(self, decision: dict, concept_node):
        """Create RELATED_TO edges for mentioned projects."""
        full_text = " ".join(str(v) for v in decision.values())
        known_projects = ["Percept", "ClawDoor", "VectorCare", "HealthSafe", "Polymarket",
                          "Robinhood", "SafeCollect", "Spendabot", "Polyclaw"]
        for proj_name in known_projects:
            if proj_name.lower() in full_text.lower():
                proj = self.db.find_node(proj_name)
                if proj and proj.id != concept_node.id:
                    self.add_edge(concept_node, proj, "RELATED_TO")
