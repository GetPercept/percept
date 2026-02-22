"""Conversation summary generation, day summaries, and calendar context for Percept.

Handles detecting conversation end, generating LLM-powered summaries,
saving summaries to DB and files, building day summaries from live data,
and matching conversations to calendar events.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.speaker_manager import resolve_speaker

logger = logging.getLogger(__name__)

# Binary path resolution with fallback
def _get_binary_path(name: str) -> str:
    """Get binary path dynamically with fallback."""
    path = shutil.which(name)
    if not path:
        logger.warning(f"Binary '{name}' not found in PATH, action will be skipped")
        return None
    return path

SUMMARY_LOG = Path(__file__).parent.parent / "data" / "summaries"
SUMMARY_LOG.mkdir(parents=True, exist_ok=True)


def build_transcript_with_names(segments: list[dict]) -> tuple[str, set[str]]:
    """Build a full transcript with resolved speaker names.

    Args:
        segments: List of segment dicts with 'text' and 'speaker' keys.

    Returns:
        Tuple of (transcript_string, set_of_speaker_names).
    """
    all_texts = []
    speakers = set()
    for s in segments:
        speaker_name = resolve_speaker(s.get("speaker", "SPEAKER_0"))
        speakers.add(speaker_name)
        all_texts.append(f"[{speaker_name}] {s['text']}")
    return "\n".join(all_texts), speakers


async def get_calendar_context(start_time: float = None) -> str:
    """Fetch today's calendar events for conversation context matching.

    Args:
        start_time: Conversation start timestamp for time matching.

    Returns:
        Calendar context string, or empty string if unavailable.
    """
    try:
        gog_path = _get_binary_path("gog")
        if not gog_path:
            return ""
            
        env = os.environ.copy()  # Inherit system PATH
        proc = await asyncio.create_subprocess_exec(
            gog_path, "cal", "list", "--from", "today", "--to", "today",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            return ""
        cal_output = stdout.decode().strip()
        if not cal_output:
            return ""
        conv_time = datetime.fromtimestamp(start_time).strftime('%H:%M') if start_time else datetime.now().strftime('%H:%M')
        return (
            f"\nCalendar context (conversation started ~{conv_time}):\n{cal_output}\n"
            f"If a calendar event matches the timing, mention: 'This was likely your [time] [event name].'"
        )
    except Exception:
        return ""


def build_day_summary(live_file: Path) -> dict:
    """Build a day summary from the live transcript file.

    Args:
        live_file: Path to the percept-live.txt file.

    Returns:
        Dict with total_conversations, total_words, speakers_seen, key_topics, date.
    """
    today_str = datetime.now().strftime('%Y-%m-%d')
    result = {"total_conversations": 0, "total_words": 0, "speakers_seen": [], "key_topics": [], "date": today_str}

    if not live_file.exists():
        return result

    speakers = set()
    conversations = 0
    words = 0
    all_text = []
    in_today = False

    for line in live_file.read_text().split('\n'):
        line = line.strip()
        if line.startswith('--- ') and line.endswith(' ---'):
            ts_str = line.strip('- ')
            in_today = ts_str.startswith(today_str)
            if in_today:
                conversations += 1
            continue
        if not in_today or not line:
            continue
        if line.startswith('['):
            bracket_end = line.find(']')
            if bracket_end > 0:
                speaker = line[1:bracket_end]
                speakers.add(resolve_speaker(speaker))
                text = line[bracket_end + 2:] if bracket_end + 2 < len(line) else ""
                words += len(text.split())
                all_text.append(text)

    # Key topics via word frequency
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "i", "you", "we", "they", "it",
        "to", "and", "of", "in", "that", "for", "on", "with", "so", "but", "just",
        "like", "yeah", "okay", "right", "um", "uh", "know", "think", "going", "got",
        "well", "dont", "thats", "its", "have", "been", "this", "not", "what", "about",
        "do", "be", "my", "your", "he", "she", "me", "or", "if", "at", "from", "can",
        "will", "one", "all", "would", "there", "their", "up", "out", "then",
    }
    word_counts = Counter()
    for text in all_text:
        for w in text.lower().split():
            w = re.sub(r'[^a-z]', '', w)
            if len(w) > 3 and w not in stop_words:
                word_counts[w] += 1

    result["total_conversations"] = conversations
    result["total_words"] = words
    result["speakers_seen"] = sorted(speakers)
    result["key_topics"] = [w for w, _ in word_counts.most_common(10)]
    return result
