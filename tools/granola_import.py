#!/usr/bin/env python3
"""
Granola → Percept Ingestion Script

Imports Granola meeting notes into Percept's SQLite conversations table.

Data sources (tried in order):
1. Local cache: ~/Library/Application Support/Granola/cache-v3.json
2. Enterprise API: https://public-api.granola.ai/v1/notes (requires GRANOLA_API_KEY)

Usage:
    python granola_import.py                    # Import from local cache
    python granola_import.py --api              # Import via Enterprise API
    python granola_import.py --since 2025-01-01 # Only import after date
    python granola_import.py --dry-run          # Preview without writing
"""

import json
import sqlite3
import hashlib
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Paths
GRANOLA_CACHE = Path.home() / "Library" / "Application Support" / "Granola" / "cache-v3.json"
PERCEPT_DB = Path(__file__).parent.parent / "data" / "percept.db"

# API
GRANOLA_API_BASE = "https://public-api.granola.ai"


def load_local_cache() -> list[dict]:
    """Load meetings from Granola's local cache-v3.json."""
    if not GRANOLA_CACHE.exists():
        print(f"❌ Granola cache not found at {GRANOLA_CACHE}")
        print("   Is Granola installed? Try --api for Enterprise API access.")
        return []

    with open(GRANOLA_CACHE, "r") as f:
        data = json.load(f)

    meetings = []
    # cache-v3.json structure: list of meeting objects with metadata, documents, transcripts
    # The exact structure varies but typically has:
    # - id, title, created_at, updated_at
    # - participants/attendees
    # - documents (notes panels)
    # - transcripts (speaker-tagged segments)
    
    items = data if isinstance(data, list) else data.get("meetings", data.get("notes", []))
    
    for item in items:
        if not isinstance(item, dict):
            continue
        meeting = {
            "id": item.get("id", ""),
            "title": item.get("title", "Untitled Meeting"),
            "created_at": item.get("created_at") or item.get("createdAt", ""),
            "updated_at": item.get("updated_at") or item.get("updatedAt", ""),
            "attendees": _extract_attendees(item),
            "transcript": _extract_transcript_local(item),
            "summary": _extract_summary_local(item),
        }
        if meeting["id"]:
            meetings.append(meeting)

    print(f"📂 Loaded {len(meetings)} meetings from local cache")
    return meetings


def _extract_attendees(item: dict) -> list[str]:
    """Extract attendee names from various cache formats."""
    attendees = []
    for key in ("attendees", "participants", "people"):
        raw = item.get(key, [])
        for a in raw:
            if isinstance(a, dict):
                name = a.get("name") or a.get("displayName") or a.get("email", "")
                if name:
                    attendees.append(name)
            elif isinstance(a, str):
                attendees.append(a)
    return attendees


def _extract_transcript_local(item: dict) -> str:
    """Extract transcript text from local cache format."""
    transcript_parts = []
    
    # Try various keys
    for key in ("transcript", "transcripts", "transcription"):
        raw = item.get(key)
        if not raw:
            continue
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):
            for seg in raw:
                if isinstance(seg, dict):
                    speaker = seg.get("speaker", {})
                    speaker_name = speaker.get("name", speaker.get("source", "Speaker")) if isinstance(speaker, dict) else str(speaker)
                    text = seg.get("text", "")
                    if text:
                        transcript_parts.append(f"{speaker_name}: {text}")
                elif isinstance(seg, str):
                    transcript_parts.append(seg)
    
    return "\n".join(transcript_parts)


def _extract_summary_local(item: dict) -> str:
    """Extract summary/notes from local cache format."""
    # Try markdown summary first, then plain text, then document panels
    for key in ("summary_markdown", "summaryMarkdown", "summary_text", "summaryText", "summary", "notes"):
        val = item.get(key)
        if val and isinstance(val, str):
            return val

    # Try document panels (Granola stores notes as document panels)
    docs = item.get("documents") or item.get("panels") or item.get("documentPanels") or []
    parts = []
    for doc in docs:
        if isinstance(doc, dict):
            content = doc.get("content") or doc.get("text") or doc.get("markdown", "")
            if content:
                parts.append(content)
    return "\n\n".join(parts)


