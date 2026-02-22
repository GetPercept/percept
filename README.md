<p align="center">
  <h1 align="center">◉ Percept</h1>
  <p align="center"><strong>Give your AI agent ears.</strong></p>
  <p align="center"><em>Open-source ambient voice intelligence for AI agents</em></p>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="docs/getting-started.md">Getting Started</a> •
  <a href="docs/api-reference.md">API</a> •
  <a href="docs/architecture.md">Architecture</a> •
  <a href="docs/cli-reference.md">CLI</a> •
  <a href="protocol/PROTOCOL.md">Protocol</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/OpenClaw-Compatible-green.svg" alt="OpenClaw Compatible">
  <img src="https://img.shields.io/badge/NVIDIA-Inception-76B900.svg" alt="NVIDIA Inception">
</p>

---

Percept is an open-source ambient voice pipeline that connects wearable microphones to AI agents. Wear a pendant, speak naturally, and your agent executes voice commands, summarizes meetings, identifies speakers, and builds a searchable knowledge graph — all processed locally on your machine.

**What makes Percept different:** It's not just transcription. The **Context Intelligence Layer (CIL)** transforms raw speech into structured, actionable context — entity extraction, relationship graphs, speaker resolution, and semantic search — so your agent actually *understands* what's being said.

## Quick Start

```bash
# Install
pip install getpercept

# Start the server (receiver on :8900, dashboard on :8960)
percept serve

# Point your Omi webhook to:
#   https://your-host:8900/webhook/transcript
```

Say **"Hey Jarvis, remind me to check email"** and watch it work.

## ✨ Features

### Voice Pipeline
- 🎙️ **Wake Word Detection** — "Hey Jarvis" (configurable via DB settings) triggers voice commands
- ⚡ **7 Action Types** — Email, text, reminders, search, calendar, notes, orders — by voice
- 📝 **Auto Summaries** — Meeting summaries sent via iMessage after 60s of silence
- 🗣️ **Speaker Identification** — Say "that was Sarah" to teach it who's talking
- 👂 **Ambient Logging** — Full transcript history with timestamps and speaker labels
- 🔒 **Local-First** — faster-whisper runs on your machine. Audio never leaves your hardware

### Context Intelligence Layer (CIL)
- 🧠 **Entity Extraction** — Two-pass pipeline: fast regex + LLM semantic extraction
- 🔗 **Relationship Graph** — Auto-builds entity relationships (mentioned_with, works_on, client_of)
- 🎯 **Entity Resolution** — 5-tier cascade: exact → fuzzy → contextual → recency → semantic
- 🔍 **Semantic Search** — NVIDIA NIM embeddings + LanceDB vector store
- 💾 **SQLite Persistence** — Conversations, utterances, speakers, contacts, actions, relationships
- 📊 **FTS5 Full-Text Search** — Porter-stemmed search across all utterances
- ⏰ **TTL Auto-Purge** — Configurable retention: utterances 30d, summaries 90d, relationships 180d

### Intent Parser
- 🏎️ **Two-Tier Hybrid** — Fast regex (handles ~80% of commands instantly) + LLM fallback
- 🔢 **Spoken Number Support** — "thirty minutes" → 1800s, "an hour and a half" → 5400s
- 📇 **Contact Resolution** — "email Sarah" auto-resolves from contacts registry
- 💬 **Spoken Email Normalization** — "david at vectorcare dot com" → user@example.com

## Architecture

```
  Mic (Omi Pendant / Apple Watch)
        │ BLE
  Phone App (streams audio)
        │ Webhook
  Percept Receiver (FastAPI, port 8900)
   ├─ Wake word detection (from DB settings)
   ├─ Intent parser (regex + LLM)
   ├─ Conversation segmentation (3s command / 60s summary)
   ├─ Entity extraction + relationship graph
   ├─ SQLite persistence (conversations, utterances, speakers, actions)
   ├─ LanceDB vector indexing (NVIDIA NIM embeddings)
   └─ Action dispatch → OpenClaw / stdout / webhook
        │
  Dashboard (port 8960)
   ├─ Live transcript feed
   ├─ Conversation history + search
   ├─ Analytics (words/day, speakers, actions)
   ├─ Settings management (wake words, contacts, speakers)
   └─ Data export + purge
```

