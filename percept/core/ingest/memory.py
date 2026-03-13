"""MEMORY.md ingester — extracts entities and relationships from long-term memory."""
from __future__ import annotations

import re
from pathlib import Path

from .base import BaseIngester


class MemoryIngester(BaseIngester):
    source_name = "memory.md"

    def ingest(self, path: Path) -> dict:
        content = self.read_file(path)
        if not content:
            return self.stats

        david = self.add_node("David", "Person")
        jarvis = self.add_node("Jarvis", "Person", {"role": "AI Assistant"})

        sections = self._parse_sections(content)
        for section_name, section_content in sections:
            self._process_section(section_name, section_content, david, jarvis)

        return self.stats

    def _parse_sections(self, content: str) -> list[tuple[str, str]]:
        sections = []
        current = None
        lines = []
        for line in content.split("\n"):
            if line.startswith("## ") or line.startswith("### "):
                if current:
                    sections.append((current, "\n".join(lines)))
                current = re.sub(r"^#+\s*", "", line).strip()
                lines = []
            else:
                lines.append(line)
        if current:
            sections.append((current, "\n".join(lines)))
        return sections

    def _process_section(self, name: str, content: str, david, jarvis):
        name_lower = name.lower()

        # Project sections
        if any(kw in name_lower for kw in ["safecollect", "healthsafe", "clawdoor", "polymarket",
                                            "polyclaw", "spendabot", "robinhood", "percept",
                                            "insider scanner", "claws memory"]):
            project_name = self._clean_project_name(name)
            props = self._extract_project_props(content)
            project = self.add_node(project_name, "Project", props)
            self.add_edge(david, project, "OWNS")

            # Extract related orgs/platforms
            self._extract_platforms(content, project)

        # Token holdings
        elif "token" in name_lower or "$" in name:
            self._process_tokens(content, david)

        # Strategy/learning sections
        elif any(kw in name_lower for kw in ["strategy", "learning", "lesson", "kelly"]):
            concept = self.add_node(name, "Concept", {"content": content[:500]})
            self.add_edge(jarvis, concept, "LEARNED")

        # People-related
        elif "about david" in name_lower:
            pass  # Already handled by user.md ingester

    def _clean_project_name(self, name: str) -> str:
        # Remove date annotations, emoji, etc.
        clean = re.sub(r"\s*[\(（].*?[\)）]", "", name)
        clean = re.sub(r"\s*—.*$", "", clean)
        clean = re.sub(r"\s*[-–].*$", "", clean)
        return clean.strip()

    def _extract_project_props(self, content: str) -> dict:
        props = {}
        # URLs
        urls = re.findall(r"https?://[^\s\)]+", content)
        if urls:
            props["urls"] = urls[:5]
        # Status
        status = re.search(r"\*\*Status:\*\*\s*(.+)", content)
        if status:
            props["status"] = status.group(1).strip()
        # Wallet
        wallet = re.search(r"\*\*Wallet:\*\*\s*(0x[a-fA-F0-9]+)", content)
        if wallet:
            props["wallet"] = wallet.group(1)
        # Balance
        balance = re.search(r"\*\*Balance:\*\*\s*(.+)", content)
        if balance:
            props["balance"] = balance.group(1).strip()
        return props

    def _extract_platforms(self, content: str, project):
        """Extract platform mentions and create relationships."""
        platforms = {
            "Railway": "Organization",
            "Polygon": "Organization",
            "Base": "Organization",
            "Stripe": "Organization",
            "Reddit": "Organization",
            "Polymarket": "Organization",
            "Robinhood": "Organization",
            "Supabase": "Organization",
        }
        for platform, ptype in platforms.items():
            if platform.lower() in content.lower():
                plat_node = self.add_node(platform, ptype)
                self.add_edge(project, plat_node, "DEPLOYED_ON")

    def _process_tokens(self, content: str, david):
        """Extract token nodes."""
        # $DOOR, $JARV etc
        tokens = re.findall(r"\$([A-Z]+)", content)
        for token in set(tokens):
            addr_match = re.search(rf"\${token}.*?(0x[a-fA-F0-9]{{40}})", content)
            props = {}
            if addr_match:
                props["address"] = addr_match.group(1)
            token_node = self.add_node(f"${token}", "Project", {
                "type": "token",
                "chain": "Base",
                **props,
            })
            self.add_edge(david, token_node, "HAS_TOKEN")
