#!/usr/bin/env python3.11
"""Percept Mesh CLI — team agent graph management."""
import sys
import os
import json
import signal
import subprocess
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from percept.mesh.config import DEFAULT_PORT, DEFAULT_HOST, SERVER_URL, API_KEY


def get_client():
    """Get a MeshClient configured from env or config."""
    from percept.mesh.agent.mesh_client import MeshClient
    url = os.environ.get("PERCEPT_MESH_URL", SERVER_URL)
    key = os.environ.get("PERCEPT_MESH_KEY", API_KEY)
    if not key:
        print("Error: Set PERCEPT_MESH_KEY env var or configure API_KEY in config.py")
        sys.exit(1)
    state_path = os.path.join(os.path.dirname(__file__), "data", "client_state.json")
    return MeshClient(url, key, local_state_path=state_path)


def cmd_server_start(args):
    """Start the team graph server."""
    port = args.port or DEFAULT_PORT
    pid_file = os.path.join(os.path.dirname(__file__), "data", ".server.pid")
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    
    if os.path.exists(pid_file):
        with open(pid_file) as f:
            old_pid = f.read().strip()
        try:
            os.kill(int(old_pid), 0)
            print(f"Server already running (PID {old_pid}) on port {port}")
            return
        except (ProcessLookupError, ValueError):
            os.unlink(pid_file)
    
    # Start server as background process
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app",
         "--host", DEFAULT_HOST, "--port", str(port)],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stdout=open(os.path.join(os.path.dirname(__file__), "data", "server.log"), "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    
    with open(pid_file, "w") as f:
        f.write(str(proc.pid))
    
    # Wait briefly and check if it started
    time.sleep(1)
    if proc.poll() is None:
        print(f"✓ Server started on port {port} (PID {proc.pid})")
    else:
        print(f"✗ Server failed to start. Check data/server.log")


def cmd_server_stop(args):
    """Stop the team graph server."""
    pid_file = os.path.join(os.path.dirname(__file__), "data", ".server.pid")
    if not os.path.exists(pid_file):
        print("Server not running (no PID file)")
        return
    
    with open(pid_file) as f:
        pid = int(f.read().strip())
    
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"✓ Server stopped (PID {pid})")
    except ProcessLookupError:
        print("Server was not running")
    
    os.unlink(pid_file)


