"""Base ingester class."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from percept.core.graph.database import GraphDB
from percept.core.graph.models import Node, Edge


class BaseIngester:
    """Base class for file ingesters."""

    source_name: str = "unknown"

    def __init__(self, db: GraphDB):
        self.db = db
        self._stats = {"nodes_created": 0, "edges_created": 0}

    def ingest(self, path: Path) -> dict:
        """Ingest a file. Override in subclasses."""
        raise NotImplementedError

    def add_node(self, name: str, node_type: str, properties: dict = None) -> Node:
        node = self.db.find_or_create_node(name, node_type, properties or {}, source=self.source_name)
        self._stats["nodes_created"] += 1
        return node

    def add_edge(self, source: Node, target: Node, edge_type: str,
                 properties: dict = None, valid_from: str = None, valid_until: str = None) -> Edge:
        edge = self.db.find_or_create_edge(
            source.id, target.id, edge_type,
            properties=properties or {}, source=self.source_name,
            valid_from=valid_from, valid_until=valid_until,
        )
        self._stats["edges_created"] += 1
        return edge

    def read_file(self, path: Path) -> str:
        """Read a file, return contents or empty string."""
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError):
            return ""

    @property
    def stats(self) -> dict:
        return {**self._stats, "source": self.source_name}
