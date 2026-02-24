#!/usr/bin/env python3
"""Percept MCP Server — expose Percept as native Claude/Anthropic tools.

Run standalone:
    python -m src.mcp_server

Or via CLI:
    percept mcp
"""

import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Ensure project root is on path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database import PerceptDB

# ── Server Setup ───────────────────────────────────────────────────────

mcp = FastMCP(
    name="percept",
    instructions=(
        "Percept is an ambient voice intelligence system. Use these tools to "
        "search conversations, check transcripts, view speakers, monitor "
        "pipeline health, and access voice command history."
    ),
)

DATA_DIR = BASE_DIR / "data"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
LIVE_FILE = Path("/tmp/percept-live.txt")


def _get_db() -> PerceptDB:
    """Get a PerceptDB instance."""
    return PerceptDB()


# ── Tools ──────────────────────────────────────────────────────────────


@mcp.tool()
def percept_search(query: str, limit: int = 10) -> str:
    """Search conversations using FTS5 full-text search.

    Use this to find specific topics, names, or phrases mentioned in past conversations.
    Returns matching utterances with highlighted snippets.

    Args:
        query: Search query (supports FTS5 syntax like AND, OR, NOT, phrases)
        limit: Maximum results to return (default 10)
    """
    db = _get_db()
    try:
        results = db.search_utterances(query, limit=limit)
        if not results:
            # Fall back to conversation-level search
            convos = db.get_conversations(search=query, limit=limit)
            return json.dumps({
                "query": query,
                "result_count": len(convos),
                "results": [
                    {
                        "id": c["id"],
                        "date": c.get("date"),
                        "speakers": c.get("speakers"),
                        "summary": (c.get("summary") or "")[:300],
                        "snippet": (c.get("transcript") or "")[:200],
                    }
                    for c in convos
                ],
            })
        return json.dumps({
            "query": query,
            "result_count": len(results),
            "results": [
                {
                    "text": r.get("text"),
                    "highlighted": r.get("highlighted"),
                    "speaker_id": r.get("speaker_id"),
                    "conversation_id": r.get("conversation_id"),
                    "started_at": r.get("started_at"),
                }
                for r in results
            ],
        })
    finally:
        db.close()


@mcp.tool()
def percept_transcripts(today_only: bool = False, limit: int = 20) -> str:
    """List recent conversation transcripts.

    Returns transcripts from the database with metadata like date, speakers, word count.

    Args:
        today_only: If True, only return today's transcripts
        limit: Maximum transcripts to return (default 20)
    """
    db = _get_db()
    try:
        date_filter = date.today().strftime("%Y-%m-%d") if today_only else None
        convos = db.get_conversations(date=date_filter, limit=limit)
        return json.dumps({
            "count": len(convos),
            "today_only": today_only,
            "transcripts": [
                {
                    "id": c["id"],
                    "date": c.get("date"),
                    "duration_seconds": c.get("duration_seconds"),
                    "word_count": c.get("word_count"),
                    "speakers": c.get("speakers"),
                    "topics": c.get("topics"),
                    "summary": c.get("summary"),
                    "transcript_preview": (c.get("transcript") or "")[:500],
                }
                for c in convos
            ],
        })
    finally:
        db.close()


@mcp.tool()
def percept_actions(limit: int = 20) -> str:
    """List voice command/action history.

    Shows commands that were detected, parsed, and dispatched from voice input.
    Includes intent, parameters, status, and execution results.

    Args:
        limit: Maximum actions to return (default 20)
    """
    db = _get_db()
    try:
        actions = db.get_actions(limit=limit)
        return json.dumps({
            "count": len(actions),
            "actions": [
                {
                    "id": a["id"],
                    "timestamp": a.get("timestamp"),
                    "intent": a.get("intent"),
                    "params": a.get("params"),
                    "raw_text": a.get("raw_text"),
                    "status": a.get("status"),
                    "result": a.get("result"),
                }
                for a in actions
            ],
        })
    finally:
        db.close()


@mcp.tool()
def percept_speakers() -> str:
    """List all known speakers with word counts and activity.

    Returns speaker profiles including total words spoken, segment counts,
    and authorization status.
    """
    db = _get_db()
    try:
        speakers = db.get_speakers()
        authorized = {s["speaker_id"] for s in db.get_authorized_speakers()}
        return json.dumps({
            "count": len(speakers),
            "speakers": [
                {
                    "id": s["id"],
                    "name": s.get("name"),
                    "total_words": s.get("total_words", 0),
                    "total_segments": s.get("total_segments", 0),
                    "first_seen": s.get("first_seen"),
                    "last_seen": s.get("last_seen"),
                    "relationship": s.get("relationship"),
                    "authorized": s["id"] in authorized,
                }
                for s in speakers
            ],
        })
    finally:
        db.close()


