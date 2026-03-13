"""Pydantic models for API request/response validation."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Team ---
class TeamCreateRequest(BaseModel):
    name: str
    
class TeamCreateResponse(BaseModel):
    team_id: str
    name: str
    admin_api_key: str

class InviteCreateRequest(BaseModel):
    role: str = "member"           # member or readonly
    max_uses: int = 1              # 0 = unlimited
    expires_hours: int = 72        # hours until expiry

class InviteResponse(BaseModel):
    invite_key: str
    role: str
    max_uses: int
    expires_at: str

class JoinRequest(BaseModel):
    invite_key: str
    member_name: str
    agent_id: Optional[str] = None  # Optional agent identifier

class JoinResponse(BaseModel):
    member_id: str
    api_key: str
    role: str
    team_name: str

class MemberInfo(BaseModel):
    member_id: str
    name: str
    role: str
    agent_id: Optional[str] = None
    status: str = "offline"         # online/idle/offline
    last_seen: Optional[str] = None
    joined_at: str = ""


# --- Sync ---
class NodePayload(BaseModel):
    id: str
    node_type: str
    name: str
    properties: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class EdgePayload(BaseModel):
    id: str
    source_id: str
    target_id: str
    edge_type: str
    properties: dict = Field(default_factory=dict)
    created_at: Optional[str] = None

class SyncPushRequest(BaseModel):
    nodes: list[NodePayload] = Field(default_factory=list)
    edges: list[EdgePayload] = Field(default_factory=list)

class SyncPushResponse(BaseModel):
    accepted_nodes: int
    accepted_edges: int
    conflicts: list[str] = Field(default_factory=list)

class SyncPullResponse(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    sync_timestamp: str


# --- Query ---
class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    results: list[dict] = Field(default_factory=list)

class ActivityResponse(BaseModel):
    events: list[dict] = Field(default_factory=list)
    period_hours: int = 24


# --- Presence ---
class HeartbeatRequest(BaseModel):
    status: str = "online"  # online, idle

class PresenceInfo(BaseModel):
    member_id: str
    name: str
    status: str
    last_seen: str
