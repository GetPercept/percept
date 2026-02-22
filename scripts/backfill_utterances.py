#!/usr/bin/env python3
"""Backfill utterances table from existing conversation markdown files.

Parses transcript lines like: **[0.0s - 1.7s] SPEAKER_0:** text
Inserts as utterances with proper timestamps and speaker IDs.
Then runs entity extraction on each conversation.
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import PerceptDB
from src.entity_extractor import EntityExtractor

CONVERSATIONS_DIR = Path(__file__).parent.parent / "data" / "conversations"

# Pattern: **[0.0s - 1.7s] SPEAKER_0:** text
# Also handles negative start times like **[-0.0s - 1.7s]**
SEGMENT_PATTERN = re.compile(
    r'\*\*\[(-?\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(\w+):\*\*\s*(.*)'
)


def parse_conversation_file(filepath: Path) -> list[dict]:
    """Parse a conversation markdown file into utterance dicts."""
    utterances = []
    text = filepath.read_text()

    # Extract conversation ID from filename (e.g., 2026-02-20_13-52.md -> 2026-02-20_13-52)
    conv_id = filepath.stem
    # Remove trailing suffixes like _1, _2, _conversation
    conv_id = re.sub(r'(_\d+|_conversation)$', '', conv_id)

    for match in SEGMENT_PATTERN.finditer(text):
        start = float(match.group(1))
        end = float(match.group(2))
        speaker = match.group(3)
        utt_text = match.group(4).strip()

        if not utt_text:
            continue

        utt_id = f"{conv_id}_{start:.1f}"
        utterances.append({
            "id": utt_id,
            "conversation_id": conv_id,
            "speaker_id": speaker,
            "text": utt_text,
            "started_at": max(0, start),  # clamp negative starts
            "ended_at": end,
            "confidence": None,
            "is_command": any(w in utt_text.lower() for w in ["jarvis", "hey jarvis"]),
        })

    return utterances


def main():
    db = PerceptDB()
    extractor = EntityExtractor(db=db, llm_enabled=False)

    if not CONVERSATIONS_DIR.exists():
        print(f"No conversations directory at {CONVERSATIONS_DIR}")
        return

    # Disable FK checks during backfill (conversation IDs from files may not all be in DB)
    with db._lock:
        db._conn.execute("PRAGMA foreign_keys=OFF")

    files = sorted(CONVERSATIONS_DIR.glob("*.md"))
    print(f"Found {len(files)} conversation files")

    total_utterances = 0
    total_entities = 0

    for i, filepath in enumerate(files):
        utterances = parse_conversation_file(filepath)
        if not utterances:
            continue

        # Batch insert utterances
        db.save_utterances_batch(utterances)
        total_utterances += len(utterances)

        # Run entity extraction
        conv_id = utterances[0]["conversation_id"]
        entities = extractor.extract_from_utterances(utterances, conv_id)
        for e in entities:
            try:
                db.save_entity_mention(conv_id, e.type, e.resolved_name or e.name)
            except Exception:
                pass
        total_entities += len(entities)

        # Build relationships
        extractor.build_relationships(entities, conv_id)

        if (i + 1) % 20 == 0:
            print(f"  Processed {i + 1}/{len(files)} files ({total_utterances} utterances, {total_entities} entities)")

    # Re-enable FK checks
    with db._lock:
        db._conn.execute("PRAGMA foreign_keys=ON")

    print(f"\nDone! Backfilled {total_utterances} utterances from {len(files)} files")
    print(f"Extracted {total_entities} entities")

    # Show audit
    stats = db.audit()
    print(f"\nDatabase stats:")
    for k, v in stats.items():
        if k == "storage_bytes":
            print(f"  Storage: {v / 1024:.1f} KB")
        else:
            print(f"  {k}: {v}")

    db.close()


if __name__ == "__main__":
    main()
