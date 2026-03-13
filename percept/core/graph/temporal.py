"""Temporal queries for the knowledge graph."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from .database import GraphDB
from .models import Node, Edge


class TemporalQuery:
    """Time-based queries over the graph."""

    def __init__(self, db: GraphDB):
        self.db = db

    def graph_at(self, date: str) -> list[Edge]:
        """Get all edges valid at a specific date (YYYY-MM-DD or ISO datetime)."""
        rows = self.db.conn.execute(
            """SELECT * FROM edges
               WHERE (valid_from IS NULL OR valid_from <= ?)
                 AND (valid_until IS NULL OR valid_until >= ?)""",
            (date, date)
        ).fetchall()
        return [Edge.from_row(dict(r)) for r in rows]

    def timeline(self, entity_name: str, days: int = 30) -> list[dict]:
        """Get temporal view of an entity — all edges created/modified in the last N days."""
        node = self.db.find_node(entity_name)
        if not node:
            return []

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = self.db.conn.execute(
            """SELECT e.*, n.name as other_name, n.type as other_type FROM edges e
               JOIN nodes n ON (
                   CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END = n.id
               )
               WHERE (e.source_id = ? OR e.target_id = ?)
                 AND e.created_at >= ?
               ORDER BY e.created_at DESC""",
            (node.id, node.id, node.id, cutoff)
        ).fetchall()

        events = []
        for r in rows:
            d = dict(r)
            events.append({
                "date": d["created_at"][:10],
                "edge_type": d["type"],
                "related": d["other_name"],
                "related_type": d["other_type"],
                "properties": d["properties"],
            })
        return events

    def recent_edges(self, days: int = 7, limit: int = 50) -> list[Edge]:
        """Get most recently created/updated edges."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        rows = self.db.conn.execute(
            "SELECT * FROM edges WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
            (cutoff, limit)
        ).fetchall()
        return [Edge.from_row(dict(r)) for r in rows]

    def decay_score(self, edge: Edge, half_life_days: float = 30.0) -> float:
        """Calculate relevance decay score (1.0 = brand new, approaches 0 over time)."""
        import math
        try:
            created = datetime.fromisoformat(edge.created_at)
            age_days = (datetime.utcnow() - created).total_seconds() / 86400
            return math.exp(-0.693 * age_days / half_life_days)
        except (ValueError, TypeError):
            return 0.5
