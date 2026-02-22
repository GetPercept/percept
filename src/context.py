"""Context extraction and conversation memory writer."""

import re
import logging
from datetime import datetime
from pathlib import Path

from src.transcriber import Conversation, Segment

logger = logging.getLogger(__name__)


def extract_context(conversation: Conversation) -> dict:
    """Extract key topics, action items, and people from a conversation."""
    text = conversation.full_text.lower()

    # Simple keyword-based extraction (no API keys needed)
    action_patterns = [
        r"(?:need to|should|have to|must|going to|will|let'?s|don'?t forget to|remind me to|make sure to)\s+(.+?)(?:\.|,|$)",
        r"(?:action item|todo|to-do|task)[:;]?\s*(.+?)(?:\.|,|$)",
    ]
    action_items = []
    for pat in action_patterns:
        for match in re.finditer(pat, text):
            item = match.group(1).strip()
            if len(item) > 5 and len(item) < 200:
                action_items.append(item)

    # People detection (capitalized words after common name indicators)
    name_pattern = r"(?:(?:^|[.!?]\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))"
    people = list(set(re.findall(name_pattern, conversation.full_text)))
    # Filter out common sentence starters
    stopwords = {"I", "The", "This", "That", "We", "They", "It", "So", "But", "And", "Or", "What", "How", "Why", "When", "Where", "Yeah", "Yes", "No", "Well", "Ok", "Okay", "Let", "Just"}
    people = [p for p in people if p not in stopwords and len(p) > 1]

    # Topic extraction: most frequent meaningful words
    words = re.findall(r'\b[a-z]{4,}\b', text)
    stop = {"that", "this", "with", "have", "from", "they", "been", "will", "would", "could",
            "should", "about", "there", "their", "what", "when", "where", "which", "just",
            "like", "know", "think", "going", "want", "really", "right", "yeah", "okay",
            "some", "them", "then", "also", "well", "here", "more", "very", "thing", "something"}
    word_counts = {}
    for w in words:
        if w not in stop:
            word_counts[w] = word_counts.get(w, 0) + 1
    topics = sorted(word_counts, key=word_counts.get, reverse=True)[:10]

    return {
        "action_items": action_items[:10],
        "people": people[:10],
        "topics": topics,
        "duration_seconds": round(conversation.last_activity - conversation.started_at, 1),
        "segment_count": len(conversation.segments),
    }


def save_conversation(conversation: Conversation, conversations_dir: str) -> Path:
    """Save conversation transcript + summary to memory/conversations/."""
    dir_path = Path(conversations_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    ts = datetime.fromtimestamp(conversation.started_at)
    filename = ts.strftime("%Y-%m-%d_%H-%M") + ".md"
    filepath = dir_path / filename

    # Avoid overwriting
    counter = 1
    while filepath.exists():
        filename = ts.strftime("%Y-%m-%d_%H-%M") + f"_{counter}.md"
        filepath = dir_path / filename
        counter += 1

    ctx = extract_context(conversation)

    lines = [
        f"# Conversation — {ts.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Duration:** {ctx['duration_seconds']}s | **Segments:** {ctx['segment_count']}",
        "",
    ]

    if ctx["topics"]:
        lines.append(f"**Topics:** {', '.join(ctx['topics'])}")
    if ctx["people"]:
        lines.append(f"**People:** {', '.join(ctx['people'])}")
    if ctx["action_items"]:
        lines.append("")
        lines.append("## Action Items")
        for item in ctx["action_items"]:
            lines.append(f"- [ ] {item}")

    lines.extend(["", "## Transcript", ""])
    for seg in conversation.segments:
        lines.append(f"**[{seg.start:.1f}s - {seg.end:.1f}s] {seg.speaker}:** {seg.text}")

    lines.append("")

    filepath.write_text("\n".join(lines))
    logger.info(f"Saved conversation to {filepath}")
    return filepath
