"""Data models for the knowledge graph."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Any


def _now() -> str:
    return datetime.utcnow().isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# Valid node types
NODE_TYPES = {
    "Person", "Organization", "Project", "Tool", "Event",
    "Document", "Concept", "Signal", "Health",
}

# Valid edge types
EDGE_TYPES = {
    "WORKS_AT", "OWNS", "COLLABORATES_WITH", "USES", "RELATED_TO",
    "DEPENDS_ON", "MENTIONED_IN", "DECIDED", "LEARNED", "SIGNALS",
    "MEASURED", "BUILT", "INVESTED_IN", "DEPLOYED_ON", "HAS_TOKEN",
    "TRADES_ON", "MEMBER_OF",
}


@dataclass
class Node:
    id: str = field(default_factory=_uuid)
    type: str = ""          # Person, Organization, Project, etc.
    name: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    source: str = ""        # Which file/ingester created this

    def to_dict(self) -> dict:
        d = asdict(self)
        d["properties"] = json.dumps(d["properties"])
        return d

    @classmethod
    def from_row(cls, row: dict) -> Node:
        props = row.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)
        return cls(
            id=row["id"],
            type=row["type"],
            name=row["name"],
            properties=props,
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
            source=row.get("source", ""),
        )

    def __str__(self) -> str:
        return f"[{self.type}] {self.name}"


@dataclass
class Edge:
    id: str = field(default_factory=_uuid)
    source_id: str = ""     # From node
    target_id: str = ""     # To node
    type: str = ""          # WORKS_AT, OWNS, etc.
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    source: str = ""        # Which file/ingester created this

    def to_dict(self) -> dict:
        d = asdict(self)
        d["properties"] = json.dumps(d["properties"])
        return d

    @classmethod
    def from_row(cls, row: dict) -> Edge:
        props = row.get("properties", "{}")
        if isinstance(props, str):
            props = json.loads(props)
        return cls(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            type=row["type"],
            properties=props,
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
            valid_from=row.get("valid_from"),
            valid_until=row.get("valid_until"),
            source=row.get("source", ""),
        )

    def __str__(self) -> str:
        return f"--[{self.type}]-->"
