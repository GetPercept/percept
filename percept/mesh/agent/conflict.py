"""Last-write-wins merge resolution for sync conflicts."""
from datetime import datetime
from typing import Optional


def resolve_node_conflict(local: dict, remote: dict) -> dict:
    """
    Resolve a conflict between local and remote versions of a node.
    Strategy: Last-write-wins based on updated_at timestamp.
    
    Returns the winning version.
    """
    local_time = local.get("updated_at", "")
    remote_time = remote.get("updated_at", "")
    
    if not local_time:
        return remote
    if not remote_time:
        return local
    
    # Parse and compare
    try:
        local_dt = datetime.fromisoformat(local_time)
        remote_dt = datetime.fromisoformat(remote_time)
        return remote if remote_dt >= local_dt else local
    except (ValueError, TypeError):
        # If timestamps are unparseable, prefer remote (server is source of truth)
        return remote


def resolve_edge_conflict(local: dict, remote: dict) -> dict:
    """
    Resolve edge conflict. Edges are simpler — last-write-wins on created_at.
    """
    local_time = local.get("created_at", "")
    remote_time = remote.get("created_at", "")
    
    if not remote_time:
        return local
    if not local_time:
        return remote
    
    try:
        local_dt = datetime.fromisoformat(local_time)
        remote_dt = datetime.fromisoformat(remote_time)
        return remote if remote_dt >= local_dt else local
    except (ValueError, TypeError):
        return remote


def merge_node_lists(local_nodes: list[dict], remote_nodes: list[dict]) -> list[dict]:
    """
    Merge two lists of nodes, resolving conflicts with LWW.
    Returns merged list.
    """
    by_id = {}
    
    for node in local_nodes:
        by_id[node["id"]] = node
    
    for node in remote_nodes:
        nid = node["id"]
        if nid in by_id:
            by_id[nid] = resolve_node_conflict(by_id[nid], node)
        else:
            by_id[nid] = node
    
    return list(by_id.values())


def merge_edge_lists(local_edges: list[dict], remote_edges: list[dict]) -> list[dict]:
    """
    Merge two lists of edges, resolving conflicts with LWW.
    """
    by_id = {}
    
    for edge in local_edges:
        by_id[edge["id"]] = edge
    
    for edge in remote_edges:
        eid = edge["id"]
        if eid in by_id:
            by_id[eid] = resolve_edge_conflict(by_id[eid], edge)
        else:
            by_id[eid] = edge
    
    return list(by_id.values())
