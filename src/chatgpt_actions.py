#!/usr/bin/env python3
"""Percept ChatGPT Actions API — OpenAPI-compatible REST endpoints for Custom GPTs.

This exposes the same Percept intelligence that the MCP server provides,
but via a standard REST API that ChatGPT Custom GPTs can consume as Actions.

Run standalone:
    python -m src.chatgpt_actions --port 8901

Or via CLI:
    percept chatgpt-api
"""

import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database import PerceptDB

# ── Config ─────────────────────────────────────────────────────────────

API_TOKEN = os.environ.get("PERCEPT_API_TOKEN", "")
OPENAPI_TITLE = "Percept — Voice Intelligence for AI"
OPENAPI_VERSION = "1.0.0"
OPENAPI_DESCRIPTION = (
    "Search and query your meeting transcripts, voice commands, speakers, "
    "and conversation history captured by Percept. Connect this to any "
    "Custom GPT to give ChatGPT access to your real-world conversations."
)

# ── App ────────────────────────────────────────────────────────────────

app = FastAPI(
    title=OPENAPI_TITLE,
    version=OPENAPI_VERSION,
    description=OPENAPI_DESCRIPTION,
    servers=[{"url": "https://percept.clawdoor.com", "description": "Percept API"}],
)

security = HTTPBearer(auto_error=False)


def _check_auth(credentials: HTTPAuthorizationCredentials | None):
    """Validate bearer token if PERCEPT_API_TOKEN is set."""
    if not API_TOKEN:
        return  # No auth configured
    if not credentials or credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def _get_db() -> PerceptDB:
    return PerceptDB()


# ── Response Models ────────────────────────────────────────────────────


class SearchResult(BaseModel):
    text: str | None = None
    highlighted: str | None = None
    speaker_id: str | None = None
    conversation_id: str | None = None
    started_at: str | None = None


class SearchResponse(BaseModel):
    query: str
    result_count: int
    results: list[SearchResult]


class TranscriptItem(BaseModel):
    id: str
    date: str | None = None
    duration_seconds: float | None = None
    word_count: int | None = None
    speakers: str | None = None
    topics: str | None = None
    summary: str | None = None
    transcript_preview: str | None = None


class TranscriptsResponse(BaseModel):
    count: int
    today_only: bool
    transcripts: list[TranscriptItem]


class SpeakerItem(BaseModel):
    id: str
    name: str | None = None
    total_words: int = 0
    total_segments: int = 0
    first_seen: str | None = None
    last_seen: str | None = None
    relationship: str | None = None


class SpeakersResponse(BaseModel):
    count: int
    speakers: list[SpeakerItem]


class EntityItem(BaseModel):
    name: str
    entity_type: str | None = None
    mention_count: int = 0
    last_mentioned: str | None = None


class EntitiesResponse(BaseModel):
    query: str | None
    count: int
    entities: list[EntityItem]


class StatusResponse(BaseModel):
    server: str
    uptime_seconds: float | None = None
    today_conversations: int = 0
    today_words: int = 0
    total_conversations: int = 0
    total_speakers: int = 0


# ── Endpoints ──────────────────────────────────────────────────────────


@app.get("/api/search", response_model=SearchResponse, tags=["Search"])
def search_conversations(
    q: str = Query(..., description="Search query (FTS5 syntax: AND, OR, NOT, phrases)"),
    limit: int = Query(10, ge=1, le=50),
    credentials: HTTPAuthorizationCredentials | None = Security(security),
):
    """Search all captured conversations for specific topics, names, or phrases."""
    _check_auth(credentials)
    db = _get_db()
    try:
        results = db.search_utterances(q, limit=limit)
        if not results:
            convos = db.get_conversations(search=q, limit=limit)
            return SearchResponse(
                query=q,
                result_count=len(convos),
                results=[
                    SearchResult(
                        text=(c.get("summary") or "")[:300],
                        conversation_id=c["id"],
                        started_at=c.get("date"),
                        speaker_id=c.get("speakers"),
                    )
                    for c in convos
                ],
            )
        return SearchResponse(
            query=q,
            result_count=len(results),
            results=[
                SearchResult(
                    text=r.get("text"),
                    highlighted=r.get("highlighted"),
                    speaker_id=r.get("speaker_id"),
                    conversation_id=r.get("conversation_id"),
                    started_at=r.get("started_at"),
                )
                for r in results
            ],
        )
    finally:
        db.close()


