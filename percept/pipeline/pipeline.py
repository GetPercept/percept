"""Percept Pipeline — orchestrates connector → KG → initiative flow."""

from __future__ import annotations

import sys
import json
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add parent paths for imports — ORDER MATTERS to avoid config.py collisions
# sys.path.insert(0, ...) prepends, so LAST insert = FIRST in path
_root = Path(__file__).parent.parent
# Insert in reverse priority: connectors, kg, then initiative (initiative must be first
# in sys.path so engine/core.py finds the right config.py)
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(_root / "percept-connectors"))
sys.path.insert(0, str(_root / "percept-kg"))
sys.path.insert(0, str(_root / "percept-initiative"))

from percept.connectors.sdk.base import BaseConnector, GraphEvent, EntityType, Node as ConnectorNode, Edge as ConnectorEdge
from percept.connectors.gmail.connector import GmailConnector
from percept.connectors.github.connector import GitHubConnector
from percept.connectors.linear.connector import LinearConnector
from percept.connectors.calendar.connector import CalendarConnector

from percept.core.graph.database import GraphDB
from percept.core.graph.models import Node as KGNode, Edge as KGEdge

from percept.initiatives.engine.core import InitiativeEngine
from percept.initiatives.engine.signals import Signal, SignalBuffer
from percept.initiatives.engine.actions import ActionHistory
from percept.initiatives.engine.rules import load_all_rules

from percept.pipeline.signals import extract_signals


# Map connector EntityType to KG node type strings
ENTITY_TYPE_MAP = {
    EntityType.PERSON: "Person",
    EntityType.DOCUMENT: "Document",
    EntityType.PROJECT: "Project",
    EntityType.CONCEPT: "Concept",
    EntityType.CHANNEL: "Channel",
    EntityType.THREAD: "Thread",
    EntityType.EVENT: "Event",
}


def load_config(config_path: str | Path | None = None) -> dict:
    """Load pipeline config from YAML."""
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    config_path = Path(config_path)
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


