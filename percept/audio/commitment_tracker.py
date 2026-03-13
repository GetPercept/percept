"""
Commitment Tracker — CIL Level 2

Extracts commitments (promises, deadlines, action items) from conversations,
tracks their status over time, and detects when they go unfulfilled.

A commitment is: someone said they would do something, optionally by a deadline.
"""

import re
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Commitment signal patterns — phrases that indicate someone is committing to something
COMMITMENT_PATTERNS = [
    # Direct promises
    r"(?:I|I'll|I will|I'm going to|I am going to|I can|I shall)\s+(?:get|send|do|make|prepare|write|create|build|fix|check|review|follow up|look into|set up|schedule|call|email|text|update|share|deliver|submit|finish|complete|handle|take care of)\b",
    # Obligation language
    r"(?:I|we)\s+(?:need to|have to|should|must|ought to|gotta|gonna)\s+\w+",
    # Deadline language
    r"(?:by|before|until|no later than|end of|within)\s+(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|end of (?:day|week|month)|the end of|EOD|COB|\d{1,2}(?:st|nd|rd|th)?)",
    # Action items
    r"(?:action item|todo|to-do|task|follow.?up|next step)s?[\s:]+",
    # Third-party commitments ("he said he would", "Sarah will")
    r"(?:he|she|they|we)\s+(?:will|'ll|said (?:he|she|they) would|promised to|agreed to|committed to)\s+\w+",
    # "Let me" pattern
    r"let me\s+(?:get|send|check|look|find|grab|pull|set|put|take|follow|circle)\b",
]

