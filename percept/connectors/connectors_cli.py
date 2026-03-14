#!/usr/bin/env python3.11
"""Percept Connector SDK — CLI interface."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from percept.connectors.sdk.base import GraphEvent
from percept.connectors.sdk.registry import ConnectorRegistry


def get_registry(mock: bool = False) -> ConnectorRegistry:
    """Build and return a registry with all installed connectors."""
    registry = ConnectorRegistry()

    # Auto-discover connectors
    from connectors.gmail.connector import GmailConnector
    from connectors.github.connector import GitHubConnector
    from connectors.slack.connector import SlackConnector
    from connectors.oura.connector import OuraConnector

    gmail = GmailConnector(mock=mock)
    github = GitHubConnector(mock=mock)
    slack = SlackConnector(mock=mock)
    oura = OuraConnector(mock=mock)

    # Auto-authenticate
    for c in [gmail, github, slack, oura]:
        try:
            c.authenticate({})
        except Exception:
            pass

    registry.register(gmail)
    registry.register(github)
    registry.register(slack)
    registry.register(oura)

    return registry


def cmd_list(args):
    """List installed connectors."""
    registry = get_registry(mock=args.mock)
    connectors = registry.list_connectors()

    if not connectors:
        print("No connectors installed.")
        return

    print(f"{'Name':<12} {'Version':<10} {'Auth':<10} {'Healthy':<10} {'Description'}")
    print("─" * 70)
    for c in connectors:
        health = "✅" if c.healthy else "❌"
        print(f"{c.name:<12} {c.version:<10} {c.auth_type:<10} {health:<10} {c.description}")


def cmd_test(args):
    """Test a connector's connection."""
    registry = get_registry(mock=args.mock)
    connector = registry.get_connector(args.connector)

    print(f"Testing {args.connector}...")
    try:
        ok = connector.test_connection()
        if ok:
            print(f"✅ {args.connector} connection OK")
        else:
            print(f"❌ {args.connector} connection failed")
            sys.exit(1)
    except Exception as e:
        print(f"❌ {args.connector} error: {e}")
        sys.exit(1)


def cmd_sync(args):
    """Sync one or all connectors."""
    registry = get_registry(mock=args.mock)

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since)

    if args.all:
        print("🔄 Syncing all connectors...")
        events = registry.sync_all(since=since)
    else:
        if not args.connector:
            print("Error: specify a connector name or --all")
            sys.exit(1)
        print(f"🔄 Syncing {args.connector}...")
        events = registry.sync_one(args.connector, since=since)

    _print_events(events, verbose=args.verbose)


def cmd_discover(args):
    """Show entity types a connector can produce."""
    registry = get_registry(mock=args.mock)
    connector = registry.get_connector(args.connector)

    schemas = connector.discover()
    print(f"\n📊 {args.connector} produces {len(schemas)} entity types:\n")
    for s in schemas:
        print(f"  {s.entity_type.value:<12} {s.name}")
        print(f"  {'':12} {s.description}")
        if s.properties:
            print(f"  {'':12} Properties: {', '.join(s.properties)}")
        print()


def cmd_create(args):
    """Scaffold a new connector from template."""
    name = args.name.lower().replace(" ", "_").replace("-", "_")
    target = Path(__file__).parent / "connectors" / name

    if target.exists():
        print(f"❌ Connector directory already exists: {target}")
        sys.exit(1)

    template = Path(__file__).parent / "templates" / "connector_template"
    shutil.copytree(template, target)

    # Replace placeholders
    class_name = "".join(w.capitalize() for w in name.split("_"))
    replacements = {
        "{{NAME}}": name,
        "{{CLASS_NAME}}": class_name,
        "{{AUTH_TYPE}}": args.auth or "none",
        "{{DESCRIPTION}}": args.description or f"{class_name} connector",
    }

    for f in target.rglob("*"):
        if f.is_file():
            content = f.read_text()
            for old, new in replacements.items():
                content = content.replace(old, new)
            f.write_text(content)

    # Create __init__.py
    (target / "__init__.py").write_text(
        f'from .connector import {class_name}Connector\n\n'
        f'__all__ = ["{class_name}Connector"]\n'
    )

    print(f"✅ Created connector scaffold at {target}/")
    print(f"   Edit {target}/connector.py to implement your connector.")


def cmd_status(args):
    """Show sync status."""
    registry = get_registry(mock=args.mock)
    status = registry.status()

    print(f"\n📊 Percept Connectors Status")
    print(f"   Registered: {status['connectors']} connectors ({', '.join(status['registered'])})\n")

    if status["last_sync"]:
        print("   Last sync:")
        for name, ts in status["last_sync"].items():
            print(f"     {name:<12} {ts}")
    else:
        print("   No sync history yet.")

    if status["errors"]:
        print("\n   ⚠️  Errors:")
        for name, err in status["errors"].items():
            print(f"     {name:<12} {err}")

    print()


def _print_events(events: list[GraphEvent], verbose: bool = False):
    """Pretty-print graph events."""
    if not events:
        print("📭 No events.")
        return

    nodes = [e for e in events if e.node]
    edges = [e for e in events if e.edge]

    print(f"\n📥 {len(events)} graph events ({len(nodes)} nodes, {len(edges)} edges)\n")

    if verbose:
        for e in events:
            if e.node:
                print(f"  📦 {e.event_type}: [{e.node.entity_type.value}] {e.node.name}")
                print(f"     id={e.node.id}")
            elif e.edge:
                print(f"  🔗 {e.event_type}: {e.edge.source_id} —[{e.edge.relation}]→ {e.edge.target_id}")
    else:
        # Summary by type
        from collections import Counter
        node_types = Counter(e.node.entity_type.value for e in nodes)
        edge_types = Counter(e.edge.relation for e in edges)

        print("  Nodes:")
        for t, count in node_types.most_common():
            print(f"    {t:<15} {count}")

        print("  Edges:")
        for t, count in edge_types.most_common():
            print(f"    {t:<15} {count}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Percept Connector SDK CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--mock", action="store_true", help="Use mock data (no real API calls)")

    sub = parser.add_subparsers(dest="command", help="Command")

    # list
    sub.add_parser("list", help="List installed connectors")

    # test
    p = sub.add_parser("test", help="Test a connector's connection")
    p.add_argument("connector", help="Connector name")

    # sync
    p = sub.add_parser("sync", help="Sync connector data")
    p.add_argument("connector", nargs="?", help="Connector name")
    p.add_argument("--all", action="store_true", help="Sync all connectors")
    p.add_argument("--since", help="ISO datetime to sync from")
    p.add_argument("--verbose", "-v", action="store_true", help="Show detailed events")

    # discover
    p = sub.add_parser("discover", help="Show entity types a connector produces")
    p.add_argument("connector", help="Connector name")

    # create
    p = sub.add_parser("create", help="Scaffold a new connector")
    p.add_argument("name", help="Connector name")
    p.add_argument("--auth", help="Auth type (oauth2, api_key, token, none)")
    p.add_argument("--description", help="Connector description")

    # status
    sub.add_parser("status", help="Show sync status and health")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "list": cmd_list,
        "test": cmd_test,
        "sync": cmd_sync,
        "discover": cmd_discover,
        "create": cmd_create,
        "status": cmd_status,
    }

    try:
        commands[args.command](args)
    except KeyError as e:
        print(f"❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
