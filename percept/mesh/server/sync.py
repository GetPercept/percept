"""Sync endpoints: receive and serve sync events from agents."""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from percept.mesh.server.auth import get_current_member, require_write
from percept.mesh.server.models import SyncPushRequest, SyncPushResponse, SyncPullResponse
from percept.mesh.server.database import upsert_nodes, upsert_edges, log_sync, pull_updates, get_sync_status

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/push", response_model=SyncPushResponse)
async def sync_push(req: SyncPushRequest, member: dict = Depends(require_write)):
    """Agent pushes shared nodes/edges to the team graph."""
    team_id = member["team_id"]
    member_id = member["id"]
    
    node_dicts = [n.model_dump() for n in req.nodes]
    edge_dicts = [e.model_dump() for e in req.edges]
    
    accepted_nodes = upsert_nodes(team_id, member_id, node_dicts)
    accepted_edges = upsert_edges(team_id, member_id, edge_dicts)
    
    log_sync(member_id, team_id, "push", accepted_nodes, accepted_edges)
    
    return SyncPushResponse(
        accepted_nodes=accepted_nodes,
        accepted_edges=accepted_edges,
        conflicts=[]
    )


@router.get("/pull", response_model=SyncPullResponse)
async def sync_pull(
    since: Optional[str] = Query(None, description="ISO timestamp to pull updates from"),
    member: dict = Depends(get_current_member)
):
    """Agent pulls team graph updates since last sync."""
    team_id = member["team_id"]
    
    nodes, edges = pull_updates(team_id, since)
    
    log_sync(member["id"], team_id, "pull", len(nodes), len(edges))
    
    return SyncPullResponse(
        nodes=nodes,
        edges=edges,
        sync_timestamp=datetime.utcnow().isoformat()
    )


@router.get("/status")
async def sync_status(member: dict = Depends(get_current_member)):
    """Show sync health and last sync times per member."""
    return {"status": get_sync_status(member["team_id"])}
