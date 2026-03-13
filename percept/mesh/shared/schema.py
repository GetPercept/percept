"""Shared node/edge type definitions for the team graph."""
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
import json


@dataclass
class TeamNode:
    """A node in the team graph (project, PR, issue, blocker, etc.)."""
    id: str                     # Globally unique (uuid)
    node_type: str              # e.g. "Project", "PR", "Issue", "Blocker"
    name: str                   # Human-readable name
    owner_id: str               # Member who created/owns this node
    properties: dict = field(default_factory=dict)  # Arbitrary metadata
    created_at: str = ""        # ISO timestamp
    updated_at: str = ""        # ISO timestamp

    def __post_init__(self):
        now = datetime.utcnow().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        d = asdict(self)
        if isinstance(d["properties"], str):
            d["properties"] = json.loads(d["properties"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TeamNode":
        props = d.get("properties", {})
        if isinstance(props, str):
            props = json.loads(props)
        return cls(
            id=d["id"],
            node_type=d["node_type"],
            name=d["name"],
            owner_id=d["owner_id"],
            properties=props,
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


@dataclass
class TeamEdge:
    """A directed edge between two nodes."""
    id: str
    source_id: str
    target_id: str
    edge_type: str              # e.g. "blocks", "reviews", "owns", "relates_to"
    owner_id: str
    properties: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        if isinstance(d["properties"], str):
            d["properties"] = json.loads(d["properties"])
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TeamEdge":
        props = d.get("properties", {})
        if isinstance(props, str):
            props = json.loads(props)
        return cls(
            id=d["id"],
            source_id=d["source_id"],
            target_id=d["target_id"],
            edge_type=d["edge_type"],
            owner_id=d["owner_id"],
            properties=props,
            created_at=d.get("created_at", ""),
        )


@dataclass
class SyncEvent:
    """A batch of nodes/edges pushed from an agent."""
    member_id: str
    nodes: list = field(default_factory=list)   # List[TeamNode dicts]
    edges: list = field(default_factory=list)   # List[TeamEdge dicts]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()
