"""SQLite team graph storage."""
import sqlite3
import json
import uuid
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from percept.mesh.config import DB_PATH, DATA_DIR


def _ensure_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db():
    """Context manager for database connections."""
    _ensure_dir()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables."""
    _ensure_dir()
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS members (
                id TEXT PRIMARY KEY,
                team_id TEXT NOT NULL REFERENCES teams(id),
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                api_key TEXT UNIQUE NOT NULL,
                agent_id TEXT,
                last_seen TEXT,
                joined_at TEXT NOT NULL,
                revoked INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS invites (
                key TEXT PRIMARY KEY,
                team_id TEXT NOT NULL REFERENCES teams(id),
                role TEXT NOT NULL DEFAULT 'member',
                max_uses INTEGER DEFAULT 1,
                uses INTEGER DEFAULT 0,
                created_by TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                name TEXT NOT NULL,
                owner_id TEXT NOT NULL REFERENCES members(id),
                team_id TEXT NOT NULL REFERENCES teams(id),
                properties TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                owner_id TEXT NOT NULL REFERENCES members(id),
                team_id TEXT NOT NULL REFERENCES teams(id),
                properties TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                action TEXT NOT NULL,
                node_count INTEGER DEFAULT 0,
                edge_count INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS heartbeats (
                member_id TEXT PRIMARY KEY REFERENCES members(id),
                status TEXT DEFAULT 'online',
                last_heartbeat TEXT NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_nodes_team ON nodes(team_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_nodes_owner ON nodes(owner_id);
            CREATE INDEX IF NOT EXISTS idx_nodes_updated ON nodes(updated_at);
            CREATE INDEX IF NOT EXISTS idx_edges_team ON edges(team_id);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_sync_log_team ON sync_log(team_id, timestamp);
            CREATE INDEX IF NOT EXISTS idx_members_api_key ON members(api_key);
        """)


# --- Team Operations ---

def create_team(name: str) -> tuple[str, str, str]:
    """Create a team. Returns (team_id, admin_member_id, admin_api_key)."""
    team_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())
    api_key = f"pm_{secrets.token_urlsafe(32)}"
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute("INSERT INTO teams (id, name, created_at) VALUES (?, ?, ?)",
                      (team_id, name, now))
        conn.execute(
            "INSERT INTO members (id, team_id, name, role, api_key, joined_at) VALUES (?, ?, ?, ?, ?, ?)",
            (member_id, team_id, "admin", "admin", api_key, now)
        )
    return team_id, member_id, api_key


def create_invite(team_id: str, created_by: str, role: str = "member",
                   max_uses: int = 1, expires_hours: int = 72) -> tuple[str, str]:
    """Create an invite key. Returns (invite_key, expires_at)."""
    invite_key = f"inv_{secrets.token_urlsafe(16)}"
    now = datetime.utcnow()
    expires_at = (now + timedelta(hours=expires_hours)).isoformat()
    
    with get_db() as conn:
        conn.execute(
            "INSERT INTO invites (key, team_id, role, max_uses, created_by, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (invite_key, team_id, role, max_uses, created_by, expires_at, now.isoformat())
        )
    return invite_key, expires_at


def use_invite(invite_key: str, member_name: str, agent_id: Optional[str] = None) -> Optional[tuple[str, str, str, str]]:
    """Join a team with an invite key. Returns (member_id, api_key, role, team_name) or None."""
    now = datetime.utcnow()
    
    with get_db() as conn:
        inv = conn.execute("SELECT * FROM invites WHERE key = ?", (invite_key,)).fetchone()
        if not inv:
            return None
        
        # Check expiry
        if inv["expires_at"] and now.isoformat() > inv["expires_at"]:
            return None
        
        # Check uses
        if inv["max_uses"] > 0 and inv["uses"] >= inv["max_uses"]:
            return None
        
        team = conn.execute("SELECT name FROM teams WHERE id = ?", (inv["team_id"],)).fetchone()
        if not team:
            return None
        
        member_id = str(uuid.uuid4())
        api_key = f"pm_{secrets.token_urlsafe(32)}"
        
        conn.execute(
            "INSERT INTO members (id, team_id, name, role, api_key, agent_id, joined_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (member_id, inv["team_id"], member_name, inv["role"], api_key, agent_id, now.isoformat())
        )
        conn.execute("UPDATE invites SET uses = uses + 1 WHERE key = ?", (invite_key,))
        
        return member_id, api_key, inv["role"], team["name"]