DEADLINE_PATTERNS = [
    (r"\bby\s+(today|tomorrow|tonight)\b", "relative"),
    (r"\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "weekday"),
    (r"\bby\s+(?:end of|the end of|EOD|COB)\s*(day|week|month|quarter|year)?\b", "eod"),
    (r"\bby\s+(\d{1,2}(?:st|nd|rd|th)?(?:\s+(?:of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*)?)\b", "date"),
    (r"\bwithin\s+(\d+)\s+(hours?|days?|weeks?|months?)\b", "duration"),
    (r"\bnext\s+(week|month|monday|tuesday|wednesday|thursday|friday)\b", "next"),
    (r"\bin\s+(\d+)\s+(minutes?|hours?|days?|weeks?)\b", "duration"),
]

# Patterns that look like commitments but aren't
FALSE_POSITIVE_PATTERNS = [
    r"(?:I|we)\s+(?:used to|would have|could have|should have|might)\b",
    r"\b(?:if|when|unless|hypothetically|theoretically)\b.*(?:I'll|I will|I can)\b",
    r"(?:do you think|would you|can you|could you|should we)\b",
]


@dataclass
class Commitment:
    """A tracked commitment extracted from conversation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = ""
    speaker_id: str = ""
    speaker_name: str = ""
    raw_text: str = ""
    action: str = ""  # What they committed to do
    assignee: str = ""  # Who committed (usually speaker)
    deadline: Optional[str] = None  # When it's due
    deadline_dt: Optional[float] = None  # Unix timestamp of deadline
    status: str = "open"  # open, fulfilled, overdue, cancelled
    confidence: float = 0.0  # 0-1 confidence score
    extracted_at: float = field(default_factory=lambda: datetime.now().timestamp())
    fulfilled_at: Optional[float] = None
    last_mentioned: Optional[float] = None
    mention_count: int = 1
    context: str = ""  # Surrounding conversation context


class CommitmentTracker:
    """Extracts and tracks commitments from conversation utterances."""

    def __init__(self, db=None):
        self.db = db
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in COMMITMENT_PATTERNS]
        self._compiled_false_positives = [re.compile(p, re.IGNORECASE) for p in FALSE_POSITIVE_PATTERNS]
        self._compiled_deadlines = [(re.compile(p, re.IGNORECASE), kind) for p, kind in DEADLINE_PATTERNS]
        self._ensure_tables()

    def _ensure_tables(self):
        """Create commitments table if it doesn't exist."""
        if not self.db:
            return
        try:
            conn = self.db._get_conn() if hasattr(self.db, '_get_conn') else None
            if not conn:
                return
            conn.execute("""
                CREATE TABLE IF NOT EXISTS commitments (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT,
                    speaker_id TEXT,
                    speaker_name TEXT,
                    raw_text TEXT NOT NULL,
                    action TEXT NOT NULL,
                    assignee TEXT,
                    deadline TEXT,
                    deadline_dt REAL,
                    status TEXT DEFAULT 'open',
                    confidence REAL DEFAULT 0.0,
                    extracted_at REAL DEFAULT (strftime('%s', 'now')),
                    fulfilled_at REAL,
                    last_mentioned REAL,
                    mention_count INTEGER DEFAULT 1,
                    context TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                );
                CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status);
                CREATE INDEX IF NOT EXISTS idx_commitments_deadline ON commitments(deadline_dt);
                CREATE INDEX IF NOT EXISTS idx_commitments_speaker ON commitments(speaker_id);
            """)
            conn.commit()
        except Exception as e:
            logger.warning(f"Could not create commitments table: {e}")

    def extract_commitments(
        self,
        utterances: list[dict],
        conversation_id: str = "",
        context_window: int = 2,
    ) -> list[Commitment]:
        """
        Extract commitments from a list of utterances.

        Args:
            utterances: List of dicts with 'text', 'speaker_id', 'speaker_name', 'timestamp'
            conversation_id: ID of the conversation
            context_window: Number of surrounding utterances to include as context

        Returns:
            List of extracted Commitment objects
        """
        commitments = []

        for i, utt in enumerate(utterances):
            text = utt.get("text", "")
            if len(text) < 10:
                continue

            # Check for false positives first
            if self._is_false_positive(text):
                continue

            # Check each commitment pattern
            matches = []
            for pattern in self._compiled_patterns:
                match = pattern.search(text)
                if match:
                    matches.append(match)

            if not matches:
                continue

            # Extract the commitment details
            action = self._extract_action(text, matches)
            deadline, deadline_dt = self._extract_deadline(text)

            # Build context from surrounding utterances
            context_parts = []
            for j in range(max(0, i - context_window), min(len(utterances), i + context_window + 1)):
                if j != i:
                    ctx_text = utterances[j].get("text", "")[:100]
                    ctx_speaker = utterances[j].get("speaker_name", "Unknown")
                    context_parts.append(f"{ctx_speaker}: {ctx_text}")

            # Calculate confidence
            confidence = self._calculate_confidence(text, matches, deadline)

            if confidence < 0.3:
                continue

            commitment = Commitment(
                conversation_id=conversation_id,
                speaker_id=utt.get("speaker_id", ""),
                speaker_name=utt.get("speaker_name", "Unknown"),
                raw_text=text,
                action=action,
                assignee=utt.get("speaker_name", "Unknown"),
                deadline=deadline,
                deadline_dt=deadline_dt,
                confidence=confidence,
                extracted_at=utt.get("timestamp", datetime.now().timestamp()),
                context="\n".join(context_parts),
            )
            commitments.append(commitment)

        return commitments

    def _is_false_positive(self, text: str) -> bool:
        """Check if text matches false positive patterns."""
        for pattern in self._compiled_false_positives:
            if pattern.search(text):
                return True
        return False

    def _extract_action(self, text: str, matches: list) -> str:
        """Extract the action/commitment from the text."""
        # Use the first match to find the commitment phrase
        first_match = matches[0]
        start = first_match.start()

        # Get the sentence containing the match
        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences:
            if first_match.group() in sentence:
                return sentence.strip()

        # Fallback: take from match to end of clause
        rest = text[start:]
        # Cut at next sentence boundary or comma-separated clause
        end_match = re.search(r'[.!?,;]|\band\b|\bbut\b', rest[len(first_match.group()):])
        if end_match:
            return rest[:len(first_match.group()) + end_match.start()].strip()

        return rest[:150].strip()

    def _extract_deadline(self, text: str) -> tuple[Optional[str], Optional[float]]:
        """Extract deadline from text, return (human string, unix timestamp)."""
        now = datetime.now()

        for pattern, kind in self._compiled_deadlines:
            match = pattern.search(text)
            if not match:
                continue

            raw = match.group(1) if match.lastindex else match.group()

            if kind == "relative":
                raw_lower = raw.lower()
                if raw_lower in ("today", "tonight"):
                    dt = now.replace(hour=23, minute=59)
                elif raw_lower == "tomorrow":
                    dt = (now + timedelta(days=1)).replace(hour=23, minute=59)
                else:
                    continue
                return raw, dt.timestamp()

            elif kind == "weekday":
                day_map = {
                    "monday": 0, "tuesday": 1, "wednesday": 2,
                    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
                }
                target = day_map.get(raw.lower())
                if target is not None:
                    days_ahead = (target - now.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    dt = (now + timedelta(days=days_ahead)).replace(hour=23, minute=59)
                    return f"by {raw}", dt.timestamp()

            elif kind == "eod":
                period = match.group(1) if match.lastindex else "day"
                if not period or period == "day":
                    dt = now.replace(hour=23, minute=59)
                    return "end of day", dt.timestamp()
                elif period == "week":
                    days_to_friday = (4 - now.weekday()) % 7
                    dt = (now + timedelta(days=days_to_friday)).replace(hour=23, minute=59)
                    return "end of week", dt.timestamp()
                elif period == "month":
                    if now.month == 12:
                        dt = now.replace(year=now.year + 1, month=1, day=1) - timedelta(days=1)
                    else:
                        dt = now.replace(month=now.month + 1, day=1) - timedelta(days=1)
                    return "end of month", dt.timestamp()
                return f"end of {period}", None

            elif kind == "duration":
                amount = int(match.group(1))
                unit = match.group(2).rstrip("s")
                if unit == "hour":
                    dt = now + timedelta(hours=amount)
                elif unit == "day":
                    dt = now + timedelta(days=amount)
                elif unit == "week":
                    dt = now + timedelta(weeks=amount)
                elif unit == "minute":
                    dt = now + timedelta(minutes=amount)
                else:
                    continue
                return f"within {amount} {match.group(2)}", dt.timestamp()

            elif kind == "next":
                ref = raw.lower()
                if ref == "week":
                    days_to_monday = (7 - now.weekday()) % 7 or 7
                    dt = (now + timedelta(days=days_to_monday + 4)).replace(hour=23, minute=59)
                    return "next week", dt.timestamp()
                elif ref == "month":
                    if now.month == 12:
                        dt = now.replace(year=now.year + 1, month=1, day=28)
                    else:
                        dt = now.replace(month=now.month + 1, day=28)
                    return "next month", dt.timestamp()
                else:
                    # Weekday name
                    day_map = {
                        "monday": 0, "tuesday": 1, "wednesday": 2,
                        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
                    }
                    target = day_map.get(ref)
                    if target is not None:
                        days_ahead = (target - now.weekday()) % 7
                        if days_ahead == 0:
                            days_ahead = 7
                        dt = (now + timedelta(days=days_ahead)).replace(hour=23, minute=59)
                        return f"next {raw}", dt.timestamp()

        return None, None

    def _calculate_confidence(self, text: str, matches: list, deadline: Optional[str]) -> float:
        """Calculate confidence score for a commitment."""
        score = 0.0

        # Base: number of pattern matches (more signals = higher confidence)
        score += min(len(matches) * 0.2, 0.4)

        # First-person commitment ("I will") is stronger than third-person
        if re.search(r"\b(?:I|I'll|I will|I'm going to|let me)\b", text, re.IGNORECASE):
            score += 0.25
        elif re.search(r"\b(?:he|she|they)\s+(?:will|said|promised)\b", text, re.IGNORECASE):
            score += 0.15

        # Has a deadline = much more likely to be a real commitment
        if deadline:
            score += 0.2

        # Specificity — mentions a concrete thing (email, document, call, etc.)
        if re.search(r"\b(?:email|document|report|contract|proposal|meeting|call|invoice|draft|presentation|deck|spreadsheet|budget|schedule)\b", text, re.IGNORECASE):
            score += 0.1

        # Named person involved
        if re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", text):
            score += 0.05

        return min(score, 1.0)

    def save_commitments(self, commitments: list[Commitment]) -> int:
        """Save commitments to database. Returns count saved."""
        if not self.db or not commitments:
            return 0

        saved = 0
        try:
            conn = self.db._get_conn()
            for c in commitments:
                conn.execute("""
                    INSERT OR IGNORE INTO commitments
                    (id, conversation_id, speaker_id, speaker_name, raw_text,
                     action, assignee, deadline, deadline_dt, status,
                     confidence, extracted_at, context, mention_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c.id, c.conversation_id, c.speaker_id, c.speaker_name,
                    c.raw_text, c.action, c.assignee, c.deadline, c.deadline_dt,
                    c.status, c.confidence, c.extracted_at, c.context, c.mention_count,
                ))
                saved += 1
            conn.commit()
            logger.info(f"Saved {saved} commitments")
        except Exception as e:
            logger.error(f"Failed to save commitments: {e}")

        return saved

    def check_overdue(self) -> list[dict]:
        """Find commitments that are past their deadline and still open."""
        if not self.db:
            return []

        try:
            conn = self.db._get_conn()
            now = datetime.now().timestamp()
            rows = conn.execute("""
                SELECT id, speaker_name, action, deadline, deadline_dt,
                       extracted_at, confidence
                FROM commitments
                WHERE status = 'open'
                  AND deadline_dt IS NOT NULL
                  AND deadline_dt < ?
                ORDER BY deadline_dt ASC
            """, (now,)).fetchall()

            return [
                {
                    "id": r[0],
                    "speaker": r[1],
                    "action": r[2],
                    "deadline": r[3],
                    "deadline_dt": r[4],
                    "days_overdue": (now - r[4]) / 86400,
                    "confidence": r[6],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Failed to check overdue: {e}")
            return []

    def get_open_commitments(self, speaker: Optional[str] = None) -> list[dict]:
        """Get all open commitments, optionally filtered by speaker."""
        if not self.db:
            return []

        try:
            conn = self.db._get_conn()
            if speaker:
                rows = conn.execute("""
                    SELECT id, speaker_name, action, deadline, deadline_dt,
                           status, confidence, extracted_at
                    FROM commitments
                    WHERE status = 'open' AND speaker_name LIKE ?
                    ORDER BY deadline_dt ASC NULLS LAST
                """, (f"%{speaker}%",)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT id, speaker_name, action, deadline, deadline_dt,
                           status, confidence, extracted_at
                    FROM commitments
                    WHERE status = 'open'
                    ORDER BY deadline_dt ASC NULLS LAST
                """).fetchall()

            return [
                {
                    "id": r[0],
                    "speaker": r[1],
                    "action": r[2],
                    "deadline": r[3],
                    "deadline_dt": r[4],
                    "status": r[5],
                    "confidence": r[6],
                    "extracted_at": r[7],
                }
                for r in rows
            ]
        except Exception as e:
            logger.error(f"Failed to get open commitments: {e}")
            return []

    def fulfill(self, commitment_id: str) -> bool:
        """Mark a commitment as fulfilled."""
        if not self.db:
            return False
        try:
            conn = self.db._get_conn()
            conn.execute("""
                UPDATE commitments
                SET status = 'fulfilled', fulfilled_at = strftime('%s', 'now')
                WHERE id = ?
            """, (commitment_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to fulfill commitment: {e}")
            return False

    def cancel(self, commitment_id: str) -> bool:
        """Mark a commitment as cancelled."""
        if not self.db:
            return False
        try:
            conn = self.db._get_conn()
            conn.execute("""
                UPDATE commitments SET status = 'cancelled' WHERE id = ?
            """, (commitment_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to cancel commitment: {e}")
            return False

    def detect_re_mention(self, text: str) -> list[dict]:
        """
        Check if new text references an existing open commitment.
        Used for cross-conversation tracking.
        """
        if not self.db:
            return []

        try:
            conn = self.db._get_conn()
            open_commitments = conn.execute("""
                SELECT id, action, speaker_name, deadline
                FROM commitments WHERE status = 'open'
            """).fetchall()

            matches = []
            text_lower = text.lower()
            for row in open_commitments:
                # Extract key nouns from the action
                action_words = set(
                    w.lower() for w in re.findall(r'\b[a-zA-Z]{4,}\b', row[1])
                ) - {"will", "would", "going", "that", "this", "them", "they", "have", "been", "with"}

                # If 2+ key words from the action appear in new text, it's a re-mention
                overlap = sum(1 for w in action_words if w in text_lower)
                if overlap >= 2:
                    matches.append({
                        "id": row[0],
                        "action": row[1],
                        "speaker": row[2],
                        "deadline": row[3],
                    })
                    # Update last_mentioned
                    conn.execute("""
                        UPDATE commitments
                        SET last_mentioned = strftime('%s', 'now'),
                            mention_count = mention_count + 1
                        WHERE id = ?
                    """, (row[0],))

            if matches:
                conn.commit()
            return matches

        except Exception as e:
            logger.error(f"Failed to detect re-mentions: {e}")
            return []