## Supported Hardware

| Device | Status | Notes |
|--------|--------|-------|
| **Omi Pendant** | ✅ Live | Primary device. BLE to phone, all-day battery. "Critical to our story" |
| **Apple Watch** | 🔜 Beta | WatchOS app built (push-to-talk, raise-to-speak). Needs real device testing |
| **AirPods** | 🔜 Planned | Via phone mic passthrough |
| **Any Webhook Source** | ✅ Ready | Standard HTTP webhook interface — any device that POSTs transcripts |

## Supported Actions

| Action | Voice Example | Resolution |
|--------|---------------|------------|
| **Email** | "Hey Jarvis, email Sarah about the meeting" | Contact lookup → email |
| **Text** | "Hey Jarvis, text Rob I'm running late" | Contact lookup → phone |
| **Reminder** | "Hey Jarvis, remind me in thirty minutes to call the dentist" | Spoken number parsing |
| **Search** | "Hey Jarvis, look up the weather in Cape Town" | Web search |
| **Note** | "Hey Jarvis, remember the API key is in the shared doc" | Context capture |
| **Calendar** | "Hey Jarvis, schedule a call with Mike tomorrow at 2pm" | Calendar integration |
| **Summary** | "Hey Jarvis, summarize this conversation" | On-demand summary |

## CLI Quick Reference

```bash
percept serve                  # Start receiver + dashboard
percept listen                 # Start receiver, output JSON events
percept status                 # Pipeline health check
percept transcripts            # List recent transcripts
percept transcripts --today    # Today's transcripts only
percept actions                # List recent voice actions
percept search "budget"        # Semantic search over conversations
percept audit                  # Data stats (conversations, utterances, storage)
percept purge --older-than 90  # Delete old data
percept config                 # Show configuration
percept config --set whisper.model_size=small
```

> See [CLI Reference](docs/cli-reference.md) for full details.

## Dashboard

The web dashboard runs on port 8960 and provides:

- **Live transcript feed** — real-time stream of what's being said
- **Conversation history** — searchable archive with speaker labels
- **Analytics** — words/day, segments/hour, speaker breakdown, action history
- **Settings page** — manage wake words, speakers, contacts, transcriber config from DB
- **Entity graph** — browse extracted entities and relationships
- **Search** — FTS5 keyword search with LanceDB vector search fallback
- **Data management** — export all data as JSON, purge by TTL or manually

## Transcription

| Transcriber | Status | Use Case |
|-------------|--------|----------|
| **Omi on-device** | ✅ Default | Omi app transcribes locally, sends text via webhook |
| **faster-whisper** | ✅ Built | Local transcription for raw audio (base model, int8, M-series optimized) |
| **NVIDIA Parakeet** | ✅ Tested | NVIDIA NIM ASR via gRPC. Superior accuracy, requires API key |
| **Deepgram** | 🔜 Planned | Cloud ASR option |

Three-tier strategy: **Local (faster-whisper) → NVIDIA (Parakeet NIM) → Cloud (Deepgram)**

## Data Model (SQLite)

| Table | Purpose | Records |
|-------|---------|---------|
| `conversations` | Full conversation records with transcripts, summaries | Core |
| `utterances` | Atomic speech units (FTS5 indexed, porter stemming) | CIL atomic unit |
| `speakers` | Speaker profiles with word counts, relationships | Identity |
| `contacts` | Name → email/phone lookup with aliases | Resolution |
| `actions` | Voice command history with status tracking | Audit |
| `entity_mentions` | Entity occurrences per conversation | CIL extraction |
| `relationships` | Weighted entity graph (source, target, type, evidence) | CIL knowledge |
| `settings` | Runtime config (wake words, timeouts, transcriber) | Config |

## Percept Protocol

The [Percept Protocol](protocol/PROTOCOL.md) defines a framework-agnostic JSON schema for voice→intent→action handoff:

- **6 event types:** transcript, conversation, intent, action_request, action_response, summary
- **3 transports:** JSON Lines on stdout, WebSocket, Webhook
- **Unix composable:** `percept listen | jq 'select(.type == "intent")' | my-agent`

## 📖 Documentation

| Doc | Description |
|-----|-------------|
| [Getting Started](docs/getting-started.md) | Install, configure Omi, first voice command |
| [Configuration](docs/configuration.md) | Config file, wake words, transcriber, CIL settings, environment variables |
| [CLI Reference](docs/cli-reference.md) | Every command, every flag, with examples |
| [API Reference](docs/api-reference.md) | Webhook endpoints, dashboard API, request/response formats |
| [Architecture](docs/architecture.md) | Pipeline diagram, CIL design, data flow, extending Percept |
| [Percept Protocol](docs/percept-protocol.md) | JSON event protocol for agent integration |
| [OpenClaw Integration](docs/openclaw-integration.md) | Using Percept with OpenClaw |
| [Decisions](docs/DECISIONS.md) | Architecture Decision Records — what we chose and why |
| [Roadmap](docs/ROADMAP.md) | Current status and what's next |
| [Contributing](docs/contributing.md) | Dev setup, PR guidelines, good first issues |

## Built for OpenClaw

Percept is designed as a first-class [OpenClaw](https://openclaw.ai) skill, but **works standalone** with any agent framework — LangChain, CrewAI, AutoGen, or a simple webhook.

```bash
# With OpenClaw
openclaw skill install percept

# Without OpenClaw — pipe events anywhere
percept listen --format json | your-agent-consumer
```

Five skill components: `percept-listen`, `percept-voice-cmd`, `percept-summarize`, `percept-speaker-id`, `percept-ambient`

> See [OpenClaw Integration](docs/openclaw-integration.md) for details.

## Project Structure

```
percept/
├── src/
│   ├── receiver.py        # FastAPI server, webhooks, wake word, action dispatch
│   ├── transcriber.py     # faster-whisper transcription, conversation tracking
│   ├── intent_parser.py   # Two-tier intent parser (regex + LLM fallback)
│   ├── database.py        # SQLite persistence (11 tables, FTS5, WAL mode)
│   ├── context_engine.py  # CIL: Context packet assembly, entity resolution
│   ├── entity_extractor.py # CIL: Two-pass entity extraction + relationship building
│   ├── vector_store.py    # NVIDIA NIM embeddings + LanceDB semantic search
│   ├── context.py         # Context extraction, conversation file saving
│   └── cli.py             # CLI entry point (9 commands)
├── config/config.json     # Server, whisper, audio settings
├── data/
│   ├── percept.db         # SQLite database (WAL mode)
│   ├── vectors/           # LanceDB vector store
│   ├── conversations/     # Conversation markdown files
│   ├── summaries/         # Auto-generated summaries
│   ├── speakers.json      # Speaker ID → name mapping
│   └── contacts.json      # Contact registry
├── dashboard/
│   ├── server.py          # Dashboard FastAPI backend (port 8960)
│   └── index.html         # Dashboard web UI
├── protocol/
│   ├── PROTOCOL.md        # Event protocol specification
│   └── schemas/           # JSON Schema for 6 event types
├── landing/               # getpercept.ai landing page (port 8950)
├── watch-app/             # Apple Watch app (push-to-talk, raise-to-speak)
├── scripts/               # Utility scripts (backfill, vector indexing)
├── research/              # Research notes (OpenHome, Zuna BCI, etc.)
└── docs/                  # Full documentation
```

## Contributing

We'd love your help:

1. ⭐ **Star the repo** — helps more than you think
2. 🧪 **Try it** — install, use it for a day, [file issues](https://github.com/getpercept/percept/issues)
3. 🔧 **Build** — language packs, hardware integrations, new action types
4. 📣 **Share** — blog about it, tweet about it

See [Contributing Guide](docs/contributing.md) for dev setup and PR guidelines.

## License

[MIT](LICENSE) — do whatever you want with it.

---

<p align="center">
  <em>"Fei-Fei Li gave AI eyes with ImageNet. We're giving AI agents ears."</em>
</p>
