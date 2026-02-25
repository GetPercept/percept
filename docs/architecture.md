# Architecture

## Pipeline Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     INPUT SOURCES                             │
│                                                              │
│  Omi Pendant → Phone → Webhook POST (real-time)              │
│  Zoom → Cloud Recording → percept zoom-sync (batch)          │
│  Granola → Local Cache → percept granola-sync (batch)        │
│  Apple Watch → Push-to-Talk → /webhook/audio (real-time)     │
│  Any VTT file → percept zoom-import (manual)                 │
└──────────────┬──────────────────────┬────────────────────────┘
               │                      │
        /webhook/audio         /webhook/transcript
        (raw PCM16)            (pre-transcribed JSON)
               │                      │
┌──────────────▼──────────────────────▼────────────────────────┐
│                    RECEIVER (src/receiver.py)                  │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │
│  │ Audio Buffer │  │  Segment     │  │ Conversation        │  │
│  │ (10s chunks) │  │  Accumulator │  │ Accumulator (60s)   │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬──────────┘  │
│         │                │                      │             │
│  ┌──────▼──────┐  ┌──────▼───────┐  ┌──────────▼──────────┐  │
│  │ Transcriber │  │ Wake Word    │  │ Auto-Summary        │  │
│  │ (Whisper)   │  │ Detection    │  │ (after 60s silence) │  │
│  └─────────────┘  └──────┬───────┘  └──────────┬──────────┘  │
│                          │                      │             │
│                   ┌──────▼───────┐              │             │
│                   │ Action       │              │             │
│                   │ Dispatcher   │              │             │
│                   └──────┬───────┘              │             │
└──────────────────────────┼──────────────────────┼────────────┘
                           │                      │
                    ┌──────▼──────────────────────▼─────┐
                    │           OUTPUT LAYER             │
                    │                                    │
                    │  OpenClaw  ← clawhub install       │
                    │              percept-meetings      │
                    │  Claude    ← MCP server (8 tools)  │
                    │  ChatGPT  ← Actions API (REST)    │
                    │  CLI      ← percept search/status  │
                    │  Webhook  ← custom endpoint        │
                    └───────────────────────────────────┘
