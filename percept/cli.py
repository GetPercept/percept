#!/usr/bin/env python3
"""Percept CLI — unified command-line interface.

Usage:
    percept sync                       Run all connectors → KG → initiatives
    percept sync --connector gmail     Single connector
    percept status                     KG stats + connector health + initiatives
    percept query "who emailed me"     Search the knowledge graph
    percept serve                      Start the audio pipeline + API
    percept connectors                 List installed connectors
    percept initiatives                List triggered initiatives
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def cmd_sync(args):
    """Run connectors, ingest to KG, evaluate initiatives."""
    from percept.pipeline.pipeline import PerceptPipeline, load_config

    config = load_config(args.config)
    pipeline = PerceptPipeline(config)

    connector = getattr(args, "connector", None)
    print(f"🔄 Syncing {'all connectors' if not connector else connector}...")

    result = pipeline.sync(connector_name=connector)

    for name, info in result["connectors"].items():
        icon = "✅" if info["status"] == "ok" else "❌"
        print(f"  {icon} {name}: {info['events']} events")
        if info.get("error"):
            print(f"      Error: {info['error']}")

    print(f"\n📊 KG: {result['kg_ingested']['nodes']} nodes, {result['kg_ingested']['edges']} edges")

    if result["signals"]:
        print(f"\n⚡ {len(result['signals'])} signals detected")
        for sig in result["signals"]:
            print(f"  • [{sig['source']}] {sig['signal_type']}: {sig['entity']}")

    if result["actions"]:
        print(f"\n🎯 {len(result['actions'])} actions fired")
        for action in result["actions"]:
            print(f"  • [{action['action_type']}] {action['rule']}: {action['message']}")

    if result["errors"]:
        print(f"\n⚠️  {len(result['errors'])} errors")
        for err in result["errors"]:
            print(f"  • {err}")

    pipeline.close()
    return 0 if not result["errors"] else 1


def cmd_status(args):
    """Show pipeline status."""
    from percept.pipeline.pipeline import PerceptPipeline, load_config

    config = load_config(args.config)
    pipeline = PerceptPipeline(config)
    status = pipeline.status()

    print("📊 Knowledge Graph")
    kg = status["kg"]
    print(f"  Nodes: {kg['nodes']}  |  Edges: {kg['edges']}  |  Density: {kg['density']}")
    if kg.get("node_types"):
        for t, c in kg["node_types"].items():
            print(f"    {t}: {c}")

    print("\n🔌 Connectors")
    for name, info in status["connectors"].items():
        health = "✅" if info["healthy"] else "❌"
        mock = " (mock)" if info.get("mock_mode") else ""
        print(f"  {health} {name} v{info['version']}{mock} — last sync: {info.get('last_sync', 'never')}")

    print("\n🧠 Initiative Engine")
    eng = status["engine"]
    print(f"  Rules: {eng['rules_enabled']}/{eng['rules_total']} enabled")
    print(f"  Signals buffered: {eng['signal_buffer_size']}")
    print(f"  Active cooldowns: {eng['active_cooldowns']}")

    pipeline.close()


def cmd_query(args):
    """Query the knowledge graph."""
    from percept.pipeline.pipeline import PerceptPipeline, load_config

    query = " ".join(args.query)
    if not query:
        print("Usage: percept query \"your question\"")
        return 1

    config = load_config(args.config)
    pipeline = PerceptPipeline(config)
    print(f"🔍 Searching: {query}\n")

    results = pipeline.kg.search_nodes(query, limit=20)
    if not results:
        print("  No results found.")
    else:
        for node in results:
            print(f"  [{node.type}] {node.name}")
            if node.properties:
                for key in ("email", "url", "state", "labels", "snippet", "date"):
                    if key in node.properties:
                        val = node.properties[key]
                        if isinstance(val, str) and len(val) > 80:
                            val = val[:77] + "..."
                        print(f"    {key}: {val}")
            neighbors = pipeline.kg.neighbors(node.id, direction="both")
            if neighbors:
                for edge, neighbor in neighbors[:3]:
                    if neighbor:
                        print(f"    → {edge.type} → [{neighbor.type}] {neighbor.name}")
            print()

    pipeline.close()


def cmd_serve(args):
    """Start the audio pipeline + API server."""
    from percept.audio.receiver import main as audio_main
    print("🎧 Starting Percept audio pipeline...")
    audio_main()


def cmd_initiatives(args):
    """List recent initiative actions."""
    from percept.pipeline.pipeline import PerceptPipeline, load_config

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

    status = pipeline.engine.status()
    print(f"Engine: {status['rules_enabled']}/{status['rules_total']} rules, "
          f"{status['signal_buffer_size']} signals buffered")
    pipeline.close()


def cmd_connectors(args):
    """List installed connectors."""
    from percept.pipeline.pipeline import PerceptPipeline, load_config

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

    pipeline.close()


def main():
    parser = argparse.ArgumentParser(
        prog="percept",
        description="Percept — the context layer for AI agents",
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")

    sub = parser.add_subparsers(dest="command")

    sync_p = sub.add_parser("sync", help="Run connectors → KG → initiatives")
    sync_p.add_argument("--connector", "-c", type=str, default=None,
                        help="Run only this connector (gmail, github, linear, calendar)")

    sub.add_parser("status", help="Show pipeline status")
    sub.add_parser("serve", help="Start the audio pipeline + API")
    sub.add_parser("initiatives", help="List triggered initiatives")
    sub.add_parser("connectors", help="List installed connectors")

    query_p = sub.add_parser("query", help="Query the knowledge graph")
    query_p.add_argument("query", nargs="*", help="Search query")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    dispatch = {
        "sync": cmd_sync,
        "status": cmd_status,
        "query": cmd_query,
        "serve": cmd_serve,
        "initiatives": cmd_initiatives,
        "connectors": cmd_connectors,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
