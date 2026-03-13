"""Agent-side client to sync with the team server."""
import json
import uuid
import requests
from datetime import datetime
from typing import Optional
from pathlib import Path

from percept.mesh.agent.share_policy import SharePolicy
from percept.mesh.agent.conflict import merge_node_lists, merge_edge_lists
from percept.mesh.agent.presence import PresenceManager


class MeshClient:
    """
    Client for an individual agent to interact with the Percept Mesh team server.
    Handles sync, presence, and queries.
    """
    
    def __init__(self, server_url: str, api_key: str, local_state_path: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.local_state_path = Path(local_state_path) if local_state_path else None
        self.last_sync: Optional[str] = None
        self.presence = PresenceManager(server_url, api_key)
        self._load_state()
    
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
    
    def _load_state(self):
        """Load last sync timestamp from local state file."""
        if self.local_state_path and self.local_state_path.exists():
            try:
                state = json.loads(self.local_state_path.read_text())
                self.last_sync = state.get("last_sync")
            except (json.JSONDecodeError, IOError):
                pass
    
    def _save_state(self):
        """Persist sync state locally."""
        if self.local_state_path:
            self.local_state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {"last_sync": self.last_sync}
            self.local_state_path.write_text(json.dumps(state))
    
    def push(self, nodes: list[dict], edges: list[dict] = None,
             approved_types: set[str] = None) -> dict:
        """
        Push local nodes/edges to the team graph.
        Applies share policy before sending.
        """
        edges = edges or []
        
        # Apply share policy
        shareable_nodes, blocked = SharePolicy.filter_nodes(nodes, approved_types)
        
        # Scrub sensitive properties
        scrubbed = [SharePolicy.scrub_properties(n) for n in shareable_nodes]
        
        if not scrubbed and not edges:
            return {"accepted_nodes": 0, "accepted_edges": 0, "blocked": len(blocked)}
        
        try:
            resp = requests.post(
                f"{self.server_url}/api/sync/push",
                json={"nodes": scrubbed, "edges": edges},
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            self.last_sync = datetime.utcnow().isoformat()
            self._save_state()
            result["blocked"] = len(blocked)
            return result
        except requests.RequestException as e:
            return {"error": str(e), "blocked": len(blocked)}
    
    def pull(self, since: Optional[str] = None) -> dict:
        """Pull updates from team graph since last sync."""
        params = {}
        sync_since = since or self.last_sync
        if sync_since:
            params["since"] = sync_since
        
        try:
            resp = requests.get(
                f"{self.server_url}/api/sync/pull",
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            self.last_sync = result.get("sync_timestamp", datetime.utcnow().isoformat())
            self._save_state()
            return result
        except requests.RequestException as e:
            return {"error": str(e), "nodes": [], "edges": []}
    
    def sync_status(self) -> dict:
        """Get sync health info."""
        try:
            resp = requests.get(
                f"{self.server_url}/api/sync/status",
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def query(self, query_text: str) -> dict:
        """Run a natural language query against the team graph."""
        try:
            resp = requests.post(
                f"{self.server_url}/api/query",
                json={"query": query_text},
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def query_blocked(self) -> dict:
        try:
            resp = requests.get(f"{self.server_url}/api/query/blocked",
                                headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def query_bandwidth(self) -> dict:
        try:
            resp = requests.get(f"{self.server_url}/api/query/bandwidth",
                                headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def query_activity(self, hours: int = 24) -> dict:
        try:
            resp = requests.get(f"{self.server_url}/api/query/activity",
                                params={"hours": hours},
                                headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def query_entity(self, name: str) -> dict:
        try:
            resp = requests.get(f"{self.server_url}/api/query/entity/{name}",
                                headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            return {"error": str(e)}
    
    def get_team_members(self) -> list[dict]:
        try:
            resp = requests.get(f"{self.server_url}/api/team/members",
                                headers=self._headers(), timeout=10)
            resp.raise_for_status()
            return resp.json().get("members", [])
        except requests.RequestException as e:
            return []
    
    def create_node(self, node_type: str, name: str, properties: dict = None) -> dict:
        """Helper to create a node dict with a UUID."""
        return {
            "id": str(uuid.uuid4()),
            "node_type": node_type,
            "name": name,
            "properties": properties or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
    
    def create_edge(self, source_id: str, target_id: str, edge_type: str,
                    properties: dict = None) -> dict:
        """Helper to create an edge dict with a UUID."""
        return {
            "id": str(uuid.uuid4()),
            "source_id": source_id,
            "target_id": target_id,
            "edge_type": edge_type,
            "properties": properties or {},
            "created_at": datetime.utcnow().isoformat(),
        }