def get_member_by_key(api_key: str) -> Optional[dict]:
    """Look up a member by API key."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT m.*, t.name as team_name FROM members m JOIN teams t ON m.team_id = t.id "
            "WHERE m.api_key = ? AND m.revoked = 0", (api_key,)
        ).fetchone()
        return dict(row) if row else None


def get_team_members(team_id: str) -> list[dict]:
    """Get all members of a team with presence info."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT m.id, m.name, m.role, m.agent_id, m.joined_at, m.last_seen, "
            "h.status, h.last_heartbeat "
            "FROM members m LEFT JOIN heartbeats h ON m.id = h.member_id "
            "WHERE m.team_id = ? AND m.revoked = 0", (team_id,)
        ).fetchall()
        
        now = datetime.utcnow()
        result = []
        for r in rows:
            status = "offline"
            last_seen = r["last_seen"]
            if r["last_heartbeat"]:
                hb_time = datetime.fromisoformat(r["last_heartbeat"])
                delta = (now - hb_time).total_seconds()
                if delta < 120:
                    status = "online"
                elif delta < 600:
                    status = "idle"
                last_seen = r["last_heartbeat"]
            
            result.append({
                "member_id": r["id"],
                "name": r["name"],
                "role": r["role"],
                "agent_id": r["agent_id"],
                "status": status,
                "last_seen": last_seen,
                "joined_at": r["joined_at"],
            })
        return result


def remove_member(team_id: str, member_id: str) -> bool:
    """Revoke a member's access."""
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE members SET revoked = 1 WHERE id = ? AND team_id = ? AND role != 'admin'",
            (member_id, team_id)
        )
        return cur.rowcount > 0


# --- Sync Operations ---

def upsert_nodes(team_id: str, owner_id: str, nodes: list[dict]) -> int:
    """Insert or update nodes. Returns count of accepted nodes."""
    now = datetime.utcnow().isoformat()
    count = 0
    with get_db() as conn:
        for n in nodes:
            props = json.dumps(n.get("properties", {}))
            created = n.get("created_at") or now
            updated = n.get("updated_at") or now
            conn.execute(
                "INSERT INTO nodes (id, node_type, name, owner_id, team_id, properties, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, properties=excluded.properties, "
                "updated_at=excluded.updated_at",
                (n["id"], n["node_type"], n["name"], owner_id, team_id,
                 props, created, updated)
            )
            count += 1
    return count


def upsert_edges(team_id: str, owner_id: str, edges: list[dict]) -> int:
    """Insert or update edges. Returns count."""
    now = datetime.utcnow().isoformat()
    count = 0
    with get_db() as conn:
        for e in edges:
            props = json.dumps(e.get("properties", {}))
            created = e.get("created_at") or now
            conn.execute(
                "INSERT INTO edges (id, source_id, target_id, edge_type, owner_id, team_id, properties, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET properties=excluded.properties",
                (e["id"], e["source_id"], e["target_id"], e["edge_type"],
                 owner_id, team_id, props, created)
            )
            count += 1
    return count


def log_sync(member_id: str, team_id: str, action: str, node_count: int, edge_count: int):
    """Log a sync event."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sync_log (member_id, team_id, action, node_count, edge_count, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (member_id, team_id, action, node_count, edge_count, datetime.utcnow().isoformat())
        )


def pull_updates(team_id: str, since: Optional[str] = None) -> tuple[list[dict], list[dict]]:
    """Pull nodes and edges updated since a timestamp."""
    with get_db() as conn:
        if since:
            nodes = conn.execute(
                "SELECT * FROM nodes WHERE team_id = ? AND updated_at > ? ORDER BY updated_at",
                (team_id, since)
            ).fetchall()
            edges = conn.execute(
                "SELECT * FROM edges WHERE team_id = ? AND created_at > ? ORDER BY created_at",
                (team_id, since)
            ).fetchall()
        else:
            nodes = conn.execute("SELECT * FROM nodes WHERE team_id = ? ORDER BY updated_at", (team_id,)).fetchall()
            edges = conn.execute("SELECT * FROM edges WHERE team_id = ? ORDER BY created_at", (team_id,)).fetchall()
        
        def row_to_dict(r):
            d = dict(r)
            if "properties" in d and isinstance(d["properties"], str):
                try:
                    d["properties"] = json.loads(d["properties"])
                except json.JSONDecodeError:
                    pass
            return d
        
        return [row_to_dict(n) for n in nodes], [row_to_dict(e) for e in edges]


def get_sync_status(team_id: str) -> list[dict]:
    """Get last sync info per member."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT member_id, action, MAX(timestamp) as last_sync, "
            "SUM(node_count) as total_nodes, SUM(edge_count) as total_edges "
            "FROM sync_log WHERE team_id = ? GROUP BY member_id, action ORDER BY last_sync DESC",
            (team_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# --- Presence ---

def update_heartbeat(member_id: str, status: str = "online"):
    """Update agent heartbeat."""
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO heartbeats (member_id, status, last_heartbeat) VALUES (?, ?, ?) "
            "ON CONFLICT(member_id) DO UPDATE SET status=excluded.status, last_heartbeat=excluded.last_heartbeat",
            (member_id, status, now)
        )
        conn.execute("UPDATE members SET last_seen = ? WHERE id = ?", (now, member_id))


def get_presence(team_id: str) -> list[dict]:
    """Get presence for all team members."""
    return get_team_members(team_id)  # Already includes presence


# --- Query Helpers ---

