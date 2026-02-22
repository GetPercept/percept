# Configuration

Percept uses a JSON config file at `config/config.json`.

## Config File

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8900
  },
  "whisper": {
    "model_size": "base",
    "device": "auto",
    "compute_type": "int8",
    "language": "en",
    "beam_size": 5
  },
  "audio": {
    "sample_rate": 16000,
    "channels": 1,
    "sample_width": 2,
    "silence_threshold_seconds": 30,
    "min_audio_length_seconds": 2,
    "max_buffer_seconds": 300
  },
  "memory": {
    "conversations_dir": "/path/to/percept/memory/conversations"
  }
}
```

## Edit via CLI

```bash
# View current config
percept config

# Set a value (supports dotted keys)
percept config --set whisper.model_size=small
percept config --set server.port=9000
percept config --set audio.silence_threshold_seconds=60
```

## Wake Word

The default wake word is **"hey jarvis"**. Wake words are stored in the **SQLite database** (`settings` table) and reload automatically every 60 seconds.

**Manage via Dashboard:**
- Go to `http://localhost:8960` → Settings → Wake Words
- Add/remove wake words through the UI

**Manage via API:**
```bash
# Get current wake words
curl http://localhost:8960/api/settings | jq '.wake_words'

# Update wake words
curl -X POST http://localhost:8960/api/settings \
  -H "Content-Type: application/json" \
  -d '{"wake_words": "[\"hey jarvis\", \"hey alexa\"]"}'
```

**Override via environment variable:**
```bash
export PERCEPT_WAKE_WORD="Hey Alexa"
```

> **Note:** Wake word detection uses simple string matching on transcribed text — no audio-level hotword detection. This means it's language-model dependent and works best in English.

## Database Settings

All runtime settings are stored in the `settings` table and managed via the Dashboard or API:

| Key | Default | Description |
|-----|---------|-------------|
| `wake_words` | `["hey jarvis"]` | JSON array of wake word phrases |
| `silence_timeout` | `3` | Seconds of silence before flushing transcript to agent |
| `conversation_end_timeout` | `60` | Seconds of silence before triggering auto-summary |
| `transcriber` | `omi` | Active transcriber: `omi`, `whisper`, `nvidia-nim` |
| `intent_llm_enabled` | `true` | Enable LLM fallback for intent parsing |
| `intent_llm_model` | `default` | Model for LLM intent parsing |
| `ttl_utterances_days` | `30` | Auto-purge utterances after N days |
| `ttl_summaries_days` | `90` | Auto-purge summaries after N days |
| `ttl_relationships_days` | `180` | Auto-purge relationships after N days |
| `webhook_port` | `8900` | Receiver webhook port |
| `dashboard_port` | `8960` | Dashboard web UI port |

## Transcriber

Percept defaults to **faster-whisper** for local transcription.

| Setting | Options | Default |
|---------|---------|---------|
| `model_size` | `tiny`, `base`, `small`, `medium`, `large-v3` | `base` |
| `device` | `auto`, `cpu`, `cuda` | `auto` |
| `compute_type` | `int8`, `float16`, `float32` | `int8` |
| `language` | Any ISO 639-1 code | `en` |
| `beam_size` | 1–10 | `5` |

**Model size tradeoffs:**

| Model | Speed | Accuracy | VRAM |
|-------|-------|----------|------|
| `tiny` | ⚡⚡⚡ | ★★☆ | ~1 GB |
| `base` | ⚡⚡ | ★★★ | ~1 GB |
| `small` | ⚡ | ★★★★ | ~2 GB |
| `medium` | 🐢 | ★★★★★ | ~5 GB |
| `large-v3` | 🐌 | ★★★★★ | ~10 GB |

On Apple Silicon (M1/M2/M3), `base` with `int8` gives excellent real-time performance.

### Future transcribers