class PerceptPipeline:
    """Main pipeline: connectors → KG → initiative engine."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self._base = Path(__file__).parent

        # Resolve paths relative to pipeline dir
        pipe_cfg = self.config.get("pipeline", {})
        kg_path = self._resolve(pipe_cfg.get("kg_db", "../percept-kg/data/graph.db"))
        signals_path = self._resolve(pipe_cfg.get("signals_db", "../percept-initiative/data/signals.db"))
        history_path = self._resolve(pipe_cfg.get("history_db", "../percept-initiative/data/history.db"))
        rules_dir = self._resolve(pipe_cfg.get("rules_dir", "../percept-initiative/rules"))

        # Ensure data dirs exist
        kg_path.parent.mkdir(parents=True, exist_ok=True)
        signals_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.kg = GraphDB(kg_path)
        self.signal_buffer = SignalBuffer(str(signals_path))
        self.history = ActionHistory(str(history_path))

        rules = load_all_rules(rules_dir)
        self.engine = InitiativeEngine(rules, self.signal_buffer, self.history)

        # Build connectors
        self.connectors: dict[str, BaseConnector] = {}
        self._init_connectors()

    def _resolve(self, rel_path: str) -> Path:
        return (self._base / rel_path).resolve()

    def _init_connectors(self):
        conn_cfg = self.config.get("connectors", {})

        # Gmail
        gmail_cfg = conn_cfg.get("gmail", {})
        if gmail_cfg.get("enabled", True):
            c = GmailConnector(
                mock=False,
                max_results=gmail_cfg.get("max_results", 20),
                query=gmail_cfg.get("query", "in:inbox"),
            )
            if c.authenticate({}):
                self.connectors["gmail"] = c
            else:
                print("[pipeline] Gmail auth failed — using mock mode")
                c = GmailConnector(mock=True)
                c.authenticate({})
                self.connectors["gmail"] = c

        # GitHub
        gh_cfg = conn_cfg.get("github", {})
        if gh_cfg.get("enabled", True):
            c = GitHubConnector(
                repos=gh_cfg.get("repos", []),
                mock=False,
                max_repos=gh_cfg.get("max_repos", 10),
            )
            if c.authenticate({}):
                self.connectors["github"] = c
            else:
                print("[pipeline] GitHub auth failed — using mock mode")
                c = GitHubConnector(mock=True)
                c.authenticate({})
                self.connectors["github"] = c

        # Linear
        linear_cfg = conn_cfg.get("linear", {})
        if linear_cfg.get("enabled", False):
            c = LinearConnector(mock=False)
            if c.authenticate({}):
                self.connectors["linear"] = c
            else:
                print("[pipeline] Linear auth failed — using mock mode")
                c = LinearConnector(mock=True)
                c.authenticate({})
                self.connectors["linear"] = c

        # Calendar
        cal_cfg = conn_cfg.get("calendar", {})
        if cal_cfg.get("enabled", False):
            c = CalendarConnector(
                mock=False,
                max_events=cal_cfg.get("max_events", 20),
            )
            if c.authenticate({}):
                self.connectors["calendar"] = c
            else:
                print("[pipeline] Calendar auth failed — using mock mode")
                c = CalendarConnector(mock=True)
                c.authenticate({})
                self.connectors["calendar"] = c

    def sync(
        self,
        connector_name: str | None = None,
        since: datetime | None = None,
    ) -> dict:
        """Run the full pipeline: sync → KG ingest → signal extraction → initiative evaluation.

        Returns summary dict with counts and any fired actions.
        """
        results = {
            "connectors": {},
            "kg_ingested": {"nodes": 0, "edges": 0},
            "signals": [],
            "actions": [],
            "errors": [],
        }

        # 1. Run connectors
        all_events: list[GraphEvent] = []
        targets = [connector_name] if connector_name else list(self.connectors.keys())

        for name in targets:
            conn = self.connectors.get(name)
            if not conn:
                results["errors"].append(f"Connector '{name}' not found or not enabled")
                continue
            try:
                events = conn.sync(since=since)
                all_events.extend(events)
                results["connectors"][name] = {
                    "events": len(events),
                    "status": "ok",
                }
            except Exception as e:
                results["connectors"][name] = {
                    "events": 0,
                    "status": "error",
                    "error": str(e),
                }
                results["errors"].append(f"{name}: {e}")

        # 2. Ingest into KG
        nodes_added = 0
        edges_added = 0
        for event in all_events:
            try:
                if event.node:
                    kg_node = self._connector_node_to_kg(event.node, event.source)
                    self.kg.add_node(kg_node)
                    nodes_added += 1
                if event.edge:
                    # Ensure source/target nodes exist before adding edge
                    kg_edge = self._connector_edge_to_kg(event.edge, event.source)
                    # Check that both endpoints exist
                    if self.kg.get_node(kg_edge.source_id) and self.kg.get_node(kg_edge.target_id):
                        self.kg.add_edge(kg_edge)
                        edges_added += 1
            except Exception as e:
                # Don't fail the whole pipeline on a single event
                pass

        results["kg_ingested"]["nodes"] = nodes_added
        results["kg_ingested"]["edges"] = edges_added

        # 3. Extract signals from events
        sig_cfg = self.config.get("signals", {})
        signals = extract_signals(
            all_events,
            stale_pr_days=sig_cfg.get("stale_pr_days", 3),
            high_activity_threshold=sig_cfg.get("high_activity_threshold", 3),
        )

        for sig in signals:
            results["signals"].append(sig.to_dict())

        # 4. Feed signals into initiative engine
        for sig in signals:
            fired = self.engine.ingest_signal(sig)
            results["actions"].extend(fired)

        return results

    def _connector_node_to_kg(self, node: ConnectorNode, source: str) -> KGNode:
        """Convert a connector SDK Node to a KG Node."""
        node_type = ENTITY_TYPE_MAP.get(node.entity_type, "Document")
        created = node.created_at
        if isinstance(created, datetime):
            created = created.isoformat()
        return KGNode(
            id=node.id,
            type=node_type,
            name=node.name,
            properties=node.properties,
            created_at=created or "",
            updated_at=datetime.now(timezone.utc).isoformat(),
            source=source,
        )

    def _connector_edge_to_kg(self, edge: ConnectorEdge, source: str) -> KGEdge:
        """Convert a connector SDK Edge to a KG Edge."""
        return KGEdge(
            id=edge.id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            type=edge.relation,
            properties=edge.properties,
            source=source,
        )

    def status(self) -> dict:
        """Get pipeline status: KG stats, connector health, engine status."""
        kg_stats = self.kg.stats()
        engine_status = self.engine.status()

        connector_status = {}
        for name, conn in self.connectors.items():
            meta = conn.get_metadata()
            connector_status[name] = {
                "version": meta.version,
                "healthy": meta.healthy,
                "last_sync": meta.last_sync.isoformat() if meta.last_sync else None,
                "mock_mode": conn._mock_mode,
            }

        return {
            "kg": kg_stats,
            "connectors": connector_status,
            "engine": engine_status,
        }

    def close(self):
        self.kg.close()
