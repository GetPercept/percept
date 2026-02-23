"""FastAPI audio webhook receiver for Omi device."""

import json
import os
import shutil
import time
import asyncio
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import re

from src.transcriber import Transcriber, Segment, Conversation
from src.context import save_conversation
from src.intent_parser import IntentParser
from src.database import PerceptDB
from src.entity_extractor import EntityExtractor
from src.context_engine import ContextEngine
from src.speaker_manager import load_speakers, save_speakers, resolve_speaker, resolve_text_with_names, is_speaker_authorized
from src.flush_manager import FlushManager
from src.action_dispatcher import dispatch_to_openclaw, send_imessage, save_action_to_db, extract_command_after_wake
from src.summary_manager import build_transcript_with_names, get_calendar_context, build_day_summary

logger = logging.getLogger(__name__)

# Binary path resolution with fallback
def _get_binary_path(name: str) -> str:
    """Get binary path dynamically with fallback."""
    path = shutil.which(name)
    if not path:
        logger.warning(f"Binary '{name}' not found in PATH, action will be skipped")
        return None
    return path

# Initialize database
_db = PerceptDB()
_entity_extractor = EntityExtractor(db=_db, llm_enabled=False)

# Wake words cache (reloads from DB every 60s)
_wake_words_cache = None
_wake_words_last_load = 0

def _get_wake_words():
    global _wake_words_cache, _wake_words_last_load
    now = time.time()
    if _wake_words_cache is None or (now - _wake_words_last_load) > 60:
        try:
            raw = _db.get_setting('wake_words', '["hey jarvis"]')
            _wake_words_cache = json.loads(raw)
            if not isinstance(_wake_words_cache, list):
                _wake_words_cache = ["hey jarvis"]
        except Exception:
            _wake_words_cache = ["hey jarvis"]
        _wake_words_last_load = now
    return _wake_words_cache
_context_engine = ContextEngine(db=_db)

# --- Speaker Registry (now using imported module) ---

