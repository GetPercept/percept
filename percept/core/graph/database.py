"""SQLite-backed graph database with FTS5 and temporal support."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from .models import Node, Edge, _now


class GraphDB:
    """Graph database using SQLite adjacency list pattern."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES nodes(id),
                target_id TEXT NOT NULL REFERENCES nodes(id),
                type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                valid_from TEXT,
                valid_until TEXT,
                source TEXT DEFAULT ''
            );

            -- Indexes for fast traversal
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
            CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
            CREATE INDEX IF NOT EXISTS idx_edges_temporal ON edges(valid_from, valid_until);

            -- FTS5 for full-text search on node names and properties
            CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                name, properties, content=nodes, content_rowid=rowid
            );

            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
                INSERT INTO nodes_fts(rowid, name, properties)
                VALUES (new.rowid, new.name, new.properties);
            END;

            CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
                INSERT INTO nodes_fts(nodes_fts, rowid, name, properties)
                VALUES ('delete', old.rowid, old.name, old.properties);
            END;

            CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
                INSERT INTO nodes_fts(nodes_fts, rowid, name, properties)
                VALUES ('delete', old.rowid, old.name, old.properties);
                INSERT INTO nodes_fts(rowid, name, properties)
                VALUES (new.rowid, new.name, new.properties);
            END;
        """)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ── Node operations ──

    def add_node(self, node: Node) -> Node:
        """Insert a node. Returns the node (with ID)."""
        self.conn.execute(
            "INSERT OR REPLACE INTO nodes (id, type, name, properties, created_at, updated_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (node.id, node.type, node.name,
             json.dumps(node.properties), node.created_at, node.updated_at, node.source)
        )
        self.conn.commit()
        return node

    def get_node(self, node_id: str) -> Optional[Node]:
        row = self.conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return Node.from_row(dict(row)) if row else None

    def find_node(self, name: str, node_type: Optional[str] = None) -> Optional[Node]:
        """Find node by exact name (case-insensitive), optionally filtered by type."""
        if node_type:
            row = self.conn.execute(
                "SELECT * FROM nodes WHERE LOWER(name) = LOWER(?) AND type = ? LIMIT 1",
                (name, node_type)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM nodes WHERE LOWER(name) = LOWER(?) LIMIT 1", (name,)
            ).fetchone()
        return Node.from_row(dict(row)) if row else None

    def find_or_create_node(self, name: str, node_type: str, properties: dict = None,
                            source: str = "") -> Node:
        """Find existing node by name+type or create new one."""
        existing = self.find_node(name, node_type)
        if existing:
            # Merge properties
            if properties:
                existing.properties.update(properties)
                existing.updated_at = _now()
                self.conn.execute(
                    "UPDATE nodes SET properties = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(existing.properties), existing.updated_at, existing.id)
                )
                self.conn.commit()
            return existing
        node = Node(type=node_type, name=name, properties=properties or {}, source=source)
        return self.add_node(node)

    def search_nodes(self, query: str, node_type: Optional[str] = None, limit: int = 50) -> list[Node]:
        """Full-text search across nodes."""
        if node_type:
            rows = self.conn.execute(
                "SELECT n.* FROM nodes n JOIN nodes_fts f ON n.rowid = f.rowid "
                "WHERE nodes_fts MATCH ? AND n.type = ? LIMIT ?",
                (query, node_type, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT n.* FROM nodes n JOIN nodes_fts f ON n.rowid = f.rowid "
                "WHERE nodes_fts MATCH ? LIMIT ?",
                (query, limit)
            ).fetchall()
        return [Node.from_row(dict(r)) for r in rows]

    def list_nodes(self, node_type: Optional[str] = None, limit: int = 100) -> list[Node]:
        if node_type:
            rows = self.conn.execute(
                "SELECT * FROM nodes WHERE type = ? ORDER BY name LIMIT ?",
                (node_type, limit)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM nodes ORDER BY type, name LIMIT ?", (limit,)
            ).fetchall()
        return [Node.from_row(dict(r)) for r in rows]

    # ── Edge operations ──

    def add_edge(self, edge: Edge) -> Edge:
        """Insert an edge. Returns the edge."""
        self.conn.execute(
            "INSERT OR REPLACE INTO edges "
            "(id, source_id, target_id, type, properties, created_at, updated_at, valid_from, valid_until, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (edge.id, edge.source_id, edge.target_id, edge.type,
             json.dumps(edge.properties), edge.created_at, edge.updated_at,
             edge.valid_from, edge.valid_until, edge.source)
        )
        self.conn.commit()
        return edge

    def find_edge(self, source_id: str, target_id: str, edge_type: str) -> Optional[Edge]:
        row = self.conn.execute(
            "SELECT * FROM edges WHERE source_id = ? AND target_id = ? AND type = ? LIMIT 1",
            (source_id, target_id, edge_type)
        ).fetchone()
        return Edge.from_row(dict(row)) if row else None

    def find_or_create_edge(self, source_id: str, target_id: str, edge_type: str,
                            properties: dict = None, source: str = "",
                            valid_from: str = None, valid_until: str = None) -> Edge:
        existing = self.find_edge(source_id, target_id, edge_type)
        if existing:
            if properties:
                existing.properties.update(properties)
                existing.updated_at = _now()
                self.conn.execute(
                    "UPDATE edges SET properties = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(existing.properties), existing.updated_at, existing.id)
                )
                self.conn.commit()
            return existing
        edge = Edge(
            source_id=source_id, target_id=target_id, type=edge_type,
            properties=properties or {}, source=source,
            valid_from=valid_from, valid_until=valid_until,
        )
        return self.add_edge(edge)

    # ── Graph traversal ──

    def neighbors(self, node_id: str, edge_type: Optional[str] = None,
                  direction: str = "both") -> list[tuple[Edge, Node]]:
        """Get all neighbors of a node. Returns (edge, neighbor_node) pairs."""
        results = []
        if direction in ("out", "both"):
            q = "SELECT e.*, n.* FROM edges e JOIN nodes n ON e.target_id = n.id WHERE e.source_id = ?"
            params = [node_id]
            if edge_type:
                q += " AND e.type = ?"
                params.append(edge_type)
            for row in self.conn.execute(q, params).fetchall():
                d = dict(row)
                edge = Edge.from_row({k: d[k] for k in Edge.__dataclass_fields__})
                # Node columns come after edge columns
                node_keys = list(Node.__dataclass_fields__.keys())
                # Rebuild from raw query — need proper column mapping
                edge_data = {
                    "id": d["id"], "source_id": d["source_id"], "target_id": d["target_id"],
                    "type": d["type"], "properties": d["properties"],
                    "created_at": d["created_at"], "updated_at": d["updated_at"],
                    "valid_from": d["valid_from"], "valid_until": d["valid_until"],
                    "source": d["source"],
                }
                edge = Edge.from_row(edge_data)
                results.append((edge, None))  # Will fix with proper join below

        # Simpler approach: separate queries
        results = []
        if direction in ("out", "both"):
            q = "SELECT * FROM edges WHERE source_id = ?"
            params = [node_id]
            if edge_type:
                q += " AND type = ?"
                params.append(edge_type)
            for erow in self.conn.execute(q, params).fetchall():
                e = Edge.from_row(dict(erow))
                n = self.get_node(e.target_id)
                if n:
                    results.append((e, n))

        if direction in ("in", "both"):
            q = "SELECT * FROM edges WHERE target_id = ?"
            params = [node_id]
            if edge_type:
                q += " AND type = ?"
                params.append(edge_type)
            for erow in self.conn.execute(q, params).fetchall():
                e = Edge.from_row(dict(erow))
                n = self.get_node(e.source_id)
                if n:
                    results.append((e, n))

        return results

    def shortest_path(self, start_name: str, end_name: str, max_depth: int = 6) -> list[tuple]:
        """BFS shortest path between two nodes (by name). Returns list of (node, edge, node) triples."""
        start = self.find_node(start_name)
        end = self.find_node(end_name)
        if not start or not end:
            return []

        from collections import deque
        visited = {start.id}
        queue = deque([(start.id, [])])  # (current_node_id, path_so_far)

        while queue:
            current_id, path = queue.popleft()
            if current_id == end.id:
                return path

            for edge, neighbor in self.neighbors(current_id):
                if neighbor and neighbor.id not in visited:
                    visited.add(neighbor.id)
                    current_node = self.get_node(current_id)
                    new_path = path + [(current_node, edge, neighbor)]
                    if neighbor.id == end.id:
                        return new_path
                    queue.append((neighbor.id, new_path))

        return []

    # ── Stats ──

    def stats(self) -> dict:
        node_count = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        type_counts = {}
        for row in self.conn.execute("SELECT type, COUNT(*) as cnt FROM nodes GROUP BY type ORDER BY cnt DESC"):
            type_counts[row["type"]] = row["cnt"]
        edge_type_counts = {}
        for row in self.conn.execute("SELECT type, COUNT(*) as cnt FROM edges GROUP BY type ORDER BY cnt DESC"):
            edge_type_counts[row["type"]] = row["cnt"]

        density = 0.0
        if node_count > 1:
            max_edges = node_count * (node_count - 1)
            density = edge_count / max_edges

        return {
            "nodes": node_count,
            "edges": edge_count,
            "density": round(density, 6),
            "node_types": type_counts,
            "edge_types": edge_type_counts,
        }

    # ── Export ──

    def export_json(self) -> dict:
        nodes = [Node.from_row(dict(r)) for r in
                 self.conn.execute("SELECT * FROM nodes").fetchall()]
        edges = [Edge.from_row(dict(r)) for r in
                 self.conn.execute("SELECT * FROM edges").fetchall()]
        return {
            "nodes": [{"id": n.id, "type": n.type, "name": n.name,
                       "properties": n.properties, "source": n.source} for n in nodes],
            "edges": [{"id": e.id, "source": e.source_id, "target": e.target_id,
                       "type": e.type, "properties": e.properties,
                       "valid_from": e.valid_from, "valid_until": e.valid_until} for e in edges],
        }

    def clear(self):
        """Drop all data."""
        self.conn.execute("DELETE FROM edges")
        self.conn.execute("DELETE FROM nodes")
        self.conn.commit()
