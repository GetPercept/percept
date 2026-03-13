"""FastAPI team graph server."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager

from percept.mesh.server.database import init_db, create_team, create_invite, use_invite, get_team_members, remove_member, update_heartbeat, get_presence
from percept.mesh.server.auth import get_current_member, require_admin, require_write
from percept.mesh.server.models import (
    TeamCreateRequest, TeamCreateResponse,
    InviteCreateRequest, InviteResponse,
    JoinRequest, JoinResponse,
    HeartbeatRequest, PresenceInfo,
)
from percept.mesh.server.sync import router as sync_router
from percept.mesh.server.query import router as query_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Percept Mesh — Team Agent Graph",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(sync_router)
app.include_router(query_router)


# --- Health ---
@app.get("/health")
async def health():
    return {"status": "ok", "service": "percept-mesh"}


# --- Team Management ---
@app.post("/api/team/create", response_model=TeamCreateResponse)
async def api_team_create(req: TeamCreateRequest):
    """Create a new team. Returns admin API key."""
    team_id, member_id, api_key = create_team(req.name)
    return TeamCreateResponse(team_id=team_id, name=req.name, admin_api_key=api_key)


@app.post("/api/team/invite", response_model=InviteResponse)
async def api_team_invite(req: InviteCreateRequest, member: dict = Depends(require_admin)):
    """Generate an invite key (admin only)."""
    invite_key, expires_at = create_invite(
        member["team_id"], member["id"],
        role=req.role, max_uses=req.max_uses, expires_hours=req.expires_hours
    )
    return InviteResponse(
        invite_key=invite_key, role=req.role,
        max_uses=req.max_uses, expires_at=expires_at
    )


@app.post("/api/team/join", response_model=JoinResponse)
async def api_team_join(req: JoinRequest):
    """Join a team with an invite key."""
    result = use_invite(req.invite_key, req.member_name, req.agent_id)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid, expired, or used invite key")
    
    member_id, api_key, role, team_name = result
    return JoinResponse(member_id=member_id, api_key=api_key, role=role, team_name=team_name)


@app.get("/api/team/members")
async def api_team_members(member: dict = Depends(get_current_member)):
    """List team members with presence."""
    return {"members": get_team_members(member["team_id"])}


@app.delete("/api/team/members/{member_id}")
async def api_team_remove(member_id: str, admin: dict = Depends(require_admin)):
    """Remove a member (admin only)."""
    if not remove_member(admin["team_id"], member_id):
        raise HTTPException(status_code=404, detail="Member not found or cannot remove admin")
    return {"removed": member_id}


# --- Presence ---
@app.get("/api/presence")
async def api_presence(member: dict = Depends(get_current_member)):
    """Get all agents' online/offline status."""
    return {"presence": get_presence(member["team_id"])}


@app.post("/api/presence/heartbeat")
async def api_heartbeat(req: HeartbeatRequest, member: dict = Depends(get_current_member)):
    """Agent heartbeat — I'm alive."""
    update_heartbeat(member["id"], req.status)
    return {"ok": True, "member_id": member["id"], "status": req.status}


if __name__ == "__main__":
    import uvicorn
    from percept.mesh.config import DEFAULT_PORT, DEFAULT_HOST
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)
