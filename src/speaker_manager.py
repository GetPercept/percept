"""Speaker registry, resolution, and name mapping for Percept.

Manages the speakers.json file and provides utilities for resolving
speaker IDs to human-readable names.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SPEAKERS_FILE = Path(__file__).parent.parent / "data" / "speakers.json"


def load_speakers() -> dict:
    """Load the speaker registry from disk.

    Returns:
        Dict mapping speaker IDs to their info (name, is_owner, approved, etc.).
    """
    try:
        with open(SPEAKERS_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "SPEAKER_0": {"name": "David", "is_owner": True},
            "SPEAKER_00": {"name": "David", "is_owner": True},
        }


def save_speakers(speakers: dict):
    """Persist the speaker registry to disk.

    Args:
        speakers: Dict mapping speaker IDs to their info dicts.
    """
    SPEAKERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SPEAKERS_FILE, "w") as f:
        json.dump(speakers, f, indent=2)


def resolve_speaker(speaker_id: str) -> str:
    """Return human name for a speaker ID if known.

    Args:
        speaker_id: Raw speaker identifier (e.g. "SPEAKER_00").

    Returns:
        Human-readable name, or the original speaker_id if unknown.
    """
    speakers = load_speakers()
    entry = speakers.get(speaker_id)
    if entry and entry.get("name") and entry["name"] != "Unknown":
        return entry["name"]
    return speaker_id


def resolve_text_with_names(text_with_speaker: str) -> str:
    """Replace [SPEAKER_XX] tags in text with known human names.

    Args:
        text_with_speaker: Text containing speaker tags like [SPEAKER_00].

    Returns:
        Text with speaker tags replaced by names where known.
    """
    speakers = load_speakers()
    for sid, info in speakers.items():
        if info.get("name") and info["name"] != "Unknown":
            text_with_speaker = text_with_speaker.replace(f"[{sid}]", f"[{info['name']}]")
    return text_with_speaker


def is_speaker_authorized(speaker_ids: set, is_user_flags: list[bool] = None) -> bool:
    """Check if any of the given speaker IDs are authorized for actions.

    Args:
        speaker_ids: Set of speaker IDs from segments.
        is_user_flags: Optional list of is_user booleans from segments.

    Returns:
        True if at least one speaker is the owner or approved.
    """
    speakers = load_speakers()
    approved = {k for k, v in speakers.items() if v.get("is_owner") or v.get("approved")}
    if speaker_ids & approved:
        return True
    if is_user_flags and any(is_user_flags):
        return True
    return False
