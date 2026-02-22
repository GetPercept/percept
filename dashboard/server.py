"""Percept Dashboard API Server — port 8960 (SQLite-backed)"""
import os, re, json, time, datetime, uuid
from pathlib import Path
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
import uvicorn, httpx

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.database import PerceptDB

app = FastAPI(title="Percept Dashboard API")

BASE = Path("/Users/jarvis/.openclaw/workspace/percept")
DATA = BASE / "data"
LIVE_TXT = Path("/tmp/percept-live.txt")
DASHBOARD_HTML = Path(__file__).parent / "index.html"
START_TIME = time.time()

db = PerceptDB(str(DATA / "percept.db"))


@app.get("/")
async def dashboard():
    return FileResponse(DASHBOARD_HTML, media_type="text/html")


@app.get("/api/health")
async def health():
    uptime = time.time() - START_TIME
    percept_ok = False
    percept_data = {}
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get("http://localhost:8900/health")
            if r.status_code == 200:
                percept_ok = True
                percept_data = r.json()
    except:
        pass
    # DB status
    try:
        conv_count = len(db.get_conversations(limit=1))
        db_ok = True
    except:
        db_ok = False
        conv_count = 0
    return {
        "dashboard_uptime": uptime,
        "percept_online": percept_ok,
        "percept": percept_data,
        "db_ok": db_ok,
    }


@app.get("/api/conversations")
async def conversations(date: str = None, limit: int = 50, search: str = None):
    return db.get_conversations(date=date, limit=limit, search=search)


@app.get("/api/conversations/{conv_id}")
async def conversation_detail(conv_id: str):
    c = db.get_conversation(conv_id)
    if c:
        return c
    return {"error": "not found"}


@app.get("/api/summaries")
async def summaries():
    convs = db.get_conversations(limit=200)
    results = []
    for c in convs:
        if c.get("summary") or c.get("summary_file_path"):
            # Load summary from file if not inline
            if not c.get("summary") and c.get("summary_file_path"):
                sfp = Path(c["summary_file_path"])
                if not sfp.is_absolute():
                    sfp = DATA / sfp
                if sfp.exists():
                    try:
                        c["summary"] = sfp.read_text().strip()
                    except Exception:
                        pass
            results.append(c)
    return results


@app.get("/api/speakers")
async def speakers():
    return db.get_speakers()


@app.get("/api/contacts")
async def contacts():
    contacts_file = DATA / "contacts.json"
    if contacts_file.exists():
        return json.loads(contacts_file.read_text())
    return {}


@app.get("/api/actions")
async def actions(status: str = None, limit: int = 50):
    return db.get_actions(status=status, limit=limit)


@app.get("/api/live")
async def live():
    if LIVE_TXT.exists():
        text = LIVE_TXT.read_text(errors="replace")
        lines = text.strip().split("\n")[-100:]
        return {"lines": lines, "total_lines": len(text.strip().split("\n"))}
    return {"lines": [], "total_lines": 0}


@app.get("/api/analytics")
async def analytics(period: str = "all"):
    today = db.get_analytics("today")
    week = db.get_analytics("week")
    month = db.get_analytics("month")
    all_time = db.get_analytics("all")
    speaker_stats = db.get_speaker_stats()

    # Segments per hour today
    today_convs = db.get_conversations(date=datetime.datetime.now().strftime("%Y-%m-%d"), limit=500)
    seg_per_hour = {}
    for c in today_convs:
        ts = c.get("timestamp", 0)
        h = datetime.datetime.fromtimestamp(ts).strftime("%H") if ts else "00"
        seg_per_hour[h] = seg_per_hour.get(h, 0) + (c.get("segment_count") or 0)

    speaker_words = {s["id"]: s["total_words"] for s in speaker_stats}

    return {
        "total_words": all_time["total_words"],
        "today_words": today["total_words"],
        "week_words": week["total_words"],
        "month_words": month["total_words"],
        "total_duration_s": all_time["total_duration_s"],
        "speaker_words": speaker_words,
        "segments_per_hour": seg_per_hour,
        "actions": db.get_actions(limit=50),
        "conversation_count": all_time["conversation_count"],
        "summary_count": len([c for c in db.get_conversations(limit=500) if c.get("summary_file_path")]),
    }


