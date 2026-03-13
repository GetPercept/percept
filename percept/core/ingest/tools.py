"""TOOLS.md ingester — extracts tool nodes and usage edges."""
from __future__ import annotations

import re
from pathlib import Path

from .base import BaseIngester


class ToolsIngester(BaseIngester):
    source_name = "tools.md"

    def ingest(self, path: Path) -> dict:
        content = self.read_file(path)
        if not content:
            return self.stats

        # Get or create David as the user of these tools
        david = self.add_node("David", "Person")

        sections = self._parse_sections(content)
        for section_name, section_content in sections:
            tool = self._create_tool(section_name, section_content)
            if tool:
                self.add_edge(david, tool, "USES")

        return self.stats

    def _parse_sections(self, content: str) -> list[tuple[str, str]]:
        """Parse ## sections from TOOLS.md."""
        sections = []
        current_name = None
        current_lines = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_name:
                    sections.append((current_name, "\n".join(current_lines)))
                current_name = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_name:
            sections.append((current_name, "\n".join(current_lines)))

        return sections

    def _create_tool(self, name: str, content: str) -> "Node | None":
        # Skip non-tool sections
        skip = {"Old Workspace", "Bookmarked Tools", "LinkedIn Accounts", "LinkedIn Lessons",
                "Reddit Lessons", "Polymarket Bot Lessons"}
        if name in skip:
            return None

        props = {}
        # Extract URLs
        urls = re.findall(r"https?://[^\s\)]+", content)
        if urls:
            props["url"] = urls[0]

        # Extract account/email
        acct = re.search(r"\*\*Account:\*\*\s*(.+)", content)
        if acct:
            props["account"] = acct.group(1).strip()

        # Extract paths
        path_match = re.search(r"\*\*(?:Path|Workspace|CLI):\*\*\s*(.+)", content)
        if path_match:
            props["path"] = path_match.group(1).strip()

        # Determine tool type
        tool_type = "tool"
        if any(w in name.lower() for w in ["bot", "scanner", "robinhood", "polymarket"]):
            tool_type = "trading"
        elif any(w in name.lower() for w in ["discord", "imessage", "linkedin", "x (", "twitter"]):
            tool_type = "communication"
        elif any(w in name.lower() for w in ["browser", "chrome"]):
            tool_type = "browser"
        elif any(w in name.lower() for w in ["github", "railway"]):
            tool_type = "devops"
        elif any(w in name.lower() for w in ["token", "clawnch", "polyclaw"]):
            tool_type = "crypto"
        elif any(w in name.lower() for w in ["google", "gog"]):
            tool_type = "productivity"

        props["tool_type"] = tool_type

        return self.add_node(name, "Tool", props)