# --- Direct iMessage helper (bypasses OpenClaw session) ---
async def _send_imessage(text: str):
    """Send iMessage directly via imsg CLI — doesn't pollute the main session."""
    try:
        imsg_path = _get_binary_path("imsg")
        if not imsg_path:
            print(f"[IMSG] imsg binary not found, skipping message", flush=True)
            return
            
        env = os.environ.copy()  # Inherit system PATH
        _imsg_target = _db.get_setting("dispatch_target", "+14153414104")
        proc = await asyncio.create_subprocess_exec(
            imsg_path, "send", "--to", _imsg_target, "--text", text,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            print(f"[IMSG] Sent directly", flush=True)
        else:
            print(f"[IMSG] Error: {stderr.decode()[:200]}", flush=True)
    except Exception as e:
        print(f"[IMSG] Failed: {e}", flush=True)


async def _send_reminder(openclaw_path: str, channel: str, target: str, task: str, env: dict):
    """Send a reminder message after the delay has elapsed."""
    try:
        proc = await asyncio.create_subprocess_exec(
            openclaw_path, "message", "send",
            "--channel", channel, "--target", target,
            "--message", f"🔔 Reminder: {task}",
            "--json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        await asyncio.wait_for(proc.communicate(), timeout=15)
        print(f"[REMINDER] Fired: {task}", flush=True)
    except Exception as e:
        print(f"[REMINDER] Failed: {e}", flush=True)


# --- Contacts Registry ---
CONTACTS_FILE = Path(__file__).parent.parent / "data" / "contacts.json"


def _load_contacts() -> dict:
    try:
        with open(CONTACTS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _lookup_contact(name: str, field: str = "email") -> str | None:
    """Look up contact by name or alias. Returns email/phone or None.
    
    "me" / "myself" resolves to the owner contact (is_owner: true in contacts.json).
    First tries the new address book database, then falls back to JSON file.
    """
    # Resolve "me" / "myself" to the owner contact
    if name.lower().strip() in ("me", "myself", "my"):
        contacts = _load_contacts()
        for _cname, info in contacts.items():
            if info.get("is_owner"):
                result = info.get(field)
                if result:
                    logger.info(f"'me' resolved to owner: {_cname} -> {field}={result}")
                    return result
        # Fall back to dispatch_target setting for phone
        if field == "phone":
            return _db.get_setting("dispatch_target", "+14153414104")
        return None

    # Try new address book database first
    try:
        contact = _db.resolve_address_book_contact(name)
        if contact:
            result = contact.get(field)
            if result:
                logger.info(f"Contact resolved from address book: {name} -> {field}={result}")
                return result
    except Exception as e:
        logger.warning(f"Address book lookup failed: {e}")
    
    # Fall back to JSON file
    contacts = _load_contacts()
    name_lower = name.lower().strip()
    for cname, info in contacts.items():
        if cname == name_lower or name_lower in [a.lower() for a in info.get("aliases", [])]:
            result = info.get(field)
            if result:
                logger.info(f"Contact resolved from JSON: {name} -> {field}={result}")
                return result
    
    logger.info(f"Contact not found: {name}")
    return None


def _normalize_spoken_email(text: str) -> str:
    """Convert spoken email: 'jane at example dot com' → 'jane@example.com'"""
    t = text.lower().strip()
    t = re.sub(r'\s+dot\s+com\b', '.com', t)
    t = re.sub(r'\s+dot\s+org\b', '.org', t)
    t = re.sub(r'\s+dot\s+net\b', '.net', t)
    t = re.sub(r'\s+dot\s+io\b', '.io', t)
    t = re.sub(r'\s+dot\s+dev\b', '.dev', t)
    t = re.sub(r'\s+dot\s+', '.', t)
    t = re.sub(r'\s+at\s+', '@', t)
    return t


def _get_context_text(context_segments: list) -> str:
    """Build context string from recent segments."""
    if not context_segments:
        return ""
    return " ".join(s.get("text", "") for s in context_segments[-5:]).strip()


def _dispatch_action(clean_text: str, context_segments: list) -> str:
    """Detect voice command type and format as VOICE_ACTION JSON, or fall back to VOICE: prefix."""
    cmd = clean_text.strip()
    cmd_lower = cmd.lower()
    context_text = _get_context_text(context_segments)

    # 1. EMAIL
    m = re.match(r'(?:send\s+an?\s+)?email\s+(?:to\s+)?(.+)', cmd_lower)
    if m:
        rest = m.group(1).strip()
        body_match = re.split(r'\s+(?:saying|about|that says|with message|with body)\s+', rest, maxsplit=1)
        recipient_part = body_match[0].strip()
        body = body_match[1].strip() if len(body_match) > 1 else ""
        to_addr = _lookup_contact(recipient_part, "email")
        if not to_addr:
            normalized = _normalize_spoken_email(recipient_part)
            to_addr = normalized if '@' in normalized else recipient_part
        subject = body[:50] if body else ""
        if not body:
            body = context_text
        payload = {"action": "email", "to": to_addr, "subject": subject, "body": body}
        return f"VOICE_ACTION: {json.dumps(payload)}"

    # 2. TEXT/MESSAGE
    m = re.match(r'(?:send\s+(?:me\s+)?a?\s*)?(?:text|message)\s+(?:to\s+)?(.+)', cmd_lower)
    if not m:
        m = re.match(r'(?:text|message)\s+(?:me\s+)?(?:saying|that)\s+(.+)', cmd_lower)
    if not m:
        m = re.match(r'tell\s+(.+)', cmd_lower)
    if m:
        rest = m.group(1).strip()
        body_match = re.split(r'\s+(?:saying|that)\s+', rest, maxsplit=1)
        if len(body_match) == 1 and cmd_lower.startswith('tell'):
            body_match = re.split(r'\s+(?:to|that)\s+', rest, maxsplit=1)
        recipient_part = body_match[0].strip()
        message = body_match[1].strip() if len(body_match) > 1 else ""
        # "send me a text" / "text me" = send to David
        if recipient_part.lower() in ("me", "me a text", "myself"):
            recipient_part = "david"
        to = _lookup_contact(recipient_part, "phone") or recipient_part
        if not message:
            message = context_text
        payload = {"action": "text", "to": to, "message": message}
        return f"VOICE_ACTION: {json.dumps(payload)}"

    # 3. REMINDER
    m = re.match(r'(?:set\s+a\s+)?remind(?:er|)\s*(?:me\s+)?(?:in\s+(.+?)\s+to\s+(.+)|to\s+(.+)|(.+))', cmd_lower)
    if m:
        when = (m.group(1) or "").strip()
        task = (m.group(2) or m.group(3) or m.group(4) or "").strip()
        # Also check for trailing time phrases: "do X in 30 minutes"
        if not when:
            time_suffix = re.search(r'\b(?:in\s+)(\d+\s*(?:minutes?|mins?|hours?|hrs?|seconds?|secs?))\b', task)
            if time_suffix:
                when = time_suffix.group(1)
                task = task[:time_suffix.start()].strip().rstrip('.,')
            # Also match spoken numbers: "thirty minutes", "five hours"
            spoken_time = re.search(r'\b(?:in\s+)?(one|two|three|four|five|ten|fifteen|twenty|thirty|forty five|sixty)\s*(minutes?|mins?|hours?|hrs?)\b', task)
            if spoken_time and not when:
                when = f"{spoken_time.group(1)} {spoken_time.group(2)}"
                task = task[:spoken_time.start()].strip().rstrip('.,')
        payload = {"action": "reminder", "task": task, "when": when}
        return f"VOICE_ACTION: {json.dumps(payload)}"

    # 4. SEARCH/RESEARCH
    m = re.match(r'(?:look\s+up|search\s+(?:for\s+)?|find\s+out\s+|research\s+|what\s+is\s+|what\s+are\s+|who\s+is\s+)(.+)', cmd_lower)
    if m:
        query = m.group(1).strip()
        payload = {"action": "search", "query": query, "context": context_text[:500]}
        return f"VOICE_ACTION: {json.dumps(payload)}"

    # 5. ORDER/SHOPPING
    m_shop = re.match(r'add\s+(.+?)\s+to\s+(?:the\s+)?shopping\s+list', cmd_lower)
    if m_shop:
        payload = {"action": "order", "item": m_shop.group(1).strip(), "store": "", "method": "", "context": context_text[:500]}
        return f"VOICE_ACTION: {json.dumps(payload)}"
    m = re.match(r'(?:order|buy)\s+(.+?)(?:\s+from\s+(.+?))?(?:\s+for\s+(pickup|delivery))?$', cmd_lower)
    if m:
        payload = {"action": "order", "item": m.group(1).strip(), "store": (m.group(2) or "").strip(), "method": (m.group(3) or "").strip(), "context": context_text[:500]}
        return f"VOICE_ACTION: {json.dumps(payload)}"

    # 6. CALENDAR
    m = re.match(r'(?:schedule|book)\s+(?:a\s+)?(.+?)(?:\s+with\s+(.+?))?(?:\s+(?:on|at|for)\s+(.+))?$', cmd_lower)
    if not m:
        m = re.match(r'set\s+up\s+(?:a\s+)?meeting\s+with\s+(.+?)(?:\s+(?:on|at|for)\s+(.+))?$', cmd_lower)
        if m:
            payload = {"action": "calendar", "event": f"meeting with {m.group(1).strip()}", "with": m.group(1).strip(), "when": (m.group(2) or "").strip()}
            return f"VOICE_ACTION: {json.dumps(payload)}"
    if not m:
        m = re.match(r'calendar\s+(.+)', cmd_lower)
        if m:
            payload = {"action": "calendar", "event": m.group(1).strip(), "with": "", "when": ""}
            return f"VOICE_ACTION: {json.dumps(payload)}"
    if m:
        event = m.group(1).strip()
        with_person = (m.group(2) or "").strip() if m.lastindex >= 2 else ""
        when = (m.group(3) or "").strip() if m.lastindex >= 3 else ""
        payload = {"action": "calendar", "event": event, "with": with_person, "when": when}
        return f"VOICE_ACTION: {json.dumps(payload)}"

    # 7. NOTE/REMEMBER
    m = re.match(r'(?:remember|note|make\s+a\s+note|save\s+this)\s*(?:that\s+)?(.+)?', cmd_lower)
    if m:
        content = (m.group(1) or "").strip()
        if not content:
            content = context_text
        payload = {"action": "note", "content": content, "context": context_text[:500]}
        return f"VOICE_ACTION: {json.dumps(payload)}"

    # Fallback
    return f"VOICE: {clean_text}"


# Track last non-owner speaker for "that was [name]" command
_last_non_owner_speaker: dict[str, str] = {}

# Load config
CONFIG_PATH = Path(__file__).parent.parent / "config" / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

app = FastAPI(title="Percept Audio Receiver", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize transcriber and intent parser
transcriber = Transcriber(CONFIG)
intent_parser = IntentParser(
    llm_enabled=CONFIG.get("intent", {}).get("llm_enabled", True),
    llm_model=CONFIG.get("intent", {}).get("llm_model", ""),
)

# Audio buffers per user (accumulate chunks before transcribing)
audio_buffers: dict[str, bytes] = defaultdict(bytes)
buffer_timestamps: dict[str, float] = {}

# How many seconds of audio to accumulate before transcribing
BUFFER_SECONDS = 10
SAMPLE_RATE = CONFIG["audio"]["sample_rate"]
BYTES_PER_SECOND = SAMPLE_RATE * CONFIG["audio"]["sample_width"]  # 32000 bytes/sec

# --- Transcript accumulation for OpenClaw forwarding ---
SILENCE_TIMEOUT = 5  # seconds of silence before flushing to OpenClaw
CONVERSATION_END_TIMEOUT = 60  # seconds of silence = conversation over, trigger summary

# Use relative paths from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONVERSATIONS_DIR = PROJECT_ROOT / "data" / "conversations"
CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
LIVE_FILE = Path("/tmp/percept-live.txt")
SUMMARY_LOG = PROJECT_ROOT / "data" / "summaries"
SUMMARY_LOG.mkdir(parents=True, exist_ok=True)

# Per-session accumulation state (short-term, 5s flush)
_accumulated_segments: dict[str, list] = defaultdict(list)
_last_segment_time: dict[str, float] = {}
_flush_tasks: dict[str, asyncio.Task] = {}
_last_wake_flush: dict[str, float] = {}  # track when last wake-word flush happened
WAKE_CONTINUATION_WINDOW = 10  # seconds after a wake flush where new speech is still treated as command

# Conversation-level accumulation (long-term, 60s summary)
_conversation_segments: dict[str, list] = defaultdict(list)
_conversation_start: dict[str, float] = {}
_conversation_end_tasks: dict[str, asyncio.Task] = {}
_last_summary_time: float = 0


COMMAND_TIMEOUT = 5  # extended timeout when wake word/action phrase detected

async def _schedule_flush(session_key: str):
    """Wait for silence, then flush. Extends timeout if wake word detected to capture full command."""
    # First wait the normal silence timeout
    await asyncio.sleep(SILENCE_TIMEOUT)
    # Before flushing, check if buffer has a wake word — if so, keep waiting for more
    current_texts = [s["text"] for s in _accumulated_segments.get(session_key, [])]
    current_full = " ".join(current_texts).lower()
    wake_words = _get_wake_words()
    has_wake = any(w in current_full for w in wake_words)
    if has_wake:
        print(f"[FLUSH] Wake word in buffer — waiting {COMMAND_TIMEOUT}s for full command", flush=True)
        # Wait additional time, but break early if no new segments arrive
        waited = 0
        last_count = len(_accumulated_segments.get(session_key, []))
        while waited < COMMAND_TIMEOUT:
            await asyncio.sleep(1)
            waited += 1
            new_count = len(_accumulated_segments.get(session_key, []))
            if new_count > last_count:
                # New segment arrived, reset wait
                last_count = new_count
                waited = 0
                print(f"[FLUSH] New segment arrived — resetting command wait", flush=True)
    await _flush_transcript(session_key)


async def _flush_transcript(session_key: str):
    """Flush accumulated user transcript to OpenClaw + conversation file."""
    segments = _accumulated_segments.pop(session_key, [])
    _last_segment_time.pop(session_key, None)
    _flush_tasks.pop(session_key, None)

    if not segments:
        return

    # Build full text (user segments only for OpenClaw, all for file)
    user_texts = [s["text"] for s in segments if s.get("is_user")]
    all_texts = [f"[{resolve_speaker(s['speaker'])}] {s['text']}" for s in segments]
    full_text = " ".join(user_texts).strip()
    full_transcript = "\n".join(all_texts)

    if not full_text:
        full_text = " ".join(s["text"] for s in segments).strip()

    if not full_text:
        return

    print(f"[FLUSH] ({len(segments)} segments): {full_text[:200]}", flush=True)

    # Check speaker authorization via DB allowlist
    segment_speakers = set(s.get("speaker", "") for s in segments)
    if _db.has_authorized_speakers():
        # Allowlist is active — check each speaker
        speaker_authorized = any(_db.is_speaker_authorized(spk) for spk in segment_speakers)
        if not speaker_authorized and any(s.get("is_user") for s in segments):
            speaker_authorized = True  # Omi's is_user flag = device owner
        if not speaker_authorized:
            snippet = full_text[:200]
            for spk in segment_speakers:
                _db.log_security_event(spk, snippet, "unauthorized_speaker",
                                       f"Speakers {segment_speakers} not in allowlist")
            print(f"[AUTH] Speakers {segment_speakers} not authorized — blocked", flush=True)
    else:
        # No allowlist configured — backward compatible, allow all
        speaker_authorized = True
    if not speaker_authorized:
        print(f"[AUTH] Speakers {segment_speakers} not authorized — logging only", flush=True)

    # Check for wake word — only forward to OpenClaw if wake word is mentioned
    WAKE_WORDS = _get_wake_words()
    has_wake_word = any(w in full_text.lower() for w in WAKE_WORDS) and speaker_authorized

    # Also treat as wake if within continuation window of a previous wake flush
    if not has_wake_word:
        last_wake = _last_wake_flush.get(session_key, 0)
        if time.time() - last_wake < WAKE_CONTINUATION_WINDOW:
            has_wake_word = True
            print(f"[WAKE] Continuation window — treating as part of previous command", flush=True)

    if has_wake_word:
        if any(w in full_text.lower() for w in WAKE_WORDS):
            print(f"[WAKE] Wake word detected! Forwarding to OpenClaw", flush=True)
        _last_wake_flush[session_key] = time.time()
    else:
        print(f"[SILENT] No wake word — saving to log only", flush=True)

    # 1. Append to rolling live file (always)
    try:
        with open(LIVE_FILE, "a") as f:
            f.write(f"\n--- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(full_transcript + "\n")
    except Exception as e:
        logger.error(f"Failed to write live file: {e}")

    # 2. Save conversation markdown
    try:
        now = datetime.now()
        filename = now.strftime("%Y-%m-%d_%H-%M-%S") + ".md"
        filepath = CONVERSATIONS_DIR / filename
        conv = Conversation(started_at=segments[0].get("start_time", time.time()), last_activity=time.time())
        for s in segments:
            conv.segments.append(Segment(
                text=s["text"], start=s.get("start", 0), end=s.get("end", 0), speaker=s["speaker"]
            ))
        save_conversation(conv, str(CONVERSATIONS_DIR))
    except Exception as e:
        logger.error(f"Failed to save conversation: {e}")

    # 2b. Save to SQLite database
    try:
        now = datetime.now()
        conv_id = now.strftime("%Y-%m-%d_%H-%M")
        speaker_set = list(set(s.get("speaker", "SPEAKER_0") for s in segments))
        word_count = sum(len(s.get("text", "").split()) for s in segments)
        _db.save_conversation(
            id=conv_id, timestamp=time.time(), date=now.strftime("%Y-%m-%d"),
            duration_seconds=segments[-1].get("end", 0) - segments[0].get("start", 0) if len(segments) > 1 else 0,
            segment_count=len(segments), word_count=word_count,
            speakers=speaker_set, transcript=full_transcript,
        )
        # Update speaker word/segment counts
        for s in segments:
            spk = s.get("speaker", "SPEAKER_0")
            wc = len(s.get("text", "").split())
            _db.update_speaker(spk, words_delta=wc, segments_delta=1)
    except Exception as e:
        logger.error(f"Failed to save to database: {e}")

    # 2c. Index in vector store
    try:
        from src.vector_store import PerceptVectorStore
        vs = PerceptVectorStore()
        vs.index_conversation(
            conversation_id=conv_id,
            transcript=full_transcript,
            speakers=speaker_set,
            date=now.strftime("%Y-%m-%d"),
        )
    except Exception as e:
        logger.warning(f"Vector indexing failed: {e}")

    # 3. Forward to OpenClaw via CLI (only if wake word detected)
    if has_wake_word:
        try:
            # Extract command after wake word (handles mid-sentence triggers)
            import re
            clean_text = full_text
            # Find last occurrence of wake word and take everything after it
            match = re.search(r'(?:hey[,.]?\s*)?jarvis[,.\s]*', clean_text, re.IGNORECASE)
            if match:
                clean_text = clean_text[match.end():].strip()
            # Strip trailing punctuation artifacts
            clean_text = clean_text.strip('.,!? ')
            # Check for voice commands
            cmd_lower = (clean_text or full_text).lower()

            # --- "that was [name]" → map last non-owner speaker ---
            that_was_match = re.search(r'that was (\w+)', cmd_lower)
            if that_was_match:
                name = that_was_match.group(1).capitalize()
                conv_key = f"conv_{session_key.split('_')[-1] if '_' in session_key else session_key}"
                last_spk = _last_non_owner_speaker.get(conv_key)
                if last_spk:
                    speakers = load_speakers()
                    speakers[last_spk] = {"name": name, "is_owner": False}
                    save_speakers(speakers)
                    clean_text = f"Mapped {last_spk} to {name}. Text David: 'Got it, I'll remember {name}.'"
                    print(f"[SPEAKER] Mapped {last_spk} → {name}", flush=True)
                else:
                    clean_text = f"No recent non-David speaker to map. Text David that."

            # --- "who was in that conversation?" ---
            elif any(kw in cmd_lower for kw in ["who was in", "who was that", "who was speaking"]):
                speakers = load_speakers()
                seen = set()
                conv_key_check = f"conv_{session_key.split('_')[-1] if '_' in session_key else session_key}"
                for s in _conversation_segments.get(conv_key_check, []):
                    seen.add(s.get("speaker", "SPEAKER_0"))
                names = [resolve_speaker(sid) for sid in seen]
                clean_text = f"Text David the speaker list: {', '.join(names) if names else 'No speakers detected yet.'}"

            # --- "summarize" / "summary" / "recap" → on-demand summary ---
            elif any(kw in cmd_lower for kw in ["summarize", "summary", "recap", "what did we talk about"]):
                conv_key_sum = f"conv_{session_key.split('_')[-1] if '_' in session_key else session_key}"
                segs = _conversation_segments.get(conv_key_sum, [])
                if segs and len(segs) >= 2:
                    # Trigger immediate summary without clearing conversation state
                    asyncio.create_task(_summarize_conversation_on_demand(conv_key_sum))
                    clean_text = "Generating summary of current conversation now. Will text it to you."
                else:
                    clean_text = "Not enough conversation to summarize yet. Text David that."

            # --- "day summary" ---
            elif "day summary" in cmd_lower:
                day_data = _build_day_summary()
                summary_text = (
                    f"Day summary so far:\n"
                    f"• Conversations: {day_data['total_conversations']}\n"
                    f"• Words: {day_data['total_words']}\n"
                    f"• Speakers: {', '.join(day_data['speakers_seen'])}\n"
                    f"• Topics: {'; '.join(day_data['key_topics'][:5]) if day_data['key_topics'] else 'none detected'}"
                )
                clean_text = f"Text David this day summary:\n{summary_text}"

            # --- Task extraction (existing) ---
            elif any(kw in cmd_lower for kw in ["tasks", "action items", "what did we discuss", "any tasks"]):
                tasks = _extract_tasks_from_live(hours=2.0)
                if tasks:
                    task_list = "\n".join(f"• {t['time']} — {t['text']}" for t in tasks)
                    clean_text = f"Here are the tasks from recent conversations. Text them to me:\n{task_list}"
                else:
                    clean_text = "No actionable tasks found in recent conversations. Let David know."

            # Dispatch through intent parser (two-tier: regex + LLM fallback)
            conv_key_ctx = f"conv_{session_key.split('_')[-1] if '_' in session_key else session_key}"
            context_segs = list(_conversation_segments.get(conv_key_ctx, []))[-5:]
            msg = await intent_parser.parse_async(clean_text or full_text, context_segs)
            print(f"[DISPATCH] {msg[:200]}", flush=True)
            # Save action to database if it's a VOICE_ACTION
            _action_id = None
            if msg.startswith("VOICE_ACTION:"):
                try:
                    action_data = json.loads(msg[len("VOICE_ACTION:"):].strip())
                    _action_id = _db.save_action(
                        conversation_id=now.strftime("%Y-%m-%d_%H-%M") if 'now' in dir() else None,
                        intent=action_data.get("action", "unknown"),
                        params=action_data,
                        raw_text=clean_text or full_text,
                    )
                except Exception as e:
                    logger.error(f"Failed to save action to DB: {e}")
            openclaw_path = _get_binary_path("openclaw")
            if not openclaw_path:
                print(f"[OPENCLAW] openclaw binary not found, skipping command", flush=True)
                if _action_id:
                    _db.update_action_status(_action_id, "failed", "openclaw binary not found")
                return
                
            env = os.environ.copy()  # Inherit system PATH
            _dispatch_target = _db.get_setting("dispatch_target", "+14153414104")
            _dispatch_channel = _db.get_setting("dispatch_channel", "imessage")

            # Route by action type — lightweight actions use message send,
            # complex actions use full agent turn
            if msg.startswith("VOICE_ACTION:"):
                try:
                    action_data = json.loads(msg[len("VOICE_ACTION:"):].strip())
                except Exception:
                    action_data = {}

                action_type = action_data.get("action", "unknown")

                if action_type == "reminder":
                    # Direct reminder: send confirmation now, schedule reminder message
                    task = action_data.get("task", "something")
                    when = action_data.get("when", "soon")
                    when_seconds = action_data.get("when_seconds", 300)
                    # Send confirmation
                    confirm_proc = await asyncio.create_subprocess_exec(
                        openclaw_path, "message", "send",
                        "--channel", _dispatch_channel, "--target", _dispatch_target,
                        "--message", f"⏰ Reminder set ({when}): {task}",
                        "--json",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
                    )
                    await asyncio.wait_for(confirm_proc.communicate(), timeout=15)
                    # Schedule the actual reminder via at/sleep
                    asyncio.get_event_loop().call_later(
                        when_seconds,
                        lambda t=task: asyncio.ensure_future(_send_reminder(openclaw_path, _dispatch_channel, _dispatch_target, t, env))
                    )
                    print(f"[OPENCLAW] Reminder set: '{task}' in {when_seconds}s", flush=True)
                    if _action_id:
                        _db.update_action_status(_action_id, "executed", f"Reminder: {task} in {when}")
                elif action_type == "text":
                    # Direct text message
                    to = action_data.get("to", _dispatch_target)
                    body = action_data.get("body", action_data.get("message", ""))
                    proc = await asyncio.create_subprocess_exec(
                        openclaw_path, "message", "send",
                        "--channel", _dispatch_channel, "--target", to,
                        "--message", body, "--json",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
                    if proc.returncode == 0:
                        print(f"[OPENCLAW] Text sent to {to}", flush=True)
                        if _action_id:
                            _db.update_action_status(_action_id, "executed", f"Sent to {to}")
                    else:
                        print(f"[OPENCLAW] Text error: {stderr.decode()[:200]}", flush=True)
                        if _action_id:
                            _db.update_action_status(_action_id, "failed", stderr.decode()[:500])
                else:
                    # Complex actions (email, search, calendar, etc.) — use full agent turn
                    proc = await asyncio.create_subprocess_exec(
                        openclaw_path, "agent", "--message", msg,
                        "--to", _dispatch_target, "--channel", _dispatch_channel, "--deliver",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                    if proc.returncode == 0:
                        print(f"[OPENCLAW] Agent turn completed", flush=True)
                        if _action_id:
                            _db.update_action_status(_action_id, "executed", stdout.decode()[:500])
                    else:
                        print(f"[OPENCLAW] Error: {stderr.decode()[:200]}", flush=True)
                        if _action_id:
                            _db.update_action_status(_action_id, "failed", stderr.decode()[:500])
            else:
                # VOICE: prefix — general command, use agent turn
                proc = await asyncio.create_subprocess_exec(
                    openclaw_path, "agent", "--message", msg,
                    "--to", _dispatch_target, "--channel", _dispatch_channel, "--deliver",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                if proc.returncode == 0:
                    print(f"[OPENCLAW] Sent successfully", flush=True)
                    if _action_id:
                        _db.update_action_status(_action_id, "executed", stdout.decode()[:500])
                else:
                    print(f"[OPENCLAW] Error: {stderr.decode()[:200]}", flush=True)
                    if _action_id:
                        _db.update_action_status(_action_id, "failed", stderr.decode()[:500])
        except Exception as e:
            logger.error(f"Failed to send to OpenClaw: {e}")
            if _action_id:
                try:
                    _db.update_action_status(_action_id, "failed", str(e))
                except Exception:
                    pass


async def _schedule_conversation_end(session_key: str):
    """Wait for extended silence, then generate conversation summary."""
    await asyncio.sleep(CONVERSATION_END_TIMEOUT)
    await _summarize_conversation(session_key)


async def _summarize_conversation(session_key: str):
    """Generate and send conversation summary when silence detected."""
    segments = _conversation_segments.pop(session_key, [])
    start_time = _conversation_start.pop(session_key, None)
    _conversation_end_tasks.pop(session_key, None)
    
    if not segments or len(segments) < 3:
        return  # Too short to summarize
    
    # Build full transcript with resolved names
    all_texts = []
    speakers = set()
    for s in segments:
        speaker_id = s.get("speaker", "SPEAKER_0")
        speaker_name = resolve_speaker(speaker_id)
        speakers.add(speaker_name)
        all_texts.append(f"[{speaker_name}] {s['text']}")
    
    full_transcript = "\n".join(all_texts)
    duration_min = (time.time() - (start_time or time.time())) / 60
    
    # Skip very short conversations (< 30 seconds of actual speech)
    total_words = sum(len(s["text"].split()) for s in segments)
    if total_words < 20:
        print(f"[SUMMARY] Skipping — only {total_words} words", flush=True)
        return
    
    print(f"[SUMMARY] Conversation ended: {len(segments)} segments, {total_words} words, {duration_min:.1f} min, speakers: {speakers}", flush=True)

    # Run entity extraction on conversation utterances
    try:
        conv_id_ee = datetime.now().strftime("%Y-%m-%d_%H-%M")
        utterance_dicts = [{"text": s.get("text", ""), "speaker_id": s.get("speaker", "SPEAKER_00")} for s in segments]
        entities = _entity_extractor.extract_from_utterances(utterance_dicts, conv_id_ee)
        # Save entity mentions
        for e in entities:
            _db.save_entity_mention(conv_id_ee, e.type, e.resolved_name or e.name)
        # Build relationships from co-occurring entities
        _entity_extractor.build_relationships(entities, conv_id_ee)
        if entities:
            print(f"[CIL] Extracted {len(entities)} entities, built relationships", flush=True)
    except Exception as e:
        logger.warning(f"Entity extraction failed: {e}")

    # Save raw transcript
    now = datetime.now()
    filename = now.strftime("%Y-%m-%d_%H-%M-%S") + "_conversation.md"
    try:
        with open(SUMMARY_LOG / filename, "w") as f:
            f.write(f"# Conversation — {now.strftime('%Y-%m-%d %H:%M')}\n")
            f.write(f"Duration: ~{duration_min:.0f} min | Segments: {len(segments)} | Speakers: {', '.join(speakers)}\n\n")
            f.write("## Transcript\n")
            f.write(full_transcript + "\n")
    except Exception as e:
        print(f"[SUMMARY] Failed to save transcript: {e}", flush=True)
    
    # Calendar context
    calendar_context = await _get_calendar_context(start_time)
    
    # Send to OpenClaw for AI-powered summary
    summary_prompt = f"""CONVERSATION_SUMMARY: A conversation just ended ({duration_min:.0f} min, speakers: {', '.join(speakers)}, {total_words} words). 

Analyze this transcript and text David a brief summary with:
1. Who was in the conversation (if identifiable)
2. Key topics discussed (2-3 bullet points)
3. Action items / commitments made
4. Any decisions reached
5. Anything that needs follow-up

If the conversation is just casual chat with no action items, keep it to 1-2 lines.
If it's a meeting/business discussion, be thorough.
{calendar_context}

TRANSCRIPT:
{full_transcript[-3000:]}"""
    
    try:
        openclaw_path = _get_binary_path("openclaw")
        if not openclaw_path:
            print(f"[SUMMARY] openclaw binary not found, skipping LLM summary", flush=True)
            return
            
        env = os.environ.copy()  # Inherit system PATH
        # First get the LLM summary (without delivering)
        proc_summary = await asyncio.create_subprocess_exec(
            openclaw_path, "agent", "--message", summary_prompt, "--to", "+1XXXXXXXXXX", "--json",  # TODO: load from config
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        summary_stdout, summary_stderr = await asyncio.wait_for(proc_summary.communicate(), timeout=60)
        llm_summary = ""
        if proc_summary.returncode == 0:
            try:
                import json as _json
                result = _json.loads(summary_stdout.decode())
                # Extract from nested OpenClaw JSON response
                if "result" in result and "payloads" in result["result"]:
                    payloads = result["result"]["payloads"]
                    llm_summary = payloads[0].get("text", "") if payloads else ""
                else:
                    llm_summary = result.get("reply", "") or result.get("message", "") or summary_stdout.decode()
            except Exception:
                llm_summary = summary_stdout.decode().strip()
            # Save LLM summary to database
            if llm_summary:
                conv_id_sum = now.strftime("%Y-%m-%d_%H-%M")
                try:
                    _db._conn.execute("UPDATE conversations SET summary = ? WHERE id = ?", (llm_summary, conv_id_sum))
                    _db._conn.commit()
                    print(f"[SUMMARY] LLM summary saved to DB", flush=True)
                except Exception as e:
                    logger.warning(f"Failed to save LLM summary to DB: {e}")
                # Also save to file
                try:
                    summary_file = SUMMARY_LOG / now.strftime("%Y-%m-%d_%H-%M-%S") + "_summary.md"
                    with open(summary_file, "w") as sf:
                        sf.write(f"# Summary — {now.strftime('%Y-%m-%d %H:%M')}\n\n{llm_summary}\n")
                except Exception:
                    pass
        # Then deliver via iMessage
        proc = await asyncio.create_subprocess_exec(
            openclaw_path, "agent", "--message", summary_prompt, "--channel", "imessage", "--deliver",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode == 0:
            print(f"[SUMMARY] Sent via iMessage directly", flush=True)
        else:
            # Fallback
            brief = f"📝 Conversation ended ({duration_min:.0f} min, {len(speakers)} speakers, {total_words} words)."
            await _send_imessage(brief)
    except Exception as e:
        print(f"[SUMMARY] Failed: {e}", flush=True)


async def _summarize_conversation_on_demand(conv_key: str):
    """Generate summary immediately without ending the conversation."""
    segments = list(_conversation_segments.get(conv_key, []))
    start_time = _conversation_start.get(conv_key)

    if not segments or len(segments) < 2:
        return

    all_texts = []
    speakers = set()
    for s in segments:
        speaker = resolve_speaker(s.get("speaker", "SPEAKER_0"))
        speakers.add(speaker)
        all_texts.append(f"[{speaker}] {s['text']}")

    full_transcript = "\n".join(all_texts)
    duration_min = (time.time() - (start_time or time.time())) / 60
    total_words = sum(len(s["text"].split()) for s in segments)

    print(f"[ON-DEMAND SUMMARY] {len(segments)} segments, {total_words} words", flush=True)

    # Calendar context
    calendar_context = await _get_calendar_context(start_time)

    summary_prompt = f"""CONVERSATION_SUMMARY (on-demand): Summarize this ongoing conversation ({duration_min:.0f} min, speakers: {', '.join(speakers)}, {total_words} words).

Text David a brief summary with:
1. Key topics (2-3 bullets)
2. Action items
3. Decisions reached
{calendar_context}

TRANSCRIPT:
{full_transcript[-3000:]}"""

    try:
        openclaw_path = _get_binary_path("openclaw")
        if not openclaw_path:
            print(f"[ON-DEMAND SUMMARY] openclaw binary not found, skipping", flush=True)
            return
            
        env = os.environ.copy()  # Inherit system PATH
        proc = await asyncio.create_subprocess_exec(
            openclaw_path, "agent", "--message", summary_prompt, "--channel", "imessage", "--deliver",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await asyncio.wait_for(proc.communicate(), timeout=60)
        print(f"[ON-DEMAND SUMMARY] Sent via iMessage", flush=True)
    except Exception as e:
        print(f"[ON-DEMAND SUMMARY] Failed: {e}", flush=True)


async def _get_calendar_context(start_time: float = None) -> str:
    """Try to match conversation against today's calendar events."""
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
        return f"\nCalendar context (conversation started ~{conv_time}):\n{cal_output}\nIf a calendar event matches the timing, mention: 'This was likely your [time] [event name].'"
    except Exception:
        return ""


def _build_day_summary() -> dict:
    """Build day summary from /tmp/percept-live.txt."""
    today_str = datetime.now().strftime('%Y-%m-%d')
    result = {"total_conversations": 0, "total_words": 0, "speakers_seen": [], "key_topics": [], "date": today_str}

    if not LIVE_FILE.exists():
        return result

    speakers = set()
    conversations = 0
    words = 0
    all_text = []
    in_today = False

    for line in LIVE_FILE.read_text().split('\n'):
        line = line.strip()
        if line.startswith('--- ') and line.endswith(' ---'):
            ts_str = line.strip('- ')
            if ts_str.startswith(today_str):
                in_today = True
                conversations += 1
            else:
                in_today = False
            continue
        if not in_today or not line:
            continue
        if line.startswith('[SPEAKER_') or line.startswith('['):
            bracket_end = line.find(']')
            if bracket_end > 0:
                speaker = line[1:bracket_end]
                speakers.add(resolve_speaker(speaker))
                text = line[bracket_end + 2:] if bracket_end + 2 < len(line) else ""
                words += len(text.split())
                all_text.append(text)

    # Extract key topics via simple keyword frequency
    from collections import Counter
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "i", "you", "we", "they", "it", "to", "and", "of", "in", "that", "for", "on", "with", "so", "but", "just", "like", "yeah", "okay", "right", "um", "uh", "know", "think", "going", "got", "well", "dont", "thats", "its", "have", "been", "this", "not", "what", "about", "do", "be", "my", "your", "he", "she", "me", "or", "if", "at", "from", "can", "will", "one", "all", "would", "there", "their", "up", "out", "then"}
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


async def _check_ambient_question(text: str, context_segments: list):
    """Detect if someone asked a question that Jarvis could answer proactively."""
    import re
    
    # Question patterns
    question_indicators = [
        r'\b(what|when|where|who|how much|how many|how long|how far)\b.*\?',
        r'\b(do you know|does anyone know|any idea|what\'s the|who\'s the)\b',
        r'\b(what time|what date|what day|how do we|how do you)\b',
    ]
    
    text_lower = text.lower()
    
    # Check if it's a question
    is_question = any(re.search(p, text_lower) for p in question_indicators)
    if not is_question:
        return
    
    # Skip questions that are clearly rhetorical or conversational
    skip_patterns = [r'how are you', r'what\'s up', r'you know what i mean', r'right\?$', r'isn\'t it\?$']
    if any(re.search(p, text_lower) for p in skip_patterns):
        return
    
    # Skip if Jarvis was already invoked (wake word handles it)
    if 'jarvis' in text_lower:
        return
    
    print(f"[AMBIENT] Question detected: {text[:100]}", flush=True)
    
    # Build context from recent segments
    recent = " ".join(s["text"] for s in context_segments[-5:])
    
    prompt = f"""AMBIENT_QUESTION: Someone near David just asked a question in conversation. If you can answer it helpfully, text David the answer so he looks brilliant. If it's not something you can answer or it's rhetorical, respond with NO_REPLY.

Context: {recent[-500:]}
Question: {text}"""
    
    try:
        openclaw_path = _get_binary_path("openclaw")
        if not openclaw_path:
            print(f"[AMBIENT] openclaw binary not found, skipping", flush=True)
            return
            
        env = os.environ.copy()  # Inherit system PATH
        proc = await asyncio.create_subprocess_exec(
            openclaw_path, "agent", "--message", prompt, "--to", "+1XXXXXXXXXX",  # TODO: load from config
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        print(f"[AMBIENT] Sent to OpenClaw", flush=True)
    except Exception as e:
        print(f"[AMBIENT] Failed: {e}", flush=True)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "percept",
        "uptime": time.time(),
        "model": CONFIG["whisper"]["model_size"],
    }


@app.get("/webhook/audio")
async def audio_health():
    """GET handler for Omi webhook validation."""
    return {"status": "ok"}


@app.post("/webhook/audio")
async def receive_audio(
    request: Request,
    uid: str = Query(default="default"),
    sample_rate: int = Query(default=16000),
):
    """Receive raw PCM16 audio bytes from Omi device.

    Omi sends: POST /webhook/audio?sample_rate=16000&uid=USER_ID
    Body: raw PCM16 bytes (application/octet-stream)
    """
    # Webhook authentication
    auth_error = _check_webhook_auth(request)
    if auth_error:
        _db.log_security_event("unknown", f"uid={uid}", auth_error,
                               "Missing or invalid Authorization header on /webhook/audio")
        return JSONResponse({"status": "unauthorized"}, status_code=401)

    audio_bytes = await request.body()
    if not audio_bytes:
        return JSONResponse({"status": "empty"}, status_code=400)

    audio_buffers[uid] += audio_bytes
    buffer_timestamps[uid] = time.time()

    logger.debug(f"Received {len(audio_bytes)} bytes from uid={uid} (buffer: {len(audio_buffers[uid])} bytes)")

    # Process when we have enough audio
    buffer_duration = len(audio_buffers[uid]) / (sample_rate * 2)
    if buffer_duration >= BUFFER_SECONDS:
        pcm_data = audio_buffers[uid]
        audio_buffers[uid] = b""

        # Run transcription in background to not block the webhook response
        asyncio.create_task(_transcribe_and_save(pcm_data, sample_rate))

    return {"status": "ok"}


async def _transcribe_and_save(pcm_data: bytes, sample_rate: int):
    """Background task: transcribe audio and save completed conversations."""
    try:
        loop = asyncio.get_event_loop()
        segments, completed = await loop.run_in_executor(
            None, transcriber.process_chunk, pcm_data, sample_rate
        )

        if segments:
            logger.info(f"Transcribed: {' | '.join(s.text for s in segments[:3])}")

        if completed and completed.segments:
            save_conversation(completed, CONFIG["memory"]["conversations_dir"])
    except Exception as e:
        logger.error(f"Transcription pipeline error: {e}", exc_info=True)


@app.get("/webhook/transcript")
async def transcript_health():
    """GET handler for Omi webhook validation."""
    return {"status": "ok"}


def _check_webhook_auth(request: Request) -> str | None:
    """Validate webhook auth via Authorization header OR ?token= query param.
    Returns None if OK, or an error reason string if rejected."""
    secret = _db.get_setting("webhook_secret")
    if not secret:
        return None  # No secret configured — allow all
    # Check Authorization header first
    auth_header = request.headers.get("Authorization", "")
    if auth_header == f"Bearer {secret}":
        return None  # Valid via header
    # Check URL query parameter as fallback (for apps that don't support headers)
    token_param = request.query_params.get("token", "")
    if token_param == secret:
        return None  # Valid via URL token
    return "invalid_webhook_auth"


@app.post("/webhook/transcript")
async def receive_transcript(
    request: Request,
    session_id: str = Query(default=""),
    uid: str = Query(default="default"),
):
    """Receive real-time transcript segments from Omi.

    Omi sends: POST /webhook/transcript?session_id=abc&uid=USER_ID
    Body: JSON array of transcript segments
    [{"text": "...", "speaker": "SPEAKER_00", "speakerId": 0,
      "is_user": false, "start": 10.0, "end": 15.0}]
    """
    # Webhook authentication
    auth_error = _check_webhook_auth(request)
    if auth_error:
        _db.log_security_event("unknown", f"uid={uid}", auth_error,
                               f"Missing or invalid Authorization header")
        logger.warning(f"[WEBHOOK AUTH] Rejected request from uid={uid}")
        return JSONResponse({"status": "unauthorized"}, status_code=401)

    raw = await request.body()
    print(f"[TRANSCRIPT RAW] {raw[:2000]}", flush=True)

    try:
        segments_data = await request.json()
    except Exception:
        # Try parsing raw since body was already consumed
        import json as _json
        try:
            segments_data = _json.loads(raw)
        except Exception:
            return JSONResponse({"status": "invalid json"}, status_code=400)

    # Omi wraps segments in {"segments": [...], "session_id": "..."}
    if isinstance(segments_data, dict) and "segments" in segments_data:
        session_id = segments_data.get("session_id", session_id)
        segments_data = segments_data["segments"]

    if not isinstance(segments_data, list):
        segments_data = [segments_data]

    segments = []
    for s in segments_data:
        seg = Segment(
            text=s.get("text", ""),
            start=s.get("start", 0.0),
            end=s.get("end", 0.0),
            speaker=s.get("speaker", "SPEAKER_00"),
        )
        if seg.text.strip():
            segments.append(seg)
            transcriber.current_conversation.segments.append(seg)
            transcriber.current_conversation.last_activity = time.time()
            print(f"[TRANSCRIPT] [{seg.speaker}] {seg.text}", flush=True)

    # Save individual utterances to DB
    now_dt = datetime.now()
    conv_id_utt = now_dt.strftime("%Y-%m-%d_%H-%M")
    for s in segments_data:
        text = s.get("text", "").strip()
        if text:
            try:
                utt_id = f"{conv_id_utt}_{s.get('start', 0):.1f}"
                _db.save_utterance(
                    id=utt_id,
                    conversation_id=conv_id_utt,
                    speaker_id=s.get("speaker", "SPEAKER_00"),
                    text=text,
                    started_at=s.get("start", 0.0),
                    ended_at=s.get("end", 0.0),
                    confidence=None,
                    is_command=any(w in text.lower() for w in ["jarvis", "hey jarvis"]),
                )
            except Exception as e:
                logger.debug(f"Failed to save utterance: {e}")

    # Accumulate for OpenClaw forwarding
    session_key = session_id or uid
    for s in segments_data:
        _accumulated_segments[session_key].append({
            "text": s.get("text", ""),
            "speaker": s.get("speaker", "SPEAKER_00"),
            "is_user": s.get("is_user", False),
            "start": s.get("start", 0.0),
            "end": s.get("end", 0.0),
            "start_time": time.time(),
        })
    _last_segment_time[session_key] = time.time()

    # Cancel previous flush timer and start a new one (3s - for wake word commands)
    if session_key in _flush_tasks:
        _flush_tasks[session_key].cancel()
    _flush_tasks[session_key] = asyncio.create_task(_schedule_flush(session_key))

    # Conversation-level accumulation (60s - for summaries)
    conv_key = f"conv_{uid}"
    if conv_key not in _conversation_start:
        _conversation_start[conv_key] = time.time()
    for s in segments_data:
        seg_data = {
            "text": s.get("text", ""),
            "speaker": s.get("speaker", "SPEAKER_00"),
            "is_user": s.get("is_user", False),
        }
        _conversation_segments[conv_key].append(seg_data)
        # Track last non-owner speaker for "that was [name]" command
        speaker_id = s.get("speaker", "SPEAKER_00")
        speakers_db = load_speakers()
        speaker_entry = speakers_db.get(speaker_id, {})
        if not speaker_entry.get("is_owner", False) and not s.get("is_user", False):
            _last_non_owner_speaker[conv_key] = speaker_id
        
        # Ambient question detection DISABLED — too noisy with regex approach
        # TODO: Re-enable with AI-based filtering (only factual questions)
        # if not s.get("is_user", False) and "?" in s.get("text", ""):
        #     asyncio.create_task(_check_ambient_question(
        #         s.get("text", ""), _conversation_segments[conv_key]
        #     ))

    # Reset conversation end timer
    if conv_key in _conversation_end_tasks:
        _conversation_end_tasks[conv_key].cancel()
    _conversation_end_tasks[conv_key] = asyncio.create_task(_schedule_conversation_end(conv_key))

    print(f"[TRANSCRIPT] Received {len(segments)} segments (session={session_id})", flush=True)
    return {"status": "ok", "segments_received": len(segments)}


@app.post("/webhook/memory")
async def receive_memory(
    request: Request,
    uid: str = Query(default="default"),
):
    """Receive completed memory/conversation from Omi.

    Omi sends the full memory object when a conversation is finalized.
    """
    # Webhook authentication
    auth_error = _check_webhook_auth(request)
    if auth_error:
        _db.log_security_event("unknown", f"uid={uid}", auth_error,
                               "Missing or invalid Authorization header on /webhook/memory")
        return JSONResponse({"status": "unauthorized"}, status_code=401)

    try:
        memory = await request.json()
    except Exception:
        return JSONResponse({"status": "invalid json"}, status_code=400)

    # Extract transcript segments from Omi's memory format
    transcript_segments = memory.get("transcript_segments", [])
    structured = memory.get("structured", {})

    if transcript_segments:
        from src.transcriber import Conversation
        conv = Conversation(
            started_at=time.time(),
            last_activity=time.time(),
        )
        for s in transcript_segments:
            conv.segments.append(Segment(
                text=s.get("text", ""),
                start=s.get("start", 0.0),
                end=s.get("end", 0.0),
                speaker=s.get("speaker", "SPEAKER_00"),
            ))
        save_conversation(conv, CONFIG["memory"]["conversations_dir"])
        logger.info(f"Saved Omi memory: {structured.get('title', 'untitled')}")

    return {"status": "ok"}


@app.get("/conversations")
async def list_conversations():
    """List saved conversation files."""
    conv_dir = Path(CONFIG["memory"]["conversations_dir"])
    if not conv_dir.exists():
        return {"conversations": []}
    files = sorted(conv_dir.glob("*.md"), reverse=True)
    return {"conversations": [f.name for f in files[:50]]}


@app.get("/status")
async def status():
    """Current pipeline status."""
    return {
        "active_buffers": len(audio_buffers),
        "current_conversation_segments": len(transcriber.current_conversation.segments),
        "completed_conversations": len(transcriber.completed_conversations),
        "buffer_sizes": {uid: len(buf) for uid, buf in audio_buffers.items()},
    }


@app.get("/day-summary")
async def day_summary():
    """Day summary: total conversations, words, speakers, topics."""
    return _build_day_summary()


@app.get("/context")
async def context():
    """Current conversation context."""
    active_speakers = set()
    total_segments = 0
    conv_duration = 0
    for key, segs in _conversation_segments.items():
        total_segments += len(segs)
        for s in segs:
            active_speakers.add(resolve_speaker(s.get("speaker", "SPEAKER_0")))
    for key, start in _conversation_start.items():
        dur = time.time() - start
        if dur > conv_duration:
            conv_duration = dur
    return {
        "active_speakers": sorted(active_speakers),
        "conversation_duration_sec": round(conv_duration, 1),
        "segments_count": total_segments,
        "active_conversations": len(_conversation_segments),
    }


@app.get("/tasks")
async def extract_tasks(hours: float = Query(default=1.0)):
    """Extract tasks/action items from recent transcripts."""
    tasks = _extract_tasks_from_live(hours)
    return {"tasks": tasks, "hours_scanned": hours, "source": str(LIVE_FILE)}


def _extract_tasks_from_live(hours: float = 1.0) -> list[dict]:
    """Parse /tmp/percept-live.txt for actionable items."""
    if not LIVE_FILE.exists():
        return []

    cutoff = datetime.now() - __import__('datetime').timedelta(hours=hours)
    tasks = []
    current_time = None
    current_texts = []

    # Task indicator patterns
    import re
    task_patterns = [
        re.compile(r'\b(send|email|text|call|schedule|book|set up|create|build|write|draft|check|look into|research|find|order|buy|cancel|update|fix|deploy|push|review|follow up|remind)\b', re.IGNORECASE),
        re.compile(r'\b(can you|could you|please|need to|have to|should|let\'s|gonna|going to|want to|i\'ll|we need)\b', re.IGNORECASE),
    ]

    for line in LIVE_FILE.read_text().split('\n'):
        line = line.strip()
        if not line:
            continue

        # Parse timestamp lines
        if line.startswith('--- ') and line.endswith(' ---'):
            ts_str = line.strip('- ')
            try:
                current_time = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                current_time = None
            current_texts = []
            continue

        # Skip old entries
        if current_time and current_time < cutoff:
            continue

        # Extract speaker text
        if line.startswith('[SPEAKER_'):
            text = line.split('] ', 1)[-1] if '] ' in line else line
            current_texts.append(text)

            # Check if this line contains a task
            action_match = task_patterns[0].search(text)
            intent_match = task_patterns[1].search(text)

            if action_match and (intent_match or len(text) > 20):
                tasks.append({
                    "text": text,
                    "action": action_match.group(0).lower(),
                    "time": current_time.strftime('%H:%M') if current_time else "unknown",
                    "context": ' '.join(current_texts[-3:]),
                })

    # Deduplicate similar tasks
    seen = set()
    unique_tasks = []
    for t in tasks:
        key = t["action"] + t["text"][:30].lower()
        if key not in seen:
            seen.add(key)
            unique_tasks.append(t)

    return unique_tasks
