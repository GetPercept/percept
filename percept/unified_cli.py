#!/usr/bin/env python3
"""Percept CLI — unified command-line interface for the Percept system.

Usage:
    percept sync                       Run all connectors, ingest to KG, evaluate initiatives
    percept sync --connector gmail     Just Gmail
    percept sync --connector github    Just GitHub
    percept status                     Show KG stats + connector health + active initiatives
    percept query "who emailed me"     Natural language KG query
    percept initiatives                List triggered/pending initiatives
    percept connectors                 List installed connectors + status
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Wire up imports — only add pipeline path, it handles the rest
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "percept-pipeline"))

from percept.pipeline.pipeline import PerceptPipeline, load_config


def cmd_sync(args):
    """Run connectors, ingest to KG, evaluate initiatives."""
    config = load_config(args.config)
    pipeline = PerceptPipeline(config)

    connector = args.connector if hasattr(args, "connector") else None
    print(f"🔄 Syncing {'all connectors' if not connector else connector}...")

    result = pipeline.sync(connector_name=connector)

    # Print results
    for name, info in result["connectors"].items():
        status_icon = "✅" if info["status"] == "ok" else "❌"
        print(f"  {status_icon} {name}: {info['events']} events")
        if info.get("error"):
            print(f"      Error: {info['error']}")

    print(f"\n📊 KG Ingested: {result['kg_ingested']['nodes']} nodes, {result['kg_ingested']['edges']} edges")

    if result["signals"]:
        print(f"\n⚡ Signals detected: {len(result['signals'])}")
        for sig in result["signals"]:
            print(f"  • [{sig['source']}] {sig['signal_type']}: {sig['entity']}")

    if result["actions"]:
        print(f"\n🎯 Actions fired: {len(result['actions'])}")
        for action in result["actions"]:
            print(f"  • [{action['action_type']}] {action['rule']}: {action['message']}")

    if result["errors"]:
        print(f"\n⚠️  Errors: {len(result['errors'])}")
        for err in result["errors"]:
            print(f"  • {err}")

    pipeline.close()
    return 0 if not result["errors"] else 1


def cmd_status(args):
    """Show pipeline status."""
    config = load_config(args.config)
    pipeline = PerceptPipeline(config)
    status = pipeline.status()

    print("📊 Knowledge Graph")
    kg = status["kg"]
    print(f"  Nodes: {kg['nodes']}")
    print(f"  Edges: {kg['edges']}")
    print(f"  Density: {kg['density']}")
    if kg.get("node_types"):
        print("  Node types:")
        for t, c in kg["node_types"].items():
            print(f"    {t}: {c}")
    if kg.get("edge_types"):
        print("  Edge types:")
        for t, c in kg["edge_types"].items():
            print(f"    {t}: {c}")

    print("\n🔌 Connectors")
    for name, info in status["connectors"].items():
        health = "✅" if info["healthy"] else "❌"
        mock = " (mock)" if info.get("mock_mode") else ""
        last = info.get("last_sync", "never")
        print(f"  {health} {name} v{info['version']}{mock} — last sync: {last}")

    print("\n🧠 Initiative Engine")
    eng = status["engine"]
    print(f"  Rules: {eng['rules_enabled']}/{eng['rules_total']} enabled")
    print(f"  Signal buffer: {eng['signal_buffer_size']} signals")
    print(f"  Active cooldowns: {eng['active_cooldowns']}")

    pipeline.close()


def cmd_query(args):
    """Query the knowledge graph."""
    config = load_config(args.config)
    pipeline = PerceptPipeline(config)

    query = " ".join(args.query)
    if not query:
        print("Usage: percept query \"your question\"")
        pipeline.close()
        return 1

    print(f"🔍 Searching: {query}\n")

    # Use FTS search on the KG
    results = pipeline.kg.search_nodes(query, limit=20)
    if not results:
        print("  No results found.")
    else:
        for node in results:
            print(f"  [{node.type}] {node.name}")
            if node.properties:
                # Show select properties
                for key in ("email", "url", "state", "labels", "snippet", "date"):
                    if key in node.properties:
                        val = node.properties[key]
                        if isinstance(val, str) and len(val) > 80:
                            val = val[:77] + "..."
                        print(f"    {key}: {val}")

            # Show connections
            neighbors = pipeline.kg.neighbors(node.id, direction="both")
            if neighbors:
                for edge, neighbor in neighbors[:3]:
                    if neighbor:
                        print(f"    → {edge.type} → [{neighbor.type}] {neighbor.name}")
            print()

    pipeline.close()


def cmd_initiatives(args):
    """List recent initiative actions."""
    config = load_config(args.config)
    pipeline = PerceptPipeline(config)

    recent = pipeline.history.recent(limit=20)
    if not recent:
        print("📋 No initiatives fired yet. Run `percept sync` first.")
    else:
        print("📋 Recent Initiatives\n")
        for item in recent:
            print(f"  [{item['action_type']}] {item['rule_name']}")
            print(f"    {item['message']}")
            print(f"    Status: {item['status']} | {item['timestamp']}")
            print()

    # Show engine status
    status = pipeline.engine.status()
    print(f"Engine: {status['rules_enabled']}/{status['rules_total']} rules enabled, "
          f"{status['signal_buffer_size']} signals buffered")

    pipeline.close()


def cmd_connectors(args):
    """List installed connectors."""
    config = load_config(args.config)
    pipeline = PerceptPipeline(config)

    print("🔌 Installed Connectors\n")
    for name, conn in pipeline.connectors.items():
        meta = conn.get_metadata()
        health = "✅" if meta.healthy else "❌"
        mock = " (MOCK)" if conn._mock_mode else " (LIVE)"
        print(f"  {health} {meta.name} v{meta.version}{mock}")
        print(f"    {meta.description}")
        print(f"    Auth: {meta.auth_type}")
        entities = conn.discover()
        if entities:
            types = ", ".join(e.name for e in entities)
            print(f"    Entities: {types}")
        if meta.last_sync:
            print(f"    Last sync: {meta.last_sync.isoformat()}")
        print()

    # Show disabled connectors from config
    conn_cfg = config.get("connectors", {})
    for name, cfg in conn_cfg.items():
        if not cfg.get("enabled", True) and name not in pipeline.connectors:
            print(f"  ⏸️  {name} (disabled in config)")

    pipeline.close()


def main():
    parser = argparse.ArgumentParser(
        prog="percept",
        description="Percept — unified knowledge graph pipeline",
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")

    subparsers = parser.add_subparsers(dest="command")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Run connectors and sync to KG")
    sync_parser.add_argument("--connector", "-c", type=str, default=None,
                             help="Run only this connector (gmail, github)")

    # status
    subparsers.add_parser("status", help="Show pipeline status")

    # query
    query_parser = subparsers.add_parser("query", help="Query the knowledge graph")
    query_parser.add_argument("query", nargs="*", help="Search query")

    # initiatives
    subparsers.add_parser("initiatives", help="List triggered initiatives")

    # connectors
    subparsers.add_parser("connectors", help="List installed connectors")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "sync": cmd_sync,
        "status": cmd_status,
        "query": cmd_query,
        "initiatives": cmd_initiatives,
        "connectors": cmd_connectors,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