@app.get("/api/transcripts", response_model=TranscriptsResponse, tags=["Transcripts"])
def list_transcripts(
    today_only: bool = Query(False, description="Only return today's transcripts"),
    limit: int = Query(20, ge=1, le=100),
    credentials: HTTPAuthorizationCredentials | None = Security(security),
):
    """List recent conversation transcripts with metadata."""
    _check_auth(credentials)
    db = _get_db()
    try:
        date_filter = date.today().strftime("%Y-%m-%d") if today_only else None
        convos = db.get_conversations(date=date_filter, limit=limit)
        return TranscriptsResponse(
            count=len(convos),
            today_only=today_only,
            transcripts=[
                TranscriptItem(
                    id=c["id"],
                    date=c.get("date"),
                    duration_seconds=c.get("duration_seconds"),
                    word_count=c.get("word_count"),
                    speakers=c.get("speakers"),
                    topics=c.get("topics"),
                    summary=c.get("summary"),
                    transcript_preview=(c.get("transcript") or "")[:500],
                )
                for c in convos
            ],
        )
    finally:
        db.close()


@app.get("/api/speakers", response_model=SpeakersResponse, tags=["Speakers"])
def list_speakers(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
):
    """List all known speakers with activity stats."""
    _check_auth(credentials)
    db = _get_db()
    try:
        speakers = db.get_speakers()
        return SpeakersResponse(
            count=len(speakers),
            speakers=[
                SpeakerItem(
                    id=s["id"],
                    name=s.get("name"),
                    total_words=s.get("total_words", 0),
                    total_segments=s.get("total_segments", 0),
                    first_seen=s.get("first_seen"),
                    last_seen=s.get("last_seen"),
                    relationship=s.get("relationship"),
                )
                for s in speakers
            ],
        )
    finally:
        db.close()


@app.get("/api/entities", response_model=EntitiesResponse, tags=["Entities"])
def list_entities(
    q: str | None = Query(None, description="Filter entities by name"),
    limit: int = Query(50, ge=1, le=200),
    credentials: HTTPAuthorizationCredentials | None = Security(security),
):
    """List extracted entities (people, companies, topics) from conversations."""
    _check_auth(credentials)
    db = _get_db()
    try:
        entities = db.get_entities(search=q, limit=limit) if hasattr(db, "get_entities") else []
        return EntitiesResponse(
            query=q,
            count=len(entities),
            entities=[
                EntityItem(
                    name=e.get("name", ""),
                    entity_type=e.get("entity_type"),
                    mention_count=e.get("mention_count", 0),
                    last_mentioned=e.get("last_mentioned"),
                )
                for e in entities
            ],
        )
    finally:
        db.close()


@app.get("/api/status", response_model=StatusResponse, tags=["Status"])
def get_status(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
):
    """Check Percept pipeline health and stats."""
    _check_auth(credentials)
    from urllib.request import urlopen

    server_status = "not_running"
    uptime = None
    try:
        resp = urlopen("http://localhost:8900/health", timeout=2)
        health = json.loads(resp.read())
        server_status = "running"
        uptime = health.get("uptime")
    except Exception:
        pass

    db = _get_db()
    try:
        today_str = date.today().strftime("%Y-%m-%d")
        convos = db.get_conversations(date=today_str, limit=1000)
        total_words = sum(c.get("word_count") or 0 for c in convos)
        audit = db.audit()
    finally:
        db.close()

    return StatusResponse(
        server=server_status,
        uptime_seconds=uptime,
        today_conversations=len(convos),
        today_words=total_words,
        total_conversations=audit.get("conversations", 0),
        total_speakers=audit.get("speakers", 0),
    )


# ── OpenAPI Schema Export ──────────────────────────────────────────────


def export_openapi_schema(output_path: str | None = None) -> dict:
    """Export the OpenAPI schema for ChatGPT Custom GPT Actions import."""
    schema = app.openapi()
    if output_path:
        with open(output_path, "w") as f:
            json.dump(schema, f, indent=2)
    return schema


# ── CLI Entry ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Percept ChatGPT Actions API")
    parser.add_argument("--port", type=int, default=8901, help="Port (default 8901)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--export-schema", type=str, help="Export OpenAPI schema to file and exit")
    args = parser.parse_args()

    if args.export_schema:
        export_openapi_schema(args.export_schema)
        print(f"Schema exported to {args.export_schema}")
        sys.exit(0)

    uvicorn.run(app, host=args.host, port=args.port)