def load_from_api(since: Optional[str] = None) -> list[dict]:
    """Load meetings from Granola Enterprise API."""
    try:
        import requests
    except ImportError:
        print("❌ requests library required for API mode: pip install requests")
        return []

    api_key = os.environ.get("GRANOLA_API_KEY")
    if not api_key:
        print("❌ Set GRANOLA_API_KEY environment variable")
        print("   Enterprise plan required. Settings → Workspaces → API tab")
        return []

    headers = {"Authorization": f"Bearer {api_key}"}
    meetings = []
    cursor = None

    while True:
        params = {"page_size": 30}
        if cursor:
            params["cursor"] = cursor
        if since:
            params["created_after"] = since

        resp = requests.get(f"{GRANOLA_API_BASE}/v1/notes", headers=headers, params=params)
        if resp.status_code == 429:
            print("⚠️  Rate limited, stopping pagination")
            break
        resp.raise_for_status()
        data = resp.json()

        notes = data.get("data", [])
        if not notes:
            break

        for note in notes:
            # Fetch full note with transcript
            detail_resp = requests.get(
                f"{GRANOLA_API_BASE}/v1/notes/{note['id']}",
                headers=headers,
                params={"include": "transcript"},
            )
            if detail_resp.status_code != 200:
                continue
            detail = detail_resp.json()

            transcript_parts = []
            for seg in (detail.get("transcript") or []):
                speaker = seg.get("speaker", {})
                source = speaker.get("source", "speaker") if isinstance(speaker, dict) else "speaker"
                text = seg.get("text", "")
                if text:
                    transcript_parts.append(f"[{source}]: {text}")

            attendee_names = [a.get("name", a.get("email", "")) for a in detail.get("attendees", [])]

            meetings.append({
                "id": detail["id"],
                "title": detail.get("title") or "Untitled Meeting",
                "created_at": detail.get("created_at", ""),
                "updated_at": detail.get("updated_at", ""),
                "attendees": attendee_names,
                "transcript": "\n".join(transcript_parts),
                "summary": detail.get("summary_markdown") or detail.get("summary_text", ""),
            })

        cursor = data.get("next_cursor")
        if not cursor:
            break

    print(f"🌐 Loaded {len(meetings)} meetings from Granola API")
    return meetings


def import_to_percept(meetings: list[dict], db_path: Path, dry_run: bool = False) -> int:
    """Import Granola meetings into Percept's conversations table."""
    if not db_path.exists():
        print(f"❌ Percept DB not found at {db_path}")
        return 0

    conn = sqlite3.connect(str(db_path))
    imported = 0
    skipped = 0

    for m in meetings:
        # Generate stable ID from Granola note ID
        conv_id = f"granola_{m['id']}"

        # Check if already imported
        existing = conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if existing:
            skipped += 1
            continue

        # Parse timestamp
        ts = _parse_timestamp(m.get("created_at", ""))
        if not ts:
            ts = datetime.now(timezone.utc).timestamp()

        date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        transcript = m.get("transcript", "")
        summary = m.get("summary", "")
        speakers = json.dumps(m.get("attendees", []))
        word_count = len(transcript.split()) if transcript else 0

        if dry_run:
            print(f"  📝 Would import: {m.get('title', 'Untitled')} ({date_str}, {word_count} words)")
        else:
            conn.execute(
                """INSERT INTO conversations 
                   (id, timestamp, date, duration_seconds, segment_count, word_count,
                    speakers, topics, transcript, summary, file_path, summary_file_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    conv_id, ts, date_str, None, None, word_count,
                    speakers, json.dumps([m.get("title", "")]),
                    transcript, summary,
                    f"granola://{m['id']}", None,
                ),
            )
        imported += 1

    if not dry_run:
        conn.commit()
    conn.close()

    print(f"✅ Imported: {imported}, Skipped (already exists): {skipped}")
    return imported


def _parse_timestamp(ts_str: str) -> Optional[float]:
    """Parse ISO timestamp to unix epoch."""
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(ts_str, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def main():
    parser = argparse.ArgumentParser(description="Import Granola meetings into Percept")
    parser.add_argument("--api", action="store_true", help="Use Enterprise API instead of local cache")
    parser.add_argument("--since", type=str, help="Only import meetings after this date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    parser.add_argument("--db", type=str, default=str(PERCEPT_DB), help="Path to Percept DB")
    args = parser.parse_args()

    print("🥣 Granola → Percept Importer")
    print("=" * 40)

    if args.api:
        meetings = load_from_api(since=args.since)
    else:
        meetings = load_local_cache()
        if args.since:
            cutoff = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
            meetings = [m for m in meetings if (_parse_timestamp(m.get("created_at", "")) or 0) >= cutoff]

    if not meetings:
        print("No meetings to import.")
        return

    import_to_percept(meetings, Path(args.db), dry_run=args.dry_run)


if __name__ == "__main__":
    main()
