"""Base classes and schemas for the Percept Connector SDK."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional


class EntityType(str, Enum):
    """Standard entity types in the Percept knowledge graph."""
    PERSON = "person"
    DOCUMENT = "document"
    PROJECT = "project"
    CONCEPT = "concept"
    CHANNEL = "channel"
    THREAD = "thread"
    EVENT = "event"


@dataclass
class EntitySchema:
    """Describes an entity type a connector can produce."""
    entity_type: EntityType
    name: str                          # e.g. "Email", "PR", "Message"
    description: str
    properties: list[str] = field(default_factory=list)  # expected property keys


@dataclass
class Node:
    """A node in the knowledge graph."""
    id: str
    entity_type: EntityType
    name: str
    properties: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        now = datetime.now(timezone.utc)
        if self.created_at is None:
            self.created_at = now
        if self.updated_at is None:
            self.updated_at = now


@dataclass
class Edge:
    """An edge (relationship) in the knowledge graph."""
    id: str = ""
    source_id: str = ""
    target_id: str = ""
    relation: str = ""                 # e.g. "SENT_TO", "AUTHORED", "POSTED_IN"
    properties: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


@dataclass
class GraphEvent:
    """A single graph mutation from a connector."""
    event_type: str              # "node_upsert", "edge_upsert", "node_delete"
    source: str                  # Connector name
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    node: Optional[Node] = None
    edge: Optional[Edge] = None
    confidence: float = 1.0      # 0-1
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
        }
        if self.node:
            d["node"] = {
                "id": self.node.id,
                "entity_type": self.node.entity_type.value,
                "name": self.node.name,
                "properties": self.node.properties,
            }
        if self.edge:
            d["edge"] = {
                "id": self.edge.id,
                "source_id": self.edge.source_id,
                "target_id": self.edge.target_id,
                "relation": self.edge.relation,
                "weight": self.edge.weight,
            }
        return d


@dataclass
class ConnectorMetadata:
    """Metadata about a connector for the registry."""
    name: str
    version: str
    auth_type: str
    description: str = ""
    entity_types: list[str] = field(default_factory=list)
    last_sync: Optional[datetime] = None
    healthy: bool = True
    error: Optional[str] = None


class BaseConnector(ABC):
    """Base class all connectors must inherit from."""

    name: str = ""
    version: str = "0.1.0"
    auth_type: str = "none"           # "oauth2", "api_key", "token", "none"
    description: str = ""

    _authenticated: bool = False
    _mock_mode: bool = False
    _last_sync: Optional[datetime] = None

    def __init__(self, mock: bool = False):
        self._mock_mode = mock

    # --- Required methods ---

    @abstractmethod
    def authenticate(self, credentials: dict) -> bool:
        """Establish connection with credentials. Return True on success."""
        ...

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify the connection works."""
        ...

    @abstractmethod
    def discover(self) -> list[EntitySchema]:
        """Return what entity types this connector can produce."""
        ...

    @abstractmethod
    def pull(self, since: datetime | None = None) -> list[GraphEvent]:
        """Pull new data since last sync. Returns graph events."""
        ...

    # --- Optional methods ---

    def stream(self, callback: Callable[[GraphEvent], None]) -> None:
        """Optional: real-time streaming via webhooks/websockets."""
        raise NotImplementedError(f"{self.name} does not support streaming")

    # --- Built-in methods ---

    def get_metadata(self) -> ConnectorMetadata:
        """Return connector info for registry."""
        return ConnectorMetadata(
            name=self.name,
            version=self.version,
            auth_type=self.auth_type,
            description=self.description,
            entity_types=[s.name for s in self.discover()],
            last_sync=self._last_sync,
            healthy=self._authenticated or self._mock_mode,
        )

    def sync(self, since: datetime | None = None) -> list[GraphEvent]:
        """Pull + update last_sync timestamp."""
        events = self.pull(since=since or self._last_sync)
        self._last_sync = datetime.now(timezone.utc)
        return events

    # --- Helpers ---

    def _make_node_event(
        self,
        node: Node,
        confidence: float = 1.0,
        raw: dict | None = None,
    ) -> GraphEvent:
        return GraphEvent(
            event_type="node_upsert",
            source=self.name,
            node=node,
            confidence=confidence,
            raw_data=raw or {},
        )

    def _make_edge_event(
        self,
        edge: Edge,
        confidence: float = 1.0,
        raw: dict | None = None,
    ) -> GraphEvent:
        return GraphEvent(
            event_type="edge_upsert",
            source=self.name,
            edge=edge,
            confidence=confidence,
            raw_data=raw or {},
        )
