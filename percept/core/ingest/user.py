"""USER.md ingester — extracts person and organization nodes."""
from __future__ import annotations

import re
from pathlib import Path

from .base import BaseIngester


class UserIngester(BaseIngester):
    source_name = "user.md"

    def ingest(self, path: Path) -> dict:
        content = self.read_file(path)
        if not content:
            return self.stats

        # Extract David as primary person
        name = self._extract_field(content, r"\*\*Name:\*\*\s*(.+)")
        role = self._extract_field(content, r"\*\*Role:\*\*\s*(.+)")
        email = self._extract_field(content, r"\*\*Email:\*\*\s*(.+)")
        phone = self._extract_field(content, r"\*\*Phone:\*\*\s*(.+)")
        tz = self._extract_field(content, r"\*\*Timezone:\*\*\s*(.+)")
        pronouns = self._extract_field(content, r"\*\*Pronouns:\*\*\s*(.+)")

        if name:
            david = self.add_node(name, "Person", {
                "role": role or "",
                "email": email or "",
                "phone": phone or "",
                "timezone": tz or "",
                "pronouns": pronouns or "",
            })

            # Extract organizations
            orgs = self._extract_orgs(content)
            for org_name, org_props in orgs:
                org = self.add_node(org_name, "Organization", org_props)
                self.add_edge(david, org, "WORKS_AT" if org_name == "VectorCare" else "OWNS")

        return self.stats

    def _extract_field(self, content: str, pattern: str) -> str | None:
        m = re.search(pattern, content)
        return m.group(1).strip() if m else None

    def _extract_orgs(self, content: str) -> list[tuple[str, dict]]:
        orgs = []
        # VectorCare
        if "VectorCare" in content:
            orgs.append(("VectorCare", {
                "type": "B2B healthcare logistics",
                "url": "vectorcare.com",
                "facilities": "2,500+",
            }))
        # HealthSafe
        if "HealthSafe" in content:
            orgs.append(("HealthSafe", {
                "type": "B2C consumer health records",
                "url": "healthsafe.io",
            }))
        # ClawDoor
        if "ClawDoor" in content:
            orgs.append(("ClawDoor", {
                "type": "Agent Neighborhood Protocol",
                "url": "clawdoor.com",
                "token": "$DOOR on Base",
            }))
        # Spendabot
        if "Spendabot" in content:
            orgs.append(("Spendabot", {
                "type": "Financial infrastructure for AI",
                "url": "spendabot.com",
            }))
        return orgs