```

## Context Intelligence Layer (CIL)

The CIL transforms raw transcripts into structured, actionable context:

```
┌───────────────────────────────────────────────────────────┐
│                  Context Intelligence Layer                 │
│                                                            │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │  Entity      │   │ Relationship │   │ Context Packet │  │
│  │  Extractor   │──▶│ Graph        │──▶│ Assembly       │  │
│  │              │   │              │   │                │  │
│  │ Fast: regex  │   │ mentioned_   │   │ Conversation   │  │
│  │ LLM: semantic│   │ with, works_ │   │ + Entities +   │  │
│  │              │   │ on, client_of│   │ Context        │  │
│  └──────┬───────┘   └──────────────┘   └───────┬────────┘  │
│         │                                       │          │
│  ┌──────▼───────┐                      ┌───────▼────────┐  │
│  │ Resolution   │                      │ Context Packet │  │
│  │ exact→fuzzy  │                      │ JSON output    │  │
│  │ →graph→      │                      │ for agents     │  │
│  │ recency      │                      └────────────────┘  │
│  └──────────────┘                                          │
└───────────────────────────────────────────────────────────┘
```

### Data Model

- **utterances** — atomic speech units with timestamps, speaker, FTS5 indexed
- **relationships** — weighted entity graph (source, target, type, evidence)
- **entity_mentions** — entity occurrences per conversation

### Entity Resolution Pipeline

1. **Exact match** — speaker name or contact name
2. **Fuzzy match** — SequenceMatcher ≥ 0.85 threshold
3. **Contextual match** — traverse relationship graph (e.g., "the client" → client_of relationship)
4. **Recency match** — pronoun resolution from recent utterances
5. **Semantic search** — vector store fallback

### Confidence Thresholds

- ≥ 0.8: auto-resolve
- 0.5–0.8: soft-resolve (flagged)
- < 0.5: needs_human

### Context Packet Format

```json
{
  "conversation": {"id": "...", "mode": "ambient", "duration_minutes": 5.2, "speakers": [...]},
  "command": {"raw_text": "...", "intent": "email", "resolved_entities": {...}},
  "recent_context": ["snippet1", "snippet2"]
}
```

## Directory Structure

```
percept/
├── src/
│   ├── receiver.py      # FastAPI server, webhooks, wake word, action dispatch
│   ├── transcriber.py   # Whisper transcription, conversation tracking
│   ├── context.py       # Context extraction, conversation saving
│   ├── context_engine.py # CIL: Context packet assembly
│   ├── entity_extractor.py # CIL: Two-pass entity extraction + resolution
│   ├── intent_parser.py # Two-tier intent parser (regex + LLM)
│   ├── database.py      # SQLite persistence (conversations, utterances, relationships)
│   ├── vector_store.py  # NVIDIA NIM + LanceDB semantic search
│   ├── chatgpt_actions.py # ChatGPT Custom GPT Actions API (port 8901)
│   ├── zoom_connector.py  # Zoom: webhook, batch sync, VTT import
│   ├── mcp_server.py     # MCP server for Claude Desktop (8 tools + 2 resources)
│   └── cli.py           # CLI entry point
├── config/
│   └── config.json      # Server, whisper, audio settings
├── data/
│   ├── conversations/   # Saved conversation markdown files
│   ├── summaries/       # Auto-generated conversation summaries
│   ├── speakers.json    # Speaker ID → name mapping
│   └── contacts.json    # Contact name → email/phone lookup
├── dashboard/
│   ├── server.py        # Dashboard FastAPI backend (port 8960)
│   └── index.html       # Dashboard web UI
├── protocol/
│   ├── PROTOCOL.md      # Event protocol specification
│   └── schemas/         # JSON Schema for each event type
│       ├── transcript_event.json
│       ├── conversation_event.json
│       ├── intent_event.json
│       ├── action_request.json
│       ├── action_response.json
│       └── summary_event.json
└── docs/                # This documentation
```

## Data Flow: Voice Command

Here's exactly what happens when you say "Hey Jarvis, email Sarah about the meeting":

1. **Omi pendant** captures audio via BLE, sends to phone app
2. **Omi app** transcribes on-device, POSTs segments to `POST /webhook/transcript`
3. **Receiver** accumulates segments per session in `_accumulated_segments`
4. After **3 seconds of silence**, `_schedule_flush()` fires
5. `_flush_transcript()` joins segment text, checks for **wake words** (`WAKE_WORDS = ["jarvis", "hey jarvis", "hey, jarvis"]`)
6. Wake word found → extract command text after the wake word
7. **IntentParser** (`src/intent_parser.py`) processes the command through two tiers:
   - **Tier 1 (regex):** Expanded patterns try to match — handles ~80% of clear commands instantly
   - `email sarah about the meeting` → matches email pattern → looks up "sarah" in contacts → resolves email
   - Also handles spoken numbers: "thirty minutes" → 1800 seconds, "an hour and a half" → 5400
   - **Tier 2 (LLM fallback):** If regex fails, sends structured prompt to LLM for intent classification
   - Returns `VOICE_ACTION: {"action": "email", "to": "sarah@example.com", "subject": "about the meeting", "body": "..."}`
8. Dispatched to **OpenClaw** via CLI: `openclaw agent --message "VOICE_ACTION: {...}"`
9. OpenClaw agent executes the email action

## Data Flow: Auto-Summary

1. Segments accumulate in `_conversation_segments` per device UID
2. Each new segment resets the 60-second timer (`_schedule_conversation_end()`)
3. After **60 seconds of silence**, `_summarize_conversation()` fires
4. Builds full transcript with resolved speaker names
5. Checks calendar context (via `gog cal list`) for meeting matching
6. Sends prompt to OpenClaw: `CONVERSATION_SUMMARY: ...` with transcript
7. OpenClaw generates summary and delivers via iMessage

## Stage-by-Stage Reference

### 1. Receiver (`src/receiver.py`)

The main FastAPI application. Responsibilities:
- Accept Omi webhooks (audio, transcript, memory)
- Buffer and accumulate transcript segments
- Detect wake words and dispatch voice commands
- Track conversations and trigger auto-summaries
- Manage speaker registry and contact lookups
- Serve status/context/tasks API endpoints

Key globals:
- `_accumulated_segments` — short-term buffer (3s flush for commands)
- `_conversation_segments` — long-term buffer (60s for summaries)
- `_last_non_owner_speaker` — tracks last unknown speaker for "that was [name]"

### 2. Transcriber (`src/transcriber.py`)

Wraps `faster-whisper` for local transcription.

Classes:
- `Segment` — dataclass: `text`, `start`, `end`, `speaker`
- `Conversation` — dataclass: list of segments with `started_at`/`last_activity`, `full_text` property
- `Transcriber` — initializes WhisperModel, provides `transcribe_audio()`, `process_chunk()`, `diarize()` (placeholder)

The transcriber handles the raw audio path (`/webhook/audio`). For the transcript path (`/webhook/transcript`), Omi sends pre-transcribed text and the `Transcriber` is used only for conversation tracking.

### 3. Context Engine (`src/context.py`)

Two functions:
- `extract_context(conversation)` — keyword-based extraction of action items, people, and topics from conversation text. No API calls needed.
- `save_conversation(conversation, dir)` — writes a markdown file with metadata, action items, and full transcript.

### 4. CLI (`src/cli.py`)

Entry point for all user commands. Delegates to:
- `cmd_serve()` — starts receiver + dashboard
- `cmd_listen()` — starts receiver with configurable output
- `cmd_status()` — checks health endpoint, counts today's files
- `cmd_transcripts()` — lists/searches conversation files
- `cmd_actions()` — lists action JSON files
- `cmd_config()` — reads/writes `config/config.json`

## Adding a New Transcriber

1. Create a new class in `src/transcriber.py` (or a new file):

```python
class DeepgramTranscriber:
    def __init__(self, config: dict):
        self.api_key = config["deepgram"]["api_key"]
    
    def transcribe_audio(self, pcm_data: bytes, sample_rate: int = 16000) -> list[Segment]:
        # Send audio to Deepgram API
        # Return list of Segment objects
        pass
    
    def process_chunk(self, pcm_data: bytes, sample_rate: int = 16000):
        segments = self.transcribe_audio(pcm_data, sample_rate)
        return segments, None
