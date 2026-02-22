"""Backfill SQLite database from existing markdown files and JSON."""

import json
import re
import time
from datetime import datetime
from pathlib import Path

from src.database import PerceptDB

BASE = Path(__file__).parent.parent
DATA = BASE / "data"
CONV_DIR = DATA / "conversations"
SUMM_DIR = DATA / "summaries"
SPEAKERS_JSON = DATA / "speakers.json"
CONTACTS_JSON = DATA / "contacts.json"
DB_PATH = DATA / "percept.db"


def parse_conv_file(fp: Path) -> dict:
    text = fp.read_text(errors="replace")
    meta = {"file_path": str(fp)}

    # ID from filename: 2026-02-20_13-52.md -> 2026-02-20_13-52
    meta["id"] = fp.stem

    # Date/time from filename
    dm = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2})", fp.name)
    if dm:
        meta["date"] = dm.group(1)
        time_str = dm.group(2).replace("-", ":")
        try:
            dt = datetime.strptime(f"{dm.group(1)} {time_str}", "%Y-%m-%d %H:%M")
            meta["timestamp"] = dt.timestamp()
        except ValueError:
            meta["timestamp"] = fp.stat().st_mtime
    else:
        meta["date"] = datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d")
        meta["timestamp"] = fp.stat().st_mtime

    # Duration
    m = re.search(r"\*\*Duration:\*\*\s*([\d.]+)s", text)
    meta["duration_seconds"] = float(m.group(1)) if m else 0

    # Segments
    m = re.search(r"\*\*Segments:\*\*\s*(\d+)", text)
    meta["segment_count"] = int(m.group(1)) if m else 0

    # Topics
    m = re.search(r"\*\*Topics:\*\*\s*(.+)", text)
    meta["topics"] = [t.strip() for t in m.group(1).split(",")] if m else []

    # People/speakers
    m = re.search(r"\*\*People:\*\*\s*(.+)", text)
    meta["speakers"] = [p.strip() for p in m.group(1).split(",")] if m else []

    # Transcript lines
    transcript_lines = []
    for line in text.split("\n"):
        tm = re.match(r"\*\*\[[\d.-]+s\s*-\s*[\d.-]+s\]\s*(SPEAKER_\d+):\*\*\s*(.*)", line)
        if tm:
            transcript_lines.append(f"[{tm.group(1)}] {tm.group(2)}")
    meta["transcript"] = "\n".join(transcript_lines)
    meta["word_count"] = sum(len(l.split()) - 1 for l in transcript_lines) if transcript_lines else 0

    return meta


def parse_summary_file(fp: Path) -> dict:
    text = fp.read_text(errors="replace")
    meta = {"file_path": str(fp)}

    # Date from filename
    dm = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})", fp.name)
    if dm:
        meta["date"] = dm.group(1)
        time_str = dm.group(2).replace("-", ":")
        try:
            dt = datetime.strptime(f"{dm.group(1)} {time_str}", "%Y-%m-%d %H:%M:%S")
            meta["timestamp"] = dt.timestamp()
        except ValueError:
            meta["timestamp"] = fp.stat().st_mtime
    else:
        meta["date"] = datetime.fromtimestamp(fp.stat().st_mtime).strftime("%Y-%m-%d")
        meta["timestamp"] = fp.stat().st_mtime

    # Duration
    m = re.search(r"Duration:\s*~?(\d+)\s*min", text)
    meta["duration_min"] = int(m.group(1)) if m else 0

    # Segments
    m = re.search(r"Segments:\s*(\d+)", text)
    meta["segments"] = int(m.group(1)) if m else 0

    # Speakers
    m = re.search(r"Speakers:\s*(.+)", text)
    meta["speakers_str"] = m.group(1).strip() if m else ""

    # Transcript
    lines = text.split("\n")
    transcript_lines = [l for l in lines if l.startswith("[SPEAKER_") or l.startswith("[David")]
    meta["transcript"] = "\n".join(transcript_lines)
    meta["word_count"] = sum(len(l.split()) for l in transcript_lines)

    return meta


def main():
    print(f"Backfilling database at {DB_PATH}")
    db = PerceptDB(str(DB_PATH))

    # 1. Import conversations
    conv_files = sorted(CONV_DIR.glob("*.md")) if CONV_DIR.exists() else []
    print(f"Found {len(conv_files)} conversation files")
    for fp in conv_files:
        try:
            m = parse_conv_file(fp)
            db.save_conversation(
                id=m["id"], timestamp=m["timestamp"], date=m["date"],
                duration_seconds=m.get("duration_seconds"),
                segment_count=m.get("segment_count"),
                word_count=m.get("word_count"),
                speakers=m.get("speakers"), topics=m.get("topics"),
                transcript=m.get("transcript"), file_path=m.get("file_path"),
            )
        except Exception as e:
            print(f"  Error: {fp.name}: {e}")
    print(f"  Imported {len(conv_files)} conversations")

    # 2. Import summaries — match to closest conversation by timestamp
    summ_files = sorted(SUMM_DIR.glob("*.md")) if SUMM_DIR.exists() else []
    print(f"Found {len(summ_files)} summary files")
    for fp in summ_files:
        try:
            s = parse_summary_file(fp)
            # Find closest conversation within 5 minutes
            convs = db.get_conversations(date=s["date"], limit=200)
            best = None
            best_diff = 300  # 5 min max
            for c in convs:
                diff = abs(c["timestamp"] - s["timestamp"])
                if diff < best_diff:
                    best_diff = diff
                    best = c
            if best:
                # Update conversation with summary data
                db.save_conversation(
                    id=best["id"], timestamp=best["timestamp"], date=best["date"],
                    duration_seconds=s.get("duration_min", 0) * 60 or best.get("duration_seconds"),
                    segment_count=s.get("segments") or best.get("segment_count"),
                    word_count=s.get("word_count") or best.get("word_count"),
                    transcript=s.get("transcript") or best.get("transcript"),
                    summary_file_path=str(fp),
                )
            else:
                # Create standalone conversation from summary
                conv_id = fp.stem
                db.save_conversation(
                    id=conv_id, timestamp=s["timestamp"], date=s["date"],
                    duration_seconds=s.get("duration_min", 0) * 60,
                    segment_count=s.get("segments"),
                    word_count=s.get("word_count"),
                    transcript=s.get("transcript"),
                    summary_file_path=str(fp),
                )
        except Exception as e:
            print(f"  Error: {fp.name}: {e}")
    print(f"  Processed {len(summ_files)} summaries")

    # 3. Import speakers
    if SPEAKERS_JSON.exists():
        speakers = json.loads(SPEAKERS_JSON.read_text())
        for sid, info in speakers.items():
            db.update_speaker(
                speaker_id=sid,
                name=info.get("name") if info.get("name") != "Unknown" else None,
                relationship="owner" if info.get("is_owner") else "unknown",
            )
        print(f"  Imported {len(speakers)} speakers")

    # 4. Import contacts
    if CONTACTS_JSON.exists():
        contacts = json.loads(CONTACTS_JSON.read_text())
        for cname, info in contacts.items():
            db.save_contact(
                id=cname, name=cname.capitalize(),
                email=info.get("email"), phone=info.get("phone"),
            )
        print(f"  Imported {len(contacts)} contacts")

    db.close()
    print("Done!")


if __name__ == "__main__":
    main()