def query_blocked(team_id: str) -> list[dict]:
    """Find members with Blocker nodes."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT n.*, m.name as member_name FROM nodes n "
            "JOIN members m ON n.owner_id = m.id "
            "WHERE n.team_id = ? AND n.node_type = 'Blocker' "
            "ORDER BY n.updated_at DESC",
            (team_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def query_bandwidth(team_id: str) -> list[dict]:
    """Estimate bandwidth per member based on open items."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT m.id, m.name, "
            "COUNT(CASE WHEN n.node_type IN ('PR', 'Issue', 'Ticket') THEN 1 END) as open_items, "
            "COUNT(CASE WHEN n.node_type = 'Blocker' THEN 1 END) as blockers, "
            "COUNT(CASE WHEN n.node_type = 'Availability' THEN 1 END) as availability_nodes "
            "FROM members m LEFT JOIN nodes n ON m.id = n.owner_id AND n.team_id = m.team_id "
            "WHERE m.team_id = ? AND m.revoked = 0 "
            "GROUP BY m.id ORDER BY open_items ASC",
            (team_id,)
        ).fetchall()
        
        result = []
        for r in rows:
            d = dict(r)
            # Simple heuristic: fewer items = more bandwidth
            load = d["open_items"] + d["blockers"] * 2
            if load == 0:
                d["bandwidth"] = "high"
            elif load <= 3:
                d["bandwidth"] = "medium"
            else:
                d["bandwidth"] = "low"
            result.append(d)
        return result


def query_activity(team_id: str, hours: int = 24) -> list[dict]:
    """Get recent activity."""
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with get_db() as conn:
        nodes = conn.execute(
            "SELECT n.*, m.name as member_name FROM nodes n "
            "JOIN members m ON n.owner_id = m.id "
            "WHERE n.team_id = ? AND n.updated_at > ? ORDER BY n.updated_at DESC",
            (team_id, since)
        ).fetchall()
        syncs = conn.execute(
            "SELECT s.*, m.name as member_name FROM sync_log s "
            "JOIN members m ON s.member_id = m.id "
            "WHERE s.team_id = ? AND s.timestamp > ? ORDER BY s.timestamp DESC",
            (team_id, since)
        ).fetchall()
        return {
            "nodes_updated": [dict(r) for r in nodes],
            "sync_events": [dict(r) for r in syncs],
        }


def query_entity(team_id: str, name: str) -> dict:
    """Find all info about a named entity."""
    with get_db() as conn:
        # Search nodes by name (case-insensitive)
        nodes = conn.execute(
            "SELECT n.*, m.name as member_name FROM nodes n "
            "JOIN members m ON n.owner_id = m.id "
            "WHERE n.team_id = ? AND (n.name LIKE ? OR n.properties LIKE ?) "
            "ORDER BY n.updated_at DESC",
            (team_id, f"%{name}%", f"%{name}%")
        ).fetchall()
        
        node_ids = [r["id"] for r in nodes]
        edges = []
        if node_ids:
            placeholders = ",".join("?" * len(node_ids))
            edges = conn.execute(
                f"SELECT * FROM edges WHERE team_id = ? AND (source_id IN ({placeholders}) OR target_id IN ({placeholders}))",
                (team_id, *node_ids, *node_ids)
            ).fetchall()
        
        return {
            "nodes": [dict(r) for r in nodes],
            "edges": [dict(r) for r in edges],
        }


def query_decisions(team_id: str, hours: int = 24) -> list[dict]:
    """Get recent Decision nodes."""
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT n.*, m.name as member_name FROM nodes n "
            "JOIN members m ON n.owner_id = m.id "
            "WHERE n.team_id = ? AND n.node_type = 'Decision' AND n.updated_at > ? "
            "ORDER BY n.updated_at DESC",
            (team_id, since)
        ).fetchall()
        return [dict(r) for r in rows]


def query_open_tickets(team_id: str, min_hours: float = 0) -> list[dict]:
    """Find open tickets, optionally older than min_hours."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT n.*, m.name as member_name FROM nodes n "
            "JOIN members m ON n.owner_id = m.id "
            "WHERE n.team_id = ? AND n.node_type = 'Ticket' "
            "ORDER BY n.created_at ASC",
            (team_id,)
        ).fetchall()
        
        if min_hours > 0:
            cutoff = (datetime.utcnow() - timedelta(hours=min_hours)).isoformat()
            return [dict(r) for r in rows if r["created_at"] < cutoff]
        return [dict(r) for r in rows]


def query_pr_reviews(team_id: str, hours: int = 168) -> list[dict]:
    """Count PR review activity per member."""
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT m.name, COUNT(e.id) as review_count FROM edges e "
            "JOIN members m ON e.owner_id = m.id "
            "WHERE e.team_id = ? AND e.edge_type = 'reviews' AND e.created_at > ? "
            "GROUP BY m.id ORDER BY review_count DESC",
            (team_id, since)
        ).fetchall()
        return [dict(r) for r in rows]