@mcp.tool()
def percept_status() -> str:
    """Check Percept pipeline health status.

    Returns server status, live stream status, today's conversation stats,
    and data audit information.
    """
    return json.dumps(_get_status())


def _get_status() -> dict:
    """Build status dict (shared by tool and resource)."""
    from urllib.request import urlopen

    # Server health
    server_status = "not_running"
    uptime = None
    try:
        resp = urlopen("http://localhost:8900/health", timeout=2)
        health = json.loads(resp.read())
        server_status = "running"
        uptime = health.get("uptime")
    except Exception:
        pass

    # Live stream
    live_status = "no_data"
    live_age = None
    if LIVE_FILE.exists():
        age = time.time() - LIVE_FILE.stat().st_mtime
        live_age = round(age, 1)
        live_status = "active" if age < 120 else "stale"

    # Today's stats
    db = _get_db()
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        convos = db.get_conversations(date=today_str, limit=1000)
        total_words = sum(c.get("word_count") or 0 for c in convos)
        audit = db.audit()
    finally:
        db.close()

    return {
        "server": server_status,
        "uptime_seconds": uptime,
        "live_stream": live_status,
        "live_stream_age_seconds": live_age,
        "today": {
            "conversations": len(convos),
            "words": total_words,
        },
        "database": audit,
    }


@mcp.tool()
def percept_security_log(limit: int = 20) -> str:
    """View security log — blocked attempts and unauthorized access events.

    Shows events like unauthorized speakers, invalid webhook auth,
    and injection detection attempts.

    Args:
        limit: Maximum events to return (default 20)
    """
    db = _get_db()
    try:
        events = db.get_security_log(limit=limit)
        return json.dumps({
            "count": len(events),
            "events": [
                {
                    "timestamp": e.get("timestamp"),
                    "speaker_id": e.get("speaker_id"),
                    "reason": e.get("reason"),
                    "transcript_snippet": e.get("transcript_snippet"),
                    "details": e.get("details"),
                }
                for e in events
            ],
        })
    finally:
        db.close()


@mcp.tool()
def percept_conversations(limit: int = 20) -> str:
    """List recent conversations with summaries.

    Returns conversation metadata including duration, speakers, topics,
    and AI-generated summaries.

    Args:
        limit: Maximum conversations to return (default 20)
    """
    db = _get_db()
    try:
        convos = db.get_conversations(limit=limit)
        return json.dumps({
            "count": len(convos),
            "conversations": [
                {
                    "id": c["id"],
                    "date": c.get("date"),
                    "duration_seconds": c.get("duration_seconds"),
                    "word_count": c.get("word_count"),
                    "segment_count": c.get("segment_count"),
                    "speakers": c.get("speakers"),
                    "topics": c.get("topics"),
                    "summary": c.get("summary"),
                }
                for c in convos
            ],
        })
    finally:
        db.close()


@mcp.tool()
def percept_listen(limit: int = 50) -> str:
    """Get latest live transcript events from the real-time stream.

    Reads the live transcript file that the audio pipeline writes to.
    Useful for seeing what's being said right now.

    Args:
        limit: Maximum lines to return (default 50)
    """
    if not LIVE_FILE.exists():
        return json.dumps({"status": "no_data", "events": []})

    age = time.time() - LIVE_FILE.stat().st_mtime
    try:
        lines = LIVE_FILE.read_text().strip().split("\n")
        lines = lines[-limit:]
    except Exception:
        lines = []

    return json.dumps({
        "status": "active" if age < 120 else "stale",
        "age_seconds": round(age, 1),
        "event_count": len(lines),
        "events": lines,
    })


# ── Resources ──────────────────────────────────────────────────────────


@mcp.resource("percept://status")
def resource_status() -> str:
    """Current Percept pipeline status including server health and today's stats."""
    return json.dumps(_get_status())


@mcp.resource("percept://speakers")
def resource_speakers() -> str:
    """List of all known speakers with word counts and authorization status."""
    db = _get_db()
    try:
        speakers = db.get_speakers()
        return json.dumps([
            {
                "id": s["id"],
                "name": s.get("name"),
                "total_words": s.get("total_words", 0),
                "relationship": s.get("relationship"),
            }
            for s in speakers
        ])
    finally:
        db.close()


# ── Entry Point ────────────────────────────────────────────────────────


def run():
    """Run the MCP server (stdio transport for Claude Desktop)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
