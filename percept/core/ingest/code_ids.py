"""vectorcare-code-identities.md ingester — extracts developer profiles."""
from __future__ import annotations

import re
from pathlib import Path

from .base import BaseIngester


class CodeIdsIngester(BaseIngester):
    source_name = "code_ids.md"

    def ingest(self, path: Path) -> dict:
        content = self.read_file(path)
        if not content:
            return self.stats

        vectorcare = self.add_node("VectorCare", "Organization")

        developers = self._parse_developers(content)
        for dev in developers:
            person = self.add_node(dev["name"], "Person", {
                "role": dev.get("role", ""),
                "github": dev.get("github", ""),
                "code_style": dev.get("style", ""),
                "values": dev.get("values", ""),
                "annoyances": dev.get("annoyances", ""),
            })
            self.add_edge(person, vectorcare, "WORKS_AT")

            # Tools they use
            for tool_name in dev.get("tools", []):
                tool = self.add_node(tool_name, "Tool", {"type": "dev_tool"})
                self.add_edge(person, tool, "USES")

        return self.stats

    def _parse_developers(self, content: str) -> list[dict]:
        devs = []
        blocks = re.split(r"\n## ", content)

        for block in blocks[1:]:
            lines = block.strip().split("\n")
            if not lines:
                continue

            header = lines[0].strip()
            body = "\n".join(lines[1:])

            # Skip non-person sections
            if "How to Write" in header:
                continue

            # Extract name and GitHub
            name_match = re.match(r"(.+?)\s*\(@(\w+)\)", header)
            if not name_match:
                continue

            dev = {
                "name": name_match.group(1).strip(),
                "github": name_match.group(2),
            }

            # Role
            role_match = re.search(r"\*\*Role:\*\*\s*(.+)", body)
            if role_match:
                dev["role"] = role_match.group(1).strip()

            # Extract "What He Values"
            values_match = re.search(r"What He Values\s*\n([\s\S]*?)(?=\n###|\Z)", body)
            if values_match:
                values = re.findall(r"[-•]\s*(.+)", values_match.group(1))
                dev["values"] = "; ".join(values)

            # What annoys
            annoy_match = re.search(r"What (?:He'd Flag|Annoys Him)\s*\n([\s\S]*?)(?=\n###|\n---|\Z)", body)
            if annoy_match:
                annoys = re.findall(r"[-•]\s*(.+)", annoy_match.group(1))
                dev["annoyances"] = "; ".join(annoys)

            # Code patterns as style summary
            style_match = re.search(r"Code Patterns\s*\n([\s\S]*?)(?=\n###|\Z)", body)
            if style_match:
                patterns = re.findall(r"\*\*(.+?)\.\*\*", style_match.group(1))
                dev["style"] = "; ".join(patterns[:5])

            # Tools mentioned
            tools = []
            if "DRF" in body or "Django" in body:
                tools.append("Django REST Framework")
            if "pytest" in body:
                tools.append("pytest")
            if "OpenSearch" in body:
                tools.append("OpenSearch")
            if "PostgreSQL" in body or "migration" in body.lower():
                tools.append("PostgreSQL")
            dev["tools"] = tools

            devs.append(dev)

        return devs