NVIDIA Riva and Deepgram support are planned. The `Transcriber` class in `src/transcriber.py` is designed to be subclassed. See [Architecture > Adding a New Transcriber](architecture.md#adding-a-new-transcriber).

## Intent Parsing

Percept uses a **two-tier hybrid intent parser** (`src/intent_parser.py`):

### Tier 1: Fast Regex
When a wake word is detected, expanded regex patterns try to match the command first. This handles ~80% of clear commands with zero latency.

| Action | Trigger Patterns |
|--------|-----------------|
| `email` | "email [person]...", "send an email to...", "shoot an email to...", "send a message to X via email" |
| `text` | "text [person]...", "message [person]...", "tell [person]...", "shoot X a text", "let X know that..." |
| `reminder` | "remind me to...", "set a reminder...", "follow up with X in Y", "don't forget to...", "make sure I...", "can you remind me..." |
| `search` | "look up...", "search for...", "what is...", "who is...", "look into..." |
| `calendar` | "schedule...", "book...", "set up a meeting...", "put X on my calendar for...", "book time for..." |
| `note` | "remember that...", "note...", "save this...", "write that down", "jot down", "add to my list" |
| `order` | "order...", "buy...", "add ... to shopping list" |

**Spoken numbers** are parsed automatically: "thirty minutes" → 1800 seconds, "an hour and a half" → 5400 seconds.

### Tier 2: LLM Fallback
If no regex matches but a wake word was detected, the parser sends a structured prompt to an LLM for intent classification. This catches conversational phrasing the regex misses.

- Only triggered for wake-word commands (no API burn on ambient speech)
- Results cached for 5 minutes to avoid duplicate calls
- Low-confidence "unknown" results are flagged as `human_required`

### Configuration

Add to `config/config.json`:

```json
{
  "intent": {
    "llm_enabled": true,
    "llm_model": ""
  }
}
```

| Setting | Description | Default |
|---------|-------------|---------|
| `intent.llm_enabled` | Enable LLM fallback when regex doesn't match | `true` |
| `intent.llm_model` | Model for LLM parsing (empty = default agent model) | `""` |

Set `llm_enabled` to `false` to use regex-only parsing (no API calls).

Unmatched commands fall back to a plain `VOICE:` prefix and are forwarded as-is.

## Speaker Registry

Speakers are tracked in both `data/speakers.json` (legacy) and the **SQLite `speakers` table** (primary). The database tracks word counts, segment counts, first/last seen timestamps, and relationships.

**Manage via Dashboard:** Settings → Speakers (add names, relationships)

**Manage via API:**
```bash
# Get all speakers with stats
curl http://localhost:8960/api/settings/speakers

# Update a speaker
curl -X POST http://localhost:8960/api/settings/speakers \
  -H "Content-Type: application/json" \
  -d '{"SPEAKER_01": {"name": "Sarah", "relationship": "colleague"}}'
```

Legacy file `data/speakers.json`:

```json
{
  "SPEAKER_0": {"name": "David", "is_owner": true},
  "SPEAKER_00": {"name": "David", "is_owner": true},
  "SPEAKER_1": {"name": "Unknown", "is_owner": false}
}
```

**Teach Percept who's speaking:**

Say: *"Hey Jarvis, that was Sarah"* — Percept maps the last non-owner speaker ID to "Sarah".

You can also edit `data/speakers.json` directly.

## Contacts Registry

Contacts are stored in both `data/contacts.json` (legacy, used by receiver for lookup) and the **SQLite `contacts` table** (managed via Dashboard).

**Manage via Dashboard:** Settings → Contacts (add/edit/delete with full CRUD)

**Manage via API:**
```bash
# Get all contacts
curl http://localhost:8960/api/settings/contacts

# Add a contact
curl -X POST http://localhost:8960/api/settings/contacts \
  -H "Content-Type: application/json" \
  -d '{"name": "Sarah", "email": "sarah@example.com", "phone": "+15551234567", "relationship": "colleague"}'

# Delete a contact
curl -X DELETE http://localhost:8960/api/settings/contacts/CONTACT_ID
```

Legacy file `data/contacts.json`:

```json
{
  "david": {
    "email": "user@example.com",
    "phone": "+1XXXXXXXXXX",
    "aliases": ["dave"]
  },
  "sarah": {
    "email": "sarah@example.com",
    "phone": "+15551234567",
    "aliases": []
  }
}
```

When you say "email Sarah", Percept looks up the contact by name or alias and resolves the email address. Spoken emails like "david at vectorcare dot com" are also normalized automatically.

## Port Configuration

| Service | Default Port | Config Key |
|---------|-------------|------------|
| Receiver (webhook) | 8900 | `server.port` |
| Dashboard | 8960 | CLI flag `--dashboard-port` |

```bash
percept serve --port 9000 --dashboard-port 9060
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PERCEPT_AGENT` | Agent target: `openclaw`, `stdout`, `webhook` | `openclaw` |
| `PERCEPT_FORMAT` | Output format: `json`, `text` | `json` |
| `PERCEPT_WAKE_WORD` | Wake word phrase | `Hey Jarvis` |
| `PERCEPT_WEBHOOK_URL` | Webhook URL for forwarding events | — |

## Silence & Conversation Thresholds

| Setting | Value | Description |
|---------|-------|-------------|
| `SILENCE_TIMEOUT` | 3s | Silence before flushing transcript to agent |
| `CONVERSATION_END_TIMEOUT` | 60s | Silence before triggering auto-summary |
| `silence_threshold_seconds` | 30s | Audio pipeline conversation break detection |

These are currently hardcoded in `src/receiver.py`. Config-file support is planned.

---

---

## Vector Store

| Setting | Default | Description |
|---------|---------|-------------|
| NVIDIA API key path | `~/.config/nvidia/credentials.json` | JSON with `nim_api_key` field |
| Embedding model | `nvidia/nv-embedqa-e5-v5` | NVIDIA NIM embedding model |
| Vector DB path | `data/vectors/` | LanceDB storage directory |
| Chunk size | 500 chars | Text chunk size for embedding |
| Chunk overlap | 50 chars | Overlap between chunks |

These can be passed to `PerceptVectorStore()` constructor. Config-file support planned.

---

## Context Intelligence Layer (CIL)

### TTL Configuration

Set `ttl_expires` on conversations to auto-purge old data:

```python
# In config/config.json (planned)
{
  "cil": {
    "ttl_default_days": null,    # null = no expiry
    "purge_on_startup": false    # auto-purge expired on server start
  }
}
```

Manual purge:
```bash
percept purge --older-than 90     # Delete conversations > 90 days old
percept purge --conversation ID   # Delete specific conversation
percept purge --all --confirm     # Delete everything
```

### Entity Extraction

| Setting | Default | Description |
|---------|---------|-------------|
| `llm_enabled` | `false` | Enable LLM pass for semantic entity extraction |
| Fuzzy match threshold | 0.85 | SequenceMatcher ratio for fuzzy entity matching |
| Auto-resolve threshold | 0.8 | Confidence above which entities are auto-resolved |
| Soft-resolve threshold | 0.5 | Confidence for soft resolution (flagged) |

### Relationship Decay

| Setting | Default | Description |
|---------|---------|-------------|
| `days_stale` | 7 | Days without seeing a relationship before decay starts |
| `decay_rate` | 0.1 | Weight reduction per decay cycle |

Relationships with weight ≤ 0 are automatically deleted.

Run decay manually:
```python
from src.database import PerceptDB
db = PerceptDB()
db.decay_relationships(days_stale=7, decay_rate=0.1)
```

---

Next: [CLI Reference](cli-reference.md) | [API Reference](api-reference.md)