```

2. In `src/receiver.py`, select the transcriber based on config:

```python
if CONFIG.get("transcriber") == "deepgram":
    transcriber = DeepgramTranscriber(CONFIG)
else:
    transcriber = Transcriber(CONFIG)
```

## Adding a New Action Type

Add a new regex pattern in `IntentParser._try_regex()` in `src/intent_parser.py`:

```python
# WEATHER
m = re.match(r'(?:what\'?s the )?weather\s+(?:in\s+)?(.+)', cmd_lower)
if m:
    return ParseResult(intent="weather", params={"location": m.group(1).strip()}, raw_text=text)
```

The LLM fallback will also attempt to parse new intent types if listed in the prompt template. The agent (OpenClaw or your webhook consumer) handles execution.

## Adding New Hardware

Percept accepts audio/transcripts via standard HTTP webhooks. To add a new device:

1. Implement a webhook sender on the device/app that POSTs to either:
   - `POST /webhook/audio` — raw PCM16 bytes
   - `POST /webhook/transcript` — JSON segments: `[{"text": "...", "speaker": "...", "start": 0.0, "end": 3.5}]`

2. Include a `uid` query parameter to identify the device

That's it. The rest of the pipeline (wake word, actions, summaries) works identically regardless of hardware source.

---

---

## Vector Store (Semantic Search)

Percept uses a **dual-store architecture**:

| Store | Purpose | Technology |
|-------|---------|------------|
| **SQLite** | Structured data — conversations, speakers, actions, contacts | `data/percept.db` |
| **LanceDB** | Semantic vectors — conversation chunks for similarity search | `data/vectors/` |

### How it works

1. **Indexing**: When a conversation is saved, it's chunked into ~500-char overlapping passages
2. **Embedding**: Each chunk is embedded via NVIDIA NIM API (`nvidia/nv-embedqa-e5-v5`)
3. **Storage**: Embeddings + metadata stored in LanceDB (local, no server needed)
4. **Search**: Query text is embedded with `input_type="query"`, then nearest-neighbor searched

### Key design decisions

- **Summaries are indexed separately** — they're high-signal, short vectors
- **Passage vs Query embedding types** — NVIDIA's model uses asymmetric embeddings
- **Graceful degradation** — if NVIDIA API is down, indexing is skipped silently
- **No re-embedding** — already-indexed conversations are skipped on bulk index
- **Rate limiting** — 0.1s sleep between API calls during bulk indexing

### Integration points

- `receiver.py` → indexes new conversations automatically after SQLite save
- `intent_parser.py` → uses semantic context for ambiguous entity resolution ("email the client")
- `cli.py` → `percept search "query"` command
- `dashboard/server.py` → `/api/search?q=query` endpoint

---

Next: [Percept Protocol](percept-protocol.md) | [Contributing](contributing.md)