def cmd_team_create(args):
    """Create a new team."""
    import requests
    url = os.environ.get("PERCEPT_MESH_URL", SERVER_URL)
    resp = requests.post(f"{url}/api/team/create", json={"name": args.name}, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ Team '{data['name']}' created")
        print(f"  Team ID:       {data['team_id']}")
        print(f"  Admin API Key: {data['admin_api_key']}")
        print(f"\n  Export this key: export PERCEPT_MESH_KEY={data['admin_api_key']}")
    else:
        print(f"✗ Failed: {resp.text}")


def cmd_team_invite(args):
    """Generate an invite key."""
    client = get_client()
    import requests
    resp = requests.post(
        f"{client.server_url}/api/team/invite",
        json={"role": args.role, "max_uses": args.max_uses, "expires_hours": args.expires},
        headers=client._headers(), timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ Invite key generated")
        print(f"  Key:     {data['invite_key']}")
        print(f"  Role:    {data['role']}")
        print(f"  Expires: {data['expires_at']}")
    else:
        print(f"✗ Failed: {resp.text}")


def cmd_team_join(args):
    """Join a team with an invite key."""
    import requests
    url = os.environ.get("PERCEPT_MESH_URL", SERVER_URL)
    resp = requests.post(
        f"{url}/api/team/join",
        json={"invite_key": args.invite_key, "member_name": args.name or "agent"},
        timeout=10
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ Joined team '{data['team_name']}' as {data['role']}")
        print(f"  Member ID: {data['member_id']}")
        print(f"  API Key:   {data['api_key']}")
        print(f"\n  Export this key: export PERCEPT_MESH_KEY={data['api_key']}")
    else:
        print(f"✗ Failed: {resp.text}")


def cmd_team_members(args):
    """List team members."""
    client = get_client()
    members = client.get_team_members()
    if not members:
        print("No members found (or server unreachable)")
        return
    
    from percept.mesh.agent.presence import PresenceManager
    print(PresenceManager.format_presence(members))


def cmd_team_remove(args):
    """Remove a member."""
    client = get_client()
    import requests
    resp = requests.delete(
        f"{client.server_url}/api/team/members/{args.member_id}",
        headers=client._headers(), timeout=10
    )
    if resp.status_code == 200:
        print(f"✓ Removed member {args.member_id}")
    else:
        print(f"✗ Failed: {resp.text}")


def cmd_sync_push(args):
    """Push shared context to team."""
    client = get_client()
    # In a real integration, this would read from the agent's local graph.
    # For now, read from a local nodes.json if it exists.
    nodes_file = os.path.join(os.path.dirname(__file__), "data", "local_nodes.json")
    edges_file = os.path.join(os.path.dirname(__file__), "data", "local_edges.json")
    
    nodes = []
    edges = []
    if os.path.exists(nodes_file):
        nodes = json.loads(open(nodes_file).read())
    if os.path.exists(edges_file):
        edges = json.loads(open(edges_file).read())
    
    if not nodes and not edges:
        print("No local nodes/edges to push. Add nodes to data/local_nodes.json")
        return
    
    result = client.push(nodes, edges)
    if "error" in result:
        print(f"✗ Push failed: {result['error']}")
    else:
        print(f"✓ Pushed: {result.get('accepted_nodes', 0)} nodes, "
              f"{result.get('accepted_edges', 0)} edges "
              f"({result.get('blocked', 0)} blocked by policy)")


def cmd_sync_pull(args):
    """Pull team updates."""
    client = get_client()
    result = client.pull()
    if "error" in result:
        print(f"✗ Pull failed: {result['error']}")
    else:
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
        print(f"✓ Pulled: {len(nodes)} nodes, {len(edges)} edges")
        for n in nodes[:10]:
            print(f"  [{n.get('node_type')}] {n.get('name')}")
        if len(nodes) > 10:
            print(f"  ... and {len(nodes) - 10} more")


def cmd_sync_auto(args):
    """Auto-sync every N seconds."""
    client = get_client()
    interval = args.interval
    print(f"Auto-syncing every {interval}s (Ctrl+C to stop)")
    
    client.presence.start()
    try:
        while True:
            result = client.pull()
            nodes = result.get("nodes", [])
            edges = result.get("edges", [])
            print(f"  [{time.strftime('%H:%M:%S')}] Pulled {len(nodes)} nodes, {len(edges)} edges")
            time.sleep(interval)
    except KeyboardInterrupt:
        client.presence.stop()
        print("\nStopped.")


def cmd_sync_status(args):
    """Show sync health."""
    client = get_client()
    result = client.sync_status()
    if "error" in result:
        print(f"✗ {result['error']}")
    else:
        status = result.get("status", [])
        if not status:
            print("No sync history.")
        else:
            print("Sync Status:")
            for s in status:
                print(f"  {s.get('member_id', '?')[:8]}... "
                      f"{s.get('action', '?')} — last: {s.get('last_sync', '?')} "
                      f"({s.get('total_nodes', 0)} nodes, {s.get('total_edges', 0)} edges)")


def cmd_query(args):
    """Natural language team query."""
    client = get_client()
    query_text = " ".join(args.query_text)
    result = client.query(query_text)
    if "error" in result:
        print(f"✗ {result['error']}")
    else:
        print(result.get("answer", "No answer"))


def cmd_query_bandwidth(args):
    """Who has bandwidth?"""
    client = get_client()
    result = client.query_bandwidth()
    if "error" in result:
        print(f"✗ {result['error']}")
    else:
        members = result.get("members", [])
        for m in members:
            icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(m["bandwidth"], "⚪")
            print(f"  {icon} {m['name']} — {m['bandwidth']} bandwidth "
                  f"({m['open_items']} items, {m['blockers']} blockers)")


def cmd_query_activity(args):
    """Recent team activity."""
    client = get_client()
    result = client.query_activity(args.hours)
    if "error" in result:
        print(f"✗ {result['error']}")
    else:
        nodes = result.get("nodes_updated", [])
        syncs = result.get("sync_events", [])
        print(f"Activity (last {args.hours}h): {len(nodes)} items, {len(syncs)} syncs")
        for n in nodes[:10]:
            print(f"  [{n.get('node_type')}] {n.get('name')} — by {n.get('member_name', '?')}")


def cmd_query_entity(args):
    """Get shared info about an entity."""
    client = get_client()
    name = " ".join(args.entity_name)
    result = client.query_entity(name)
    if "error" in result:
        print(f"✗ {result['error']}")
    else:
        nodes = result.get("nodes", [])
        edges = result.get("edges", [])
        if not nodes:
            print(f"No info found for '{name}'")
        else:
            print(f"Entity '{name}': {len(nodes)} nodes, {len(edges)} edges")
            for n in nodes:
                props = n.get("properties", {})
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except json.JSONDecodeError:
                        pass
                print(f"  [{n.get('node_type')}] {n.get('name')} — by {n.get('member_name', '?')}")
                if props:
                    for k, v in props.items():
                        print(f"    {k}: {v}")


def cmd_presence(args):
    """Show who's online."""
    client = get_client()
    members = client.presence.get_team_presence()
    print(client.presence.format_presence(members))


def main():
    parser = argparse.ArgumentParser(description="Percept Mesh — Team Agent Graph CLI")
    sub = parser.add_subparsers(dest="command")
    
    # server
    server_p = sub.add_parser("server")
    server_sub = server_p.add_subparsers(dest="server_cmd")
    start_p = server_sub.add_parser("start")
    start_p.add_argument("--port", type=int, default=None)
    server_sub.add_parser("stop")
    
    # team
    team_p = sub.add_parser("team")
    team_sub = team_p.add_subparsers(dest="team_cmd")
    create_p = team_sub.add_parser("create")
    create_p.add_argument("name")
    invite_p = team_sub.add_parser("invite")
    invite_p.add_argument("--role", default="member")
    invite_p.add_argument("--max-uses", type=int, default=1)
    invite_p.add_argument("--expires", type=int, default=72)
    join_p = team_sub.add_parser("join")
    join_p.add_argument("invite_key")
    join_p.add_argument("--name", default=None)
    team_sub.add_parser("members")
    remove_p = team_sub.add_parser("remove")
    remove_p.add_argument("member_id")
    
    # sync
    sync_p = sub.add_parser("sync")
    sync_sub = sync_p.add_subparsers(dest="sync_cmd")
    sync_sub.add_parser("push")
    sync_sub.add_parser("pull")
    auto_p = sync_sub.add_parser("auto")
    auto_p.add_argument("--interval", type=int, default=300)
    sync_sub.add_parser("status")
    
    # query
    query_p = sub.add_parser("query")
    query_sub = query_p.add_subparsers(dest="query_cmd")
    nl_p = query_sub.add_parser("nl", help="Natural language query")
    nl_p.add_argument("query_text", nargs="+")
    query_sub.add_parser("bandwidth")
    activity_p = query_sub.add_parser("activity")
    activity_p.add_argument("--hours", type=int, default=24)
    entity_p = query_sub.add_parser("entity")
    entity_p.add_argument("entity_name", nargs="+")
    
    # Also support: python cli.py query "text here" directly
    query_p.add_argument("query_text", nargs="*", default=[])
    
    # presence
    sub.add_parser("presence")
    
    args = parser.parse_args()
    
    if args.command == "server":
        if args.server_cmd == "start":
            cmd_server_start(args)
        elif args.server_cmd == "stop":
            cmd_server_stop(args)
        else:
            print("Usage: cli.py server [start|stop]")
    elif args.command == "team":
        if args.team_cmd == "create":
            cmd_team_create(args)
        elif args.team_cmd == "invite":
            cmd_team_invite(args)
        elif args.team_cmd == "join":
            cmd_team_join(args)
        elif args.team_cmd == "members":
            cmd_team_members(args)
        elif args.team_cmd == "remove":
            cmd_team_remove(args)
        else:
            print("Usage: cli.py team [create|invite|join|members|remove]")
    elif args.command == "sync":
        if args.sync_cmd == "push":
            cmd_sync_push(args)
        elif args.sync_cmd == "pull":
            cmd_sync_pull(args)
        elif args.sync_cmd == "auto":
            cmd_sync_auto(args)
        elif args.sync_cmd == "status":
            cmd_sync_status(args)
        else:
            print("Usage: cli.py sync [push|pull|auto|status]")
    elif args.command == "query":
        if args.query_cmd == "bandwidth":
            cmd_query_bandwidth(args)
        elif args.query_cmd == "activity":
            cmd_query_activity(args)
        elif args.query_cmd == "entity":
            cmd_query_entity(args)
        elif args.query_cmd == "nl":
            cmd_query(args)
        elif args.query_text:
            cmd_query(args)
        else:
            print("Usage: cli.py query [bandwidth|activity|entity <name>|nl <text>|\"<text>\"]")
    elif args.command == "presence":
        cmd_presence(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
