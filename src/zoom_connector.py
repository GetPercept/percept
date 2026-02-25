#!/usr/bin/env python3
"""Percept Zoom Connector — ingest Zoom meeting transcripts into Percept.

Supports two modes:
1. **Webhook** — Zoom sends `recording.completed` events, we auto-download + ingest
2. **Manual import** — Point at a Zoom cloud recording or local VTT/transcript file

Setup:
    1. Create a Zoom Server-to-Server OAuth app at marketplace.zoom.us
    2. Set env vars: ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
    3. Add webhook endpoint: https://percept.clawdoor.com/zoom/webhook
    4. Subscribe to `recording.completed` event

Run standalone:
    python -m src.zoom_connector --port 8902

Or via CLI:
    percept zoom-sync           # Sync recent recordings
    percept zoom-import <url>   # Import specific recording
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException, Request as FastAPIRequest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database import PerceptDB

logger = logging.getLogger("percept.zoom")

# ── Config ─────────────────────────────────────────────────────────────

ZOOM_ACCOUNT_ID = os.environ.get("ZOOM_ACCOUNT_ID", "")
ZOOM_CLIENT_ID = os.environ.get("ZOOM_CLIENT_ID", "")
ZOOM_CLIENT_SECRET = os.environ.get("ZOOM_CLIENT_SECRET", "")
ZOOM_WEBHOOK_SECRET = os.environ.get("ZOOM_WEBHOOK_SECRET", "")
ZOOM_API_BASE = "https://api.zoom.us/v2"
ZOOM_OAUTH_URL = "https://zoom.us/oauth/token"

# Token cache
_token_cache: dict[str, Any] = {"token": None, "expires_at": 0}

# ── OAuth ──────────────────────────────────────────────────────────────


def _get_access_token() -> str:
    """Get Zoom Server-to-Server OAuth access token (cached)."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    if not all([ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET]):
        raise RuntimeError(
            "Zoom credentials not configured. Set ZOOM_ACCOUNT_ID, "
            "ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET environment variables."
        )

    import base64

    credentials = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
    data = urlencode({"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID}).encode()

    req = Request(
        ZOOM_OAUTH_URL,
        data=data,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    resp = urlopen(req, timeout=10)
    result = json.loads(resp.read())

    _token_cache["token"] = result["access_token"]
    _token_cache["expires_at"] = now + result.get("expires_in", 3600)
    return result["access_token"]


def _zoom_api(endpoint: str, method: str = "GET") -> dict:
    """Make authenticated Zoom API call."""
    token = _get_access_token()
    url = f"{ZOOM_API_BASE}{endpoint}" if endpoint.startswith("/") else endpoint
    req = Request(url, headers={"Authorization": f"Bearer {token}"}, method=method)
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read())


# ── Transcript Parsing ─────────────────────────────────────────────────


def parse_vtt(vtt_content: str) -> list[dict]:
    """Parse WebVTT transcript into utterance segments."""
    lines = vtt_content.strip().split("\n")
    segments = []
    current_speaker = None
    current_text = []
    current_start = None

    for line in lines:
        line = line.strip()
        if not line or line == "WEBVTT" or line.startswith("NOTE"):
            continue

        # Timestamp line: 00:00:00.000 --> 00:00:05.000
        if " --> " in line:
            if current_text and current_start:
                segments.append({
                    "speaker_id": current_speaker or "UNKNOWN",
                    "text": " ".join(current_text),
                    "started_at": current_start,
                })
                current_text = []
            parts = line.split(" --> ")
            current_start = parts[0].strip()
            continue

        # Speaker label: "Speaker Name: text" or just text
        if ": " in line and not line[0].isdigit():
            colon_idx = line.index(": ")
            potential_speaker = line[:colon_idx].strip()
            # Heuristic: speaker names are short
            if len(potential_speaker) < 40:
                current_speaker = potential_speaker
                line = line[colon_idx + 2:]

        if line and not line.isdigit():
            current_text.append(line)

    # Final segment
    if current_text and current_start:
        segments.append({
            "speaker_id": current_speaker or "UNKNOWN",
            "text": " ".join(current_text),
            "started_at": current_start,
        })

    return segments


# ── Import Logic ───────────────────────────────────────────────────────


def import_recording(meeting_id: str | int) -> dict:
    """Import a Zoom cloud recording's transcript into Percept."""
    recordings = _zoom_api(f"/meetings/{meeting_id}/recordings")
    meeting_topic = recordings.get("topic", f"Zoom Meeting {meeting_id}")
    meeting_start = recordings.get("start_time", "")

    # Find transcript file
    transcript_file = None
    for f in recordings.get("recording_files", []):
        if f.get("file_type") == "TRANSCRIPT" or f.get("recording_type") == "audio_transcript":
            transcript_file = f
            break

    if not transcript_file:
        return {"error": "No transcript found for this recording", "meeting_id": meeting_id}

    # Download transcript
    download_url = transcript_file["download_url"]
    token = _get_access_token()
    req = Request(
        f"{download_url}?access_token={token}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = urlopen(req, timeout=30)
    vtt_content = resp.read().decode("utf-8")

    return _ingest_transcript(
        topic=meeting_topic,
        date_str=meeting_start,
        vtt_content=vtt_content,
        source=f"zoom:{meeting_id}",
    )


def import_vtt_file(file_path: str, topic: str | None = None) -> dict:
    """Import a local VTT transcript file into Percept."""
    p = Path(file_path)
    if not p.exists():
        return {"error": f"File not found: {file_path}"}

    vtt_content = p.read_text()
    return _ingest_transcript(
        topic=topic or p.stem,
        date_str=datetime.now().isoformat(),
        vtt_content=vtt_content,
        source=f"file:{file_path}",
    )


def _ingest_transcript(topic: str, date_str: str, vtt_content: str, source: str) -> dict:
    """Parse and store a VTT transcript in the Percept database."""
    segments = parse_vtt(vtt_content)
    if not segments:
        return {"error": "No segments parsed from transcript", "source": source}

    full_transcript = "\n".join(
        f"[{s['speaker_id']}] {s['text']}" for s in segments
    )
    word_count = sum(len(s["text"].split()) for s in segments)
    speakers = list({s["speaker_id"] for s in segments})

    db = PerceptDB()
    try:
        conv_id = db.save_conversation(
            transcript=full_transcript,
            summary=f"Zoom: {topic}",
            speakers=", ".join(speakers),
            word_count=word_count,
            source=source,
        )

        # Save individual utterances for FTS search
        for seg in segments:
            db.save_utterance(
                conversation_id=conv_id,
                speaker_id=seg["speaker_id"],
                text=seg["text"],
                started_at=seg.get("started_at"),
            )

        return {
            "status": "imported",
            "conversation_id": conv_id,
            "topic": topic,
            "segments": len(segments),
            "word_count": word_count,
            "speakers": speakers,
            "source": source,
        }
    finally:
        db.close()


def sync_recent(days: int = 7, user_id: str = "me") -> list[dict]:
    """Sync all recordings from the past N days."""
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    to_date = datetime.utcnow().strftime("%Y-%m-%d")

    recordings = _zoom_api(
        f"/users/{user_id}/recordings?from={from_date}&to={to_date}&page_size=100"
    )

    results = []
    for meeting in recordings.get("meetings", []):
        has_transcript = any(
            f.get("file_type") == "TRANSCRIPT" or f.get("recording_type") == "audio_transcript"
            for f in meeting.get("recording_files", [])
        )
        if has_transcript:
            result = import_recording(meeting["id"])
            results.append(result)

    return results


# ── Webhook Server ─────────────────────────────────────────────────────

webhook_app = FastAPI(title="Percept Zoom Webhook", version="1.0.0")


def _verify_webhook(payload: bytes, signature: str, timestamp: str) -> bool:
    """Verify Zoom webhook signature."""
    if not ZOOM_WEBHOOK_SECRET:
        return True  # No verification configured
    message = f"v0:{timestamp}:{payload.decode()}"
    expected = "v0=" + hmac.new(
        ZOOM_WEBHOOK_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@webhook_app.post("/zoom/webhook")
async def zoom_webhook(request: FastAPIRequest):
    """Handle Zoom webhook events."""
    body = await request.body()
    signature = request.headers.get("x-zm-signature", "")
    timestamp = request.headers.get("x-zm-request-timestamp", "")

    if not _verify_webhook(body, signature, timestamp):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(body)
    event = payload.get("event", "")

    # Zoom URL validation challenge
    if event == "endpoint.url_validation":
        plain_token = payload["payload"]["plainToken"]
        encrypted = hmac.new(
            ZOOM_WEBHOOK_SECRET.encode(), plain_token.encode(), hashlib.sha256
        ).hexdigest()
        return {"plainToken": plain_token, "encryptedToken": encrypted}

    # Recording completed — auto-import
    if event == "recording.completed":
        meeting = payload.get("payload", {}).get("object", {})
        meeting_id = meeting.get("id")
        if meeting_id:
            logger.info(f"Recording completed for meeting {meeting_id}, importing...")
            try:
                result = import_recording(meeting_id)
                logger.info(f"Import result: {result}")
            except Exception as e:
                logger.error(f"Failed to import meeting {meeting_id}: {e}")

    return {"status": "ok"}


# ── CLI Entry ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(description="Percept Zoom Connector")
    sub = parser.add_subparsers(dest="command")

    serve_cmd = sub.add_parser("serve", help="Run webhook server")
    serve_cmd.add_argument("--port", type=int, default=8902)
    serve_cmd.add_argument("--host", default="127.0.0.1")

    sync_cmd = sub.add_parser("sync", help="Sync recent recordings")
    sync_cmd.add_argument("--days", type=int, default=7)

    import_cmd = sub.add_parser("import", help="Import a recording or VTT file")
    import_cmd.add_argument("source", help="Meeting ID or path to VTT file")
    import_cmd.add_argument("--topic", help="Meeting topic (for VTT files)")

    args = parser.parse_args()

    if args.command == "serve":
        uvicorn.run(webhook_app, host=args.host, port=args.port)
    elif args.command == "sync":
        results = sync_recent(days=args.days)
        print(json.dumps(results, indent=2))
    elif args.command == "import":
        if Path(args.source).exists():
            result = import_vtt_file(args.source, topic=args.topic)
        else:
            result = import_recording(args.source)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