@app.get("/api/utterances")
async def utterances(conversation_id: str = None):
    """Get utterances for a conversation."""
    if conversation_id:
        return db.get_utterances(conversation_id)
    return {"error": "conversation_id required"}


@app.get("/api/search")
async def search_utterances(q: str = "", limit: int = 20):
    """FTS5 search across utterances, with fallback to vector search."""
    if not q:
        return {"results": [], "query": ""}
    # Try FTS5 first
    results = db.search_utterances(q, limit=limit)
    if results:
        return {"results": results, "query": q, "source": "fts5"}
    # Fallback to vector search
    try:
        from src.vector_store import PerceptVectorStore
        vs = PerceptVectorStore()
        results = vs.search(q, limit=limit)
        return {"results": results, "query": q, "source": "vector"}
    except Exception as e:
        return {"results": [], "query": q, "error": str(e)}


@app.get("/api/relationships")
async def relationships(entity_id: str = None):
    """Get relationship graph for an entity."""
    return db.get_relationships(entity_id=entity_id)


@app.get("/api/entities")
async def entities():
    """List all known entities with mention counts."""
    try:
        rows = db._conn.execute("""
            SELECT entity_name, entity_type, COUNT(*) as mention_count,
                   MAX(timestamp) as last_mentioned
            FROM entity_mentions
            GROUP BY entity_name, entity_type
            ORDER BY mention_count DESC
            LIMIT 200
        """).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/audit")
async def audit():
    """Data audit stats."""
    return db.audit()


@app.get("/api/vector-stats")
async def vector_stats():
    """Vector store statistics."""
    try:
        from src.vector_store import PerceptVectorStore
        vs = PerceptVectorStore()
        return vs.stats()
    except Exception as e:
        return {"error": str(e)}


## --- Settings API ---

@app.get("/api/settings")
async def get_settings():
    return db.get_all_settings()


@app.post("/api/settings")
async def update_settings(request: Request):
    body = await request.json()
    for key, value in body.items():
        db.set_setting(key, str(value))
    return {"ok": True}


@app.get("/api/settings/speakers")
async def get_settings_speakers():
    return db.get_speakers()


@app.post("/api/settings/speakers")
async def update_settings_speakers(request: Request):
    body = await request.json()
    for speaker_id, data in body.items():
        name = data.get("name") if isinstance(data, dict) else data
        relationship = data.get("relationship") if isinstance(data, dict) else None
        db.update_speaker(speaker_id, name=name, relationship=relationship)
    return {"ok": True}


@app.get("/api/settings/contacts")
async def get_settings_contacts():
    return db.get_contacts()


@app.post("/api/settings/contacts")
async def add_settings_contact(request: Request):
    body = await request.json()
    contact_id = body.get("id") or str(uuid.uuid4())
    db.save_contact(
        id=contact_id,
        name=body.get("name", ""),
        email=body.get("email"),
        phone=body.get("phone"),
        relationship=body.get("relationship"),
    )
    return {"ok": True, "id": contact_id}


@app.delete("/api/settings/contacts/{contact_id}")
async def delete_settings_contact(contact_id: str):
    db.delete_contact(contact_id)
    return {"ok": True}


@app.post("/api/purge")
async def purge_data(request: Request):
    body = await request.json()
    ttl_utt = int(body.get("ttl_utterances_days", 30))
    ttl_sum = int(body.get("ttl_summaries_days", 90))
    ttl_rel = int(body.get("ttl_relationships_days", 180))
    deleted = db.purge_older_than(ttl_utt)
    return {"ok": True, "deleted_conversations": deleted}


@app.get("/api/export")
async def export_data():
    data = {
        "conversations": db.get_conversations(limit=10000),
        "speakers": db.get_speakers(),
        "contacts": db.get_contacts(),
        "actions": db.get_actions(limit=10000),
        "relationships": db.get_relationships(),
        "settings": db.get_all_settings(),
        "audit": db.audit(),
    }
    return JSONResponse(content=data, headers={
        "Content-Disposition": "attachment; filename=percept-export.json"
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8960)
