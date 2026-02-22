"""Two-tier intent parser: fast regex + LLM fallback."""

import json
import re
import shutil
import time
import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Binary path resolution with fallback
def _get_binary_path(name: str) -> str:
    """Get binary path dynamically with fallback."""
    path = shutil.which(name)
    if not path:
        logger.warning(f"Binary '{name}' not found in PATH, action will be skipped")
        return None
    return path

# ---------------------------------------------------------------------------
# Spoken number / time parser
# ---------------------------------------------------------------------------

SPOKEN_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "forty five": 45, "a": 1, "an": 1, "half": 30,
}

TIME_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
    "half hour": 1800, "half an hour": 1800,
}


def _parse_spoken_number(text: str) -> Optional[int]:
    """Parse a spoken number phrase into an integer.
    
    Handles: "thirty", "forty five", "twenty five", compound tens+units.
    """
    text = text.strip().lower()
    # Direct lookup (includes multi-word like "forty five")
    if text in SPOKEN_NUMBERS:
        return SPOKEN_NUMBERS[text]
    # Try as digit
    try:
        return int(text)
    except ValueError:
        pass
    # Compound: "twenty five", "thirty two", etc.
    parts = text.split()
    if len(parts) == 2 and parts[0] in SPOKEN_NUMBERS and parts[1] in SPOKEN_NUMBERS:
        tens = SPOKEN_NUMBERS[parts[0]]
        ones = SPOKEN_NUMBERS[parts[1]]
        if tens >= 20 and ones < 10:
            return tens + ones
    return None


def parse_spoken_duration(text: str) -> Optional[int]:
    """Parse a spoken duration string into seconds.
    
    Examples:
        "thirty minutes" → 1800
        "five hours" → 18000
        "an hour and a half" → 5400
        "forty five minutes" → 2700
        "2 hours" → 7200
        "half an hour" → 1800
    """
    text = text.strip().lower()
    total = 0
    found = False

    # Handle "half an hour" / "half hour" specially
    for phrase, secs in [("half an hour", 1800), ("half hour", 1800)]:
        if phrase in text:
            total += secs
            text = text.replace(phrase, "")
            found = True

    # Handle "an hour and a half" → split on "and"
    # Also handles "an hour" standalone
    parts = re.split(r'\s+and\s+', text)
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # "a half" standalone after "and"
        if part in ("a half", "half"):
            # Need context — assume half of the previous unit
            # Default: half hour = 1800
            total += 1800
            found = True
            continue

        # Try matching "<number> <unit>"
        # Multi-word numbers first: "forty five minutes"
        matched = False
        for unit_phrase, unit_secs in sorted(TIME_UNITS.items(), key=lambda x: -len(x[0])):
            pattern = rf'^(.+?)\s+{re.escape(unit_phrase)}s?$'
            m = re.match(pattern, part)
            if m:
                num = _parse_spoken_number(m.group(1).strip())
                if num is not None:
                    total += num * unit_secs
                    found = True
                    matched = True
                    break
        if matched:
            continue

        # "an hour", "a minute"
        for unit_phrase, unit_secs in TIME_UNITS.items():
            if part in (f"an {unit_phrase}", f"a {unit_phrase}"):
                total += unit_secs
                found = True
                break

    return total if found else None


# ---------------------------------------------------------------------------
# Contacts / email helpers (imported from receiver)
# ---------------------------------------------------------------------------

def _lazy_receiver():
    """Import receiver helpers lazily to avoid circular imports."""
    from src.receiver import _lookup_contact, _normalize_spoken_email, _get_context_text
    return _lookup_contact, _normalize_spoken_email, _get_context_text


def _extract_clean_email(text: str) -> str:
    """Extract clean email address from text, stripping trailing punctuation and words."""
    # First look for standard email pattern
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    if email_match:
        return email_match.group(0)
    # If no standard email found, return normalized text (for spoken emails)
    return text.strip()


def _extract_clean_phone(text: str) -> str:
    """Extract clean phone number from text, stripping trailing punctuation and words."""
    # Look for phone patterns: +1234567890, (123) 456-7890, 123-456-7890, etc.
    phone_patterns = [
        r'\+?1?[-\s]?\(?(\d{3})\)?[-\s]?(\d{3})[-\s]?(\d{4})',  # US phone formats
        r'\+\d{1,3}[-\s]?\d{3,14}',  # International format
    ]
    
    for pattern in phone_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    
    # If no phone pattern found, return original text stripped
    return text.strip()


