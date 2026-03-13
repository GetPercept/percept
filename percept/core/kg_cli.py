#!/usr/bin/env python3.11
"""Percept Knowledge Graph CLI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from percept.core.config import DB_PATH, SOURCES
from percept.core.graph.database import GraphDB
from percept.core.graph.models import Node, Edge
from percept.core.graph.query import QueryEngine
from percept.core.graph.temporal import TemporalQuery


def get_db() -> GraphDB:
    return GraphDB(DB_PATH)


def cmd_ingest(args):
    """Ingest all source files into the graph."""
    db = get_db()

    if args.clean:
        db.clear()
        print("🗑️  Cleared existing graph.")

    from ingest.user import UserIngester
    from ingest.tools import ToolsIngester
    from ingest.memory import MemoryIngester
    from ingest.decisions import DecisionsIngester
    from ingest.lessons import LessonsIngester
    from ingest.code_ids import CodeIdsIngester
    from ingest.daily import DailyIngester

    ingesters = [
        (UserIngester(db), SOURCES["user"]),
        (ToolsIngester(db), SOURCES["tools"]),
        (MemoryIngester(db), SOURCES["memory"]),
        (DecisionsIngester(db), SOURCES["decisions"]),
        (LessonsIngester(db), SOURCES["lessons"]),
        (CodeIdsIngester(db), SOURCES["code_ids"]),
        (DailyIngester(db), SOURCES["daily_dir"]),
    ]

    total_nodes = 0
    total_edges = 0

    for ingester, path in ingesters:
        try:
            stats = ingester.ingest(path)
            n = stats["nodes_created"]
            e = stats["edges_created"]
            total_nodes += n
            total_edges += e
            print(f"  ✅ {stats['source']}: {n} nodes, {e} edges")
        except Exception as ex:
            print(f"  ❌ {ingester.source_name}: {ex}")

    print(f"\n📊 Total: {total_nodes} nodes, {total_edges} edges ingested")

    # Show final stats
    s = db.stats()
    print(f"📈 Graph now has {s['nodes']} nodes, {s['edges']} edges (density: {s['density']})")
    db.close()


def cmd_query(args):
    """Run a natural language query."""
    db = get_db()
    engine = QueryEngine(db)
    result = engine.query(args.text)
    print(f"\n🔍 {result['summary']}")
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    elif result["results"]:
        for i, r in enumerate(result["results"][:10], 1):
            if isinstance(r, dict):
                name = r.get("name", r.get("decision", r.get("lesson", str(r))))
                print(f"  {i}. {name}")
                for k, v in r.items():
                    if k not in ("name", "decision", "lesson") and v:
                        val = str(v)[:100]
                        print(f"     {k}: {val}")
    db.close()


def cmd_add_node(args):
    """Add a node to the graph."""
    db = get_db()
    props = {}
    if args.properties:
        for p in args.properties:
            k, v = p.split("=", 1)
            props[k] = v
    # Also handle --role, --org, etc as properties
    for attr in ("role", "org", "email", "url", "status"):
        val = getattr(args, attr, None)
        if val:
            props[attr] = val

    node = db.find_or_create_node(args.name, args.type, props, source="cli")
    print(f"✅ Added [{node.type}] {node.name} (id: {node.id[:8]})")
    db.close()


def cmd_add_edge(args):
    """Add an edge between two nodes."""
    db = get_db()
    source = db.find_node(args.source)  # --from
    target = db.find_node(args.target)  # --to

    if not source:
        print(f"❌ Source node '{args.source}' not found.")
        return
    if not target:
        print(f"❌ Target node '{args.target}' not found.")
        return

    edge = db.find_or_create_edge(source.id, target.id, args.type, source="cli")
    print(f"✅ {source.name} --[{edge.type}]--> {target.name}")
    db.close()


def cmd_neighbors(args):
    """Show all neighbors of a node."""
    db = get_db()
    node = db.find_node(args.name)
    if not node:
        print(f"❌ Node '{args.name}' not found.")
        return

    print(f"\n🔗 Neighbors of [{node.type}] {node.name}:")
    neighbors = db.neighbors(node.id)
    if not neighbors:
        print("  (none)")
    for edge, neighbor in neighbors:
        if neighbor:
            direction = "→" if edge.source_id == node.id else "←"
            print(f"  {direction} [{edge.type}] {neighbor.name} [{neighbor.type}]")
    db.close()


def cmd_path(args):
    """Find shortest path between two entities."""
    db = get_db()
    path = db.shortest_path(args.start, args.end)
    if not path:
        print(f"❌ No path found between '{args.start}' and '{args.end}'.")
        return

    print(f"\n🛤️  Path from '{args.start}' to '{args.end}' ({len(path)} hops):")
    for src, edge, tgt in path:
        print(f"  [{src.type}] {src.name} --[{edge.type}]--> [{tgt.type}] {tgt.name}")
    db.close()


def cmd_timeline(args):
    """Show temporal view of an entity."""
    db = get_db()
    tq = TemporalQuery(db)
    events = tq.timeline(args.entity, days=args.days)
    if not events:
        print(f"❌ No recent activity for '{args.entity}'.")
        return

    print(f"\n📅 Timeline for '{args.entity}' (last {args.days} days):")
    for e in events:
        print(f"  {e['date']} | {e['edge_type']} → {e['related']} [{e['related_type']}]")
    db.close()


def cmd_stats(args):
    """Show graph statistics."""
    db = get_db()
    s = db.stats()
    print(f"\n📊 Knowledge Graph Stats")
    print(f"  Nodes: {s['nodes']}")
    print(f"  Edges: {s['edges']}")
    print(f"  Density: {s['density']}")
    print(f"\n  Node types:")
    for t, c in s["node_types"].items():
        print(f"    {t}: {c}")
    print(f"\n  Edge types:")
    for t, c in s["edge_types"].items():
        print(f"    {t}: {c}")
    db.close()


def cmd_export(args):
    """Export graph to JSON."""
    db = get_db()
    data = db.export_json()
    if args.output:
        Path(args.output).write_text(json.dumps(data, indent=2, default=str))
        print(f"✅ Exported to {args.output}")
    else:
        print(json.dumps(data, indent=2, default=str))
    db.close()


def cmd_visualize(args):
    """ASCII visualization of the graph (or subgraph around an entity)."""
    db = get_db()

    if args.entity:
        node = db.find_node(args.entity)
        if not node:
            print(f"❌ Node '{args.entity}' not found.")
            return
        _viz_subgraph(db, node, args.depth)
    else:
        _viz_full(db)
    db.close()


def _viz_subgraph(db: GraphDB, center: Node, depth: int = 1):
    """Visualize a subgraph around a center node."""
    print(f"\n🕸️  Graph around [{center.type}] {center.name}:\n")
    print(f"  ╔══ {center.name} [{center.type}] ══╗")

    neighbors = db.neighbors(center.id)
    for i, (edge, neighbor) in enumerate(neighbors):
        if not neighbor:
            continue
        is_last = i == len(neighbors) - 1
        connector = "╚" if is_last else "╠"
        direction = "→" if edge.source_id == center.id else "←"
        print(f"  {connector}══ {direction} [{edge.type}] ══ {neighbor.name} [{neighbor.type}]")

        if depth > 1:
            sub_neighbors = db.neighbors(neighbor.id)
            for j, (se, sn) in enumerate(sub_neighbors[:5]):
                if sn and sn.id != center.id:
                    prefix = "     " if is_last else "  ║  "
                    print(f"{prefix}  └─ [{se.type}] → {sn.name}")


def _viz_full(db: GraphDB):
    """Full graph overview."""
    s = db.stats()
    print(f"\n🕸️  Knowledge Graph ({s['nodes']} nodes, {s['edges']} edges)\n")

    for node_type, count in sorted(s["node_types"].items()):
        nodes = db.list_nodes(node_type, limit=10)
        print(f"  [{node_type}] ({count})")
        for n in nodes:
            neighbors = db.neighbors(n.id)
            conn_count = len(neighbors)
            print(f"    • {n.name} ({conn_count} connections)")
        if count > 10:
            print(f"    ... and {count - 10} more")
        print()


def cmd_search(args):
    """Full-text search across nodes."""
    db = get_db()
    nodes = db.search_nodes(args.query, node_type=args.type)
    if not nodes:
        print(f"No results for '{args.query}'.")
        return
    print(f"\n🔍 Search results for '{args.query}':")
    for n in nodes[:20]:
        print(f"  [{n.type}] {n.name}")
        if n.properties:
            for k, v in list(n.properties.items())[:3]:
                print(f"    {k}: {str(v)[:80]}")
    db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Percept Knowledge Graph CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3.11 cli.py ingest --clean          # Fresh ingest from all source files
  python3.11 cli.py query "Who works at VectorCare?"
  python3.11 cli.py neighbors David
  python3.11 cli.py path David Polymarket
  python3.11 cli.py stats
  python3.11 cli.py visualize --entity David
        """,
    )
    subs = parser.add_subparsers(dest="command")

    # ingest
    p = subs.add_parser("ingest", help="Ingest source files into the graph")
    p.add_argument("--clean", action="store_true", help="Clear graph before ingesting")

    # query
    p = subs.add_parser("query", help="Natural language query")
    p.add_argument("text", help="Query text")
    p.add_argument("--json", action="store_true", help="Output raw JSON")

    # add-node
    p = subs.add_parser("add-node", help="Add a node")
    p.add_argument("--type", required=True, help="Node type (Person, Organization, etc.)")
    p.add_argument("--name", required=True, help="Node name")
    p.add_argument("--role", help="Role (for Person)")
    p.add_argument("--org", help="Organization")
    p.add_argument("--email", help="Email")
    p.add_argument("--url", help="URL")
    p.add_argument("--status", help="Status")
    p.add_argument("--properties", nargs="*", help="Additional properties as key=value")

    # add-edge
    p = subs.add_parser("add-edge", help="Add an edge")
    p.add_argument("--from", dest="source", required=True, help="Source node name")
    p.add_argument("--to", dest="target", required=True, help="Target node name")
    p.add_argument("--type", required=True, help="Edge type (WORKS_AT, OWNS, etc.)")

    # neighbors
    p = subs.add_parser("neighbors", help="Show neighbors of a node")
    p.add_argument("name", help="Node name")

    # path
    p = subs.add_parser("path", help="Shortest path between nodes")
    p.add_argument("start", help="Start node name")
    p.add_argument("end", help="End node name")

    # timeline
    p = subs.add_parser("timeline", help="Temporal view of an entity")
    p.add_argument("--entity", required=True, help="Entity name")
    p.add_argument("--days", type=int, default=30, help="Number of days to look back")

    # stats
    subs.add_parser("stats", help="Graph statistics")

    # export
    p = subs.add_parser("export", help="Export graph")
    p.add_argument("--format", default="json", choices=["json"], help="Export format")
    p.add_argument("--output", "-o", help="Output file path")

    # visualize
    p = subs.add_parser("visualize", help="ASCII visualization")
    p.add_argument("--entity", help="Center entity (optional)")
    p.add_argument("--depth", type=int, default=1, help="Traversal depth")

    # search
    p = subs.add_parser("search", help="Full-text search")
    p.add_argument("query", help="Search query")
    p.add_argument("--type", help="Filter by node type")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    commands = {
        "ingest": cmd_ingest,
        "query": cmd_query,
        "add-node": cmd_add_node,
        "add-edge": cmd_add_edge,
        "neighbors": cmd_neighbors,
        "path": cmd_path,
        "timeline": cmd_timeline,
        "stats": cmd_stats,
        "export": cmd_export,
        "visualize": cmd_visualize,
        "search": cmd_search,
    }

    fn = commands.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
