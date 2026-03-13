"""Team graph query engine."""
from fastapi import APIRouter, Depends, Query
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from percept.mesh.server.auth import get_current_member
from percept.mesh.server.models import QueryRequest, QueryResponse
from percept.mesh.server import database as db

router = APIRouter(prefix="/api/query", tags=["query"])


def _natural_language_query(team_id: str, query: str) -> dict:
    """Route natural language queries to the right database function."""
    q = query.lower().strip()
    
    if any(k in q for k in ["blocked", "blocker", "stuck"]):
        results = db.query_blocked(team_id)
        if not results:
            return {"answer": "No one is currently blocked.", "results": []}
        names = list(set(r.get("member_name", "unknown") for r in results))
        blockers = [r.get("name", "") for r in results]
        return {
            "answer": f"Blocked: {', '.join(names)}. Blockers: {'; '.join(blockers)}",
            "results": results
        }
    
    if any(k in q for k in ["bandwidth", "available", "capacity", "free"]):
        results = db.query_bandwidth(team_id)
        high = [r["name"] for r in results if r["bandwidth"] == "high"]
        answer = f"Members with bandwidth: {', '.join(high)}" if high else "Everyone appears loaded."
        return {"answer": answer, "results": results}
    
    if any(k in q for k in ["decision", "decided"]):
        hours = 24
        for word in q.split():
            if word.isdigit():
                hours = int(word)
        results = db.query_decisions(team_id, hours)
        if not results:
            return {"answer": f"No decisions recorded in the last {hours} hours.", "results": []}
        decisions = [r.get("name", "") for r in results]
        return {"answer": f"Decisions ({len(results)}): {'; '.join(decisions)}", "results": results}
    
    if any(k in q for k in ["ticket", "support"]):
        min_hours = 0
        if "4 hour" in q or "over 4" in q:
            min_hours = 4
        results = db.query_open_tickets(team_id, min_hours)
        if not results:
            return {"answer": "No matching open tickets.", "results": []}
        return {"answer": f"Found {len(results)} open ticket(s).", "results": results}
    
    if any(k in q for k in ["review", "pr", "pull request"]):
        results = db.query_pr_reviews(team_id)
        if not results:
            return {"answer": "No PR reviews found this week.", "results": []}
        top = results[0]
        return {
            "answer": f"Top reviewer: {top['name']} ({top['review_count']} reviews)",
            "results": results
        }
    
    if any(k in q for k in ["activity", "recent", "happening", "going on"]):
        hours = 24
        for word in q.split():
            if word.isdigit():
                hours = int(word)
        results = db.query_activity(team_id, hours)
        node_count = len(results.get("nodes_updated", []))
        sync_count = len(results.get("sync_events", []))
        return {
            "answer": f"Last {hours}h: {node_count} items updated, {sync_count} sync events.",
            "results": [results]
        }
    
    if any(k in q for k in ["status", "project"]):
        # Try to find entity name in query
        words = q.replace("?", "").replace("what's", "").replace("the", "").replace("status", "").replace("of", "").replace("project", "").strip()
        if words:
            results = db.query_entity(team_id, words)
            node_count = len(results.get("nodes", []))
            return {
                "answer": f"Found {node_count} items related to '{words}'.",
                "results": [results]
            }
    
    # Fallback: try entity search
    results = db.query_entity(team_id, q)
    node_count = len(results.get("nodes", []))
    if node_count > 0:
        return {"answer": f"Found {node_count} items matching '{q}'.", "results": [results]}
    
    return {"answer": f"No results found for: {q}", "results": []}


@router.post("")
async def query_natural(req: QueryRequest, member: dict = Depends(get_current_member)):
    """Natural language team query."""
    result = _natural_language_query(member["team_id"], req.query)
    return QueryResponse(**result)


@router.get("/blocked")
async def query_blocked(member: dict = Depends(get_current_member)):
    """Who's blocked?"""
    results = db.query_blocked(member["team_id"])
    return {"blocked": results}


@router.get("/bandwidth")
async def query_bandwidth(member: dict = Depends(get_current_member)):
    """Who has bandwidth?"""
    results = db.query_bandwidth(member["team_id"])
    return {"members": results}


@router.get("/activity")
async def query_activity(
    hours: int = Query(24, description="Hours to look back"),
    member: dict = Depends(get_current_member)
):
    """Recent team activity."""
    return db.query_activity(member["team_id"], hours)


@router.get("/entity/{name}")
async def query_entity(name: str, member: dict = Depends(get_current_member)):
    """Get shared info about an entity."""
    return db.query_entity(member["team_id"], name)