# ---------------------------------------------------------------------------
# Regex patterns (Tier 1)
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    intent: str  # email, text, reminder, search, order, calendar, note, unknown
    params: dict = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 1.0
    source: str = "regex"  # "regex" or "llm"
    human_required: bool = False

    def to_voice_action(self) -> str:
        """Format as VOICE_ACTION: {json} string."""
        return f"VOICE_ACTION: {json.dumps({'action': self.intent, **self.params})}"


class IntentParser:
    """Two-tier intent parser: fast regex first, LLM fallback second."""

    def __init__(self, llm_enabled: bool = True, llm_model: str = ""):
        self.llm_enabled = llm_enabled
        self.llm_model = llm_model
        self._cache: dict[str, tuple[str, float]] = {}  # text -> (result, timestamp)
        self._cache_ttl = 300  # 5 minutes
        self._vector_store = None

    def _get_vector_store(self):
        if self._vector_store is None:
            try:
                from src.vector_store import PerceptVectorStore
                self._vector_store = PerceptVectorStore()
            except Exception:
                pass
        return self._vector_store

    def parse(self, text: str, context_segments: list = None) -> str:
        """Parse text into a VOICE_ACTION string or VOICE: fallback.
        
        Returns same format as old _dispatch_action() for compatibility.
        """
        context_segments = context_segments or []
        result = self._try_regex(text, context_segments)
        if result:
            self._save_to_db(result)
            return result.to_voice_action()

        # Tier 2: LLM fallback (async not available in sync context, return fallback)
        # The async version is parse_async()
        return f"VOICE: {text}"

    async def parse_async(self, text: str, context_segments: list = None) -> str:
        """Async version with LLM fallback."""
        context_segments = context_segments or []
        result = self._try_regex(text, context_segments)
        if result:
            self._save_to_db(result)
            return result.to_voice_action()

        # Tier 2: LLM fallback
        if self.llm_enabled:
            result = await self._try_llm(text, context_segments)
            if result and result.intent != "unknown":
                self._save_to_db(result)
                return result.to_voice_action()
            if result and result.human_required:
                return f"VOICE_ACTION: {json.dumps({'action': 'unknown', 'text': text, 'human_required': True})}"

        return f"VOICE: {text}"

    def _get_context_text(self, context_segments: list) -> str:
        if not context_segments:
            return ""
        return " ".join(s.get("text", "") for s in context_segments[-5:]).strip()

    def _try_regex(self, text: str, context_segments: list) -> Optional[ParseResult]:
        """Tier 1: Fast regex matching with expanded patterns."""
        cmd = text.strip()
        cmd_lower = cmd.lower()
        context_text = self._get_context_text(context_segments)

        # --- EMAIL ---
        email_patterns = [
            r'(?:send\s+an?\s+)?email\s+(?:to\s+)?(.+)',
            r'shoot\s+an?\s+email\s+(?:to\s+)?(.+)',
            r'send\s+a\s+message\s+to\s+(.+?)\s+via\s+email(?:\s+(.*))?',
            r'email\s+(\S+)\s+about\s+(.+)',
        ]
        for pat in email_patterns:
            m = re.match(pat, cmd_lower)
            if m:
                return self._parse_email(m, cmd_lower, context_text)

        # --- TEXT/MESSAGE ---
        text_patterns = [
            r'(?:send\s+(?:me\s+)?a?\s*)?(?:text|message)\s+(?:to\s+)?(.+)',
            r'(?:text|message)\s+(?:me\s+)?(?:saying|that)\s+(.+)',
            r'shoot\s+(\S+)\s+a\s+text(?:\s+(.*))?',
            r'let\s+(\S+)\s+know\s+(?:that\s+)?(.+)',
            r'tell\s+(.+)',
        ]
        for pat in text_patterns:
            m = re.match(pat, cmd_lower)
            if m:
                return self._parse_text(m, cmd_lower, context_text, pat)

        # --- REMINDER (expanded) ---
        reminder_patterns = [
            r'(?:set\s+a\s+)?remind(?:er|)\s*(?:me\s+)?(?:in\s+(.+?)\s+to\s+(.+)|to\s+(.+)|(.+))',
            r'follow\s+up\s+with\s+(.+?)(?:\s+in\s+(.+))?$',
            r'(?:don\'?t\s+forget|make\s+sure\s+(?:I|i|we))\s+(?:to\s+)?(.+)',
            r'can\s+you\s+remind\s+(?:me\s+)?(?:to\s+)?(.+)',
        ]
        for i, pat in enumerate(reminder_patterns):
            m = re.match(pat, cmd_lower)
            if m:
                return self._parse_reminder(m, cmd_lower, context_text, pattern_index=i)

        # --- SEARCH ---
        m = re.match(r'(?:look\s+up|search\s+(?:for\s+)?|find\s+out\s+|research\s+|what\s+is\s+|what\s+are\s+|who\s+is\s+|look\s+into\s+)(.+)', cmd_lower)
        if m:
            return ParseResult(intent="search", params={"query": m.group(1).strip(), "context": context_text[:500]}, raw_text=text)

        # --- NOTE (expanded) --- must be before ORDER to catch "add to my list"
        note_patterns = [
            r'(?:remember|note|make\s+a\s+note|save\s+this)\s*(?:that\s+)?(.+)?',
            r'(?:write\s+that\s+down|jot\s+(?:that\s+)?down|save\s+that)(?:\s*[:\-]\s*(.+))?',
            r'add\s+(?:that\s+)?to\s+my\s+(?:notes?|list)(?:\s*[:\-]\s*(.+))?',
        ]
        for pat in note_patterns:
            m = re.match(pat, cmd_lower)
            if m:
                content = ""
                for g in range(1, (m.lastindex or 0) + 1):
                    val = m.group(g)
                    if val and val.strip():
                        content = val.strip()
                        break
                if not content:
                    content = context_text
                return ParseResult(intent="note", params={"content": content, "context": context_text[:500]}, raw_text=text)

        # --- ORDER/SHOPPING ---
        m_shop = re.match(r'add\s+(.+?)\s+to\s+(?:the\s+)?shopping\s+list', cmd_lower)
        if m_shop:
            return ParseResult(intent="order", params={"item": m_shop.group(1).strip(), "store": "", "method": "", "context": context_text[:500]}, raw_text=text)
        m = re.match(r'(?:order|buy)\s+(.+?)(?:\s+from\s+(.+?))?(?:\s+for\s+(pickup|delivery))?$', cmd_lower)
        if m:
            return ParseResult(intent="order", params={"item": m.group(1).strip(), "store": (m.group(2) or "").strip(), "method": (m.group(3) or "").strip(), "context": context_text[:500]}, raw_text=text)

        # --- CALENDAR (expanded) ---
        calendar_patterns = [
            r'(?:schedule|book)\s+(?:a\s+)?(.+?)(?:\s+with\s+(.+?))?(?:\s+(?:on|at|for)\s+(.+))?$',
            r'set\s+up\s+(?:a\s+)?meeting\s+with\s+(.+?)(?:\s+(?:on|at|for)\s+(.+))?$',
            r'(?:put|add)\s+(?:that\s+|the\s+)?(.+?)\s+(?:on|to)\s+(?:my\s+)?calendar(?:\s+(?:for|on|at)\s+(.+))?',
            r'book\s+(?:a\s+)?time\s+(?:for|to)\s+(.+?)(?:\s+(?:on|at|for)\s+(.+))?$',
            r'calendar\s+(.+)',
        ]
        for pat in calendar_patterns:
            m = re.match(pat, cmd_lower)
            if m:
                return self._parse_calendar(m, cmd_lower, context_text, pat)

        return None

    def _parse_email(self, m: re.Match, cmd_lower: str, context_text: str) -> ParseResult:
        _lookup_contact, _normalize_spoken_email, _ = _lazy_receiver()
        rest = m.group(1).strip()
        # Check if pattern has explicit "about" group
        if m.lastindex and m.lastindex >= 2 and m.group(2):
            recipient_part = rest
            body = m.group(2).strip()
        else:
            body_match = re.split(r'\s+(?:saying|about|that says|with message|with body)\s+', rest, maxsplit=1)
            recipient_part = body_match[0].strip()
            body = body_match[1].strip() if len(body_match) > 1 else ""
        
        # Clean up the recipient part - extract only the email address
        to_addr = _lookup_contact(recipient_part, "email")
        if not to_addr:
            normalized = _normalize_spoken_email(recipient_part)
            if '@' in normalized:
                to_addr = _extract_clean_email(normalized)
            else:
                to_addr = _extract_clean_email(recipient_part)
        
        subject = body[:50] if body else ""
        if not body:
            body = context_text
        return ParseResult(intent="email", params={"to": to_addr, "subject": subject, "body": body}, raw_text=cmd_lower)

    def _parse_text(self, m: re.Match, cmd_lower: str, context_text: str, pattern: str) -> ParseResult:
        _lookup_contact, _, _ = _lazy_receiver()
        rest = m.group(1).strip()

        # Patterns with explicit message group
        if m.lastindex and m.lastindex >= 2 and m.group(2):
            recipient_part = rest if 'shoot' in pattern or 'let' in pattern else m.group(1).strip()
            # For "shoot X a text Y" or "let X know Y"
            recipient_part = m.group(1).strip()
            message = m.group(2).strip()
        else:
            body_match = re.split(r'\s+(?:saying|that)\s+', rest, maxsplit=1)
            if len(body_match) == 1 and 'tell' in pattern:
                body_match = re.split(r'\s+(?:to|that)\s+', rest, maxsplit=1)
            if len(body_match) > 1:
                recipient_part = body_match[0].strip()
                message = body_match[1].strip()
            else:
                # No explicit separator — try to split on first known contact name
                # e.g. "text David the demo is working" → recipient=David, message=the demo is working
                words = rest.split()
                if len(words) >= 2:
                    # Check if first word is a contact
                    first_word = words[0]
                    if _lookup_contact(first_word, "phone"):
                        recipient_part = first_word
                        message = " ".join(words[1:])
                    else:
                        recipient_part = rest
                        message = ""
                else:
                    recipient_part = rest
                    message = ""

        if recipient_part.lower() in ("me", "me a text", "myself"):
            recipient_part = "david"
        
        # Clean up the recipient part - extract only the phone number
        to = _lookup_contact(recipient_part, "phone")
        if not to:
            to = _extract_clean_phone(recipient_part)
        
        if not message:
            message = context_text
        return ParseResult(intent="text", params={"to": to, "message": message}, raw_text=cmd_lower)

    def _parse_reminder(self, m: re.Match, cmd_lower: str, context_text: str, pattern_index: int) -> ParseResult:
        task = ""
        when = ""

        if pattern_index == 0:
            # Original reminder pattern
            when = (m.group(1) or "").strip()
            task = (m.group(2) or m.group(3) or m.group(4) or "").strip()
        elif pattern_index == 1:
            # "follow up with X [in Y]"
            task = f"follow up with {m.group(1).strip()}"
            when = (m.group(2) or "").strip() if m.lastindex >= 2 else ""
        elif pattern_index == 2:
            # "don't forget to X" / "make sure I X"
            task = m.group(1).strip()
        elif pattern_index == 3:
            # "can you remind me to X"
            task = m.group(1).strip()

        # Extract trailing time from task: "do X in thirty minutes"
        if not when:
            # Digit-based: "in 30 minutes"
            time_suffix = re.search(r'\b(?:in\s+)(\d+\s*(?:minutes?|mins?|hours?|hrs?|seconds?|secs?))\b', task)
            if time_suffix:
                when = time_suffix.group(1)
                task = task[:time_suffix.start()].strip().rstrip('.,')

        if not when:
            # Spoken number: "in thirty minutes"
            spoken_time = re.search(
                r'\b(?:in\s+)((?:(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|'
                r'thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|'
                r'fifty|sixty|seventy|eighty|ninety|forty five|an?|half)\s*)+)'
                r'\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b', task)
            if spoken_time:
                when = f"{spoken_time.group(1).strip()} {spoken_time.group(2)}"
                task = task[:spoken_time.start()].strip().rstrip('.,')

        # Convert spoken when to seconds if possible
        when_seconds = None
        if when:
            when_seconds = parse_spoken_duration(when)

        params = {"task": task, "when": when}
        if when_seconds is not None:
            params["when_seconds"] = when_seconds

        return ParseResult(intent="reminder", params=params, raw_text=cmd_lower)

    def _parse_calendar(self, m: re.Match, cmd_lower: str, context_text: str, pattern: str) -> ParseResult:
        if 'meeting' in pattern:
            event = f"meeting with {m.group(1).strip()}"
            with_person = m.group(1).strip()
            when = (m.group(2) or "").strip() if m.lastindex >= 2 else ""
        elif 'put' in pattern or 'add' in pattern:
            event = m.group(1).strip()
            with_person = ""
            when = (m.group(2) or "").strip() if m.lastindex >= 2 else ""
        elif 'book' in pattern and 'time' in pattern:
            event = m.group(1).strip()
            with_person = ""
            when = (m.group(2) or "").strip() if m.lastindex >= 2 else ""
        elif pattern == r'calendar\s+(.+)':
            event = m.group(1).strip()
            with_person = ""
            when = ""
        else:
            event = m.group(1).strip()
            with_person = (m.group(2) or "").strip() if m.lastindex >= 2 else ""
            when = (m.group(3) or "").strip() if m.lastindex >= 3 else ""

        return ParseResult(intent="calendar", params={"event": event, "with": with_person, "when": when}, raw_text=cmd_lower)

    # --- Tier 2: LLM Fallback ---

    async def _try_llm(self, text: str, context_segments: list) -> Optional[ParseResult]:
        """Use LLM to parse intent when regex fails."""
        # Check cache
        cache_key = text.strip().lower()
        if cache_key in self._cache:
            cached_result, cached_time = self._cache[cache_key]
            if time.time() - cached_time < self._cache_ttl:
                logger.info(f"[INTENT] Cache hit for: {text[:50]}")
                return cached_result

        context_text = " ".join(s.get("text", "") for s in context_segments[-3:])

        # Enrich with semantic context for ambiguous references
        semantic_context = ""
        ambiguous_refs = ["the client", "the team", "that meeting", "that person", "them", "him", "her"]
        if any(ref in text.lower() for ref in ambiguous_refs):
            vs = self._get_vector_store()
            if vs:
                try:
                    semantic_context = vs.get_relevant_context(text, minutes=60, limit=3)
                    if semantic_context:
                        semantic_context = f"\nRelevant conversation history:\n{semantic_context[:1000]}"
                except Exception:
                    pass

        prompt = f"""Parse this voice command into a structured action.
Command: "{text}"
Recent context: "{context_text}"
{semantic_context}

Respond with JSON only:
{{"intent": "email|text|reminder|search|order|calendar|note|unknown", "params": {{}}, "confidence": 0.0-1.0, "human_required": false}}

For params, include relevant fields:
- email: to, subject, body
- text: to, message
- reminder: task, when, when_seconds (if duration mentioned)
- search: query
- order: item, store
- calendar: event, with, when
- note: content"""

        try:
            openclaw_path = _get_binary_path("openclaw")
            if not openclaw_path:
                logger.warning("[INTENT] openclaw binary not found, skipping LLM fallback")
                return None
                
            env = os.environ.copy()  # Inherit system PATH
            proc = await asyncio.create_subprocess_exec(
                openclaw_path, "agent", "--message",
                f"INTENT_PARSE (respond with raw JSON only, no markdown): {prompt}",
                "--to", "+1XXXXXXXXXX", "--json",  # TODO: load from config
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)

            if proc.returncode != 0:
                logger.warning(f"[INTENT] LLM call failed: {stderr.decode()[:200]}")
                return None

            response = stdout.decode().strip()
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]+\}', response)
            if not json_match:
                logger.warning(f"[INTENT] No JSON in LLM response: {response[:200]}")
                return None

            parsed = json.loads(json_match.group())
            intent = parsed.get("intent", "unknown")
            params = parsed.get("params", {})
            confidence = parsed.get("confidence", 0.5)
            human_required = parsed.get("human_required", False)

            if intent == "unknown" and confidence < 0.3:
                human_required = True

            result = ParseResult(
                intent=intent,
                params=params,
                raw_text=text,
                confidence=confidence,
                source="llm",
                human_required=human_required,
            )

            # Cache it
            self._cache[cache_key] = (result, time.time())
            logger.info(f"[INTENT] LLM parsed: {intent} (confidence={confidence})")
            return result

        except asyncio.TimeoutError:
            logger.warning("[INTENT] LLM call timed out")
            return None
        except Exception as e:
            logger.error(f"[INTENT] LLM error: {e}")
            return None

    def _save_to_db(self, result: ParseResult):
        """Save parsed intent to database if available."""
        try:
            from src.database import PerceptDB
            db = PerceptDB()
            db.save_action(
                intent=result.intent,
                params=result.params,
                raw_text=result.raw_text,
                status='pending',
            )
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"[INTENT] DB save failed: {e}")
