"""lessons.md ingester — extracts lesson/learning nodes."""
from __future__ import annotations

import re
from pathlib import Path

from .base import BaseIngester


class LessonsIngester(BaseIngester):
    source_name = "lessons.md"

    def ingest(self, path: Path) -> dict:
        content = self.read_file(path)
        if not content:
            return self.stats

        jarvis = self.add_node("Jarvis", "Person", {"role": "AI Assistant"})
        lessons = self._parse_lessons(content)

        for lesson in lessons:
            concept = self.add_node(lesson["title"], "Concept", {
                "lesson": True,
                "problem": lesson.get("problem", ""),
                "prevention": lesson.get("prevention", ""),
                "rule": lesson.get("rule", ""),
                "date": lesson.get("date", ""),
            })
            self.add_edge(jarvis, concept, "LEARNED", {
                "date": lesson.get("date", ""),
            })

        return self.stats

    def _parse_lessons(self, content: str) -> list[dict]:
        lessons = []
        blocks = re.split(r"\n## ", content)

        for block in blocks[1:]:
            lines = block.strip().split("\n")
            if not lines:
                continue

            title_line = lines[0].strip()
            # Extract date
            date_match = re.search(r"\(([^)]+\d{4})\)", title_line)
            date = date_match.group(1) if date_match else ""
            title = re.sub(r"\s*\([^)]+\)\s*$", "", title_line).strip()

            body = "\n".join(lines[1:])
            lesson = {"title": title, "date": date}

            # Extract problem/prevention/rule
            for pat, key in [
                (r"\*\*Problem:\*\*\s*(.+?)(?=\n\*\*|\Z)", "problem"),
                (r"\*\*Prevention:\*\*\s*(.+?)(?=\n\*\*|\Z)", "prevention"),
                (r"\*\*Rule[:\s]*\*\*\s*(.+?)(?=\n\*\*|\Z)", "rule"),
                (r"\*\*Cause:\*\*\s*(.+?)(?=\n\*\*|\Z)", "cause"),
                (r"\*\*Fix:\*\*\s*(.+?)(?=\n\*\*|\Z)", "fix"),
            ]:
                m = re.search(pat, body, re.DOTALL)
                if m:
                    lesson[key] = m.group(1).strip()

            # If no structured fields, use the body as content
            if not any(k in lesson for k in ("problem", "prevention", "rule", "cause")):
                # Check for bullet-point rules
                rules = re.findall(r"[-•]\s*\*\*(.+?)\*\*\s*[-—]\s*(.+)", body)
                if rules:
                    lesson["rules"] = [{"rule": r[0], "detail": r[1]} for r in rules]
                else:
                    lesson["content"] = body[:500]

            lessons.append(lesson)

        return lessons
