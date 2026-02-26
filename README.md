<!-- mcp-name: io.github.getpercept/percept -->
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

### 🎙️ Ambient Voice Pipeline
https://github.com/GetPercept/percept/raw/main/demo.mp4

### 🤖 MCP Integration — Claude Desktop
https://github.com/GetPercept/percept/raw/main/demo-mcp.mov

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

### Security
- 🔐 **Speaker Authorization** — Allowlist of authorized speakers. Only approved voices trigger commands
- 🔑 **Webhook Authentication** — Bearer token or URL token (`?token=`) on all webhook endpoints
- 📋 **Security Audit Log** — All blocked attempts logged with timestamp, speaker, transcript snippet, and reason
- 🛡️ **Command Safety Classifier** — 6-category pattern matching blocks exfiltration, credential access, destructive commands, network changes, info leaks, and prompt injection. Pen tested: 7/7 attacks blocked
- 🏠 **Local-First** — Audio and transcripts never leave your machine. No cloud dependency
- 📖 **[Full security documentation →](SECURITY.md)**

### Intent Parser
- 🏎️ **Two-Tier Hybrid** — Fast regex (handles ~80% of commands instantly) + LLM fallback
- 🔢 **Spoken Number Support** — "thirty minutes" → 1800s, "an hour and a half" → 5400s
- 📇 **Contact Resolution** — "email Sarah" auto-resolves from contacts registry
- 💬 **Spoken Email Normalization** — "jane at example dot com" → jane@example.com

## Architecture

```
  Mic (Omi Pendant / Apple Watch)
        │ BLE
  Phone App (streams audio)
        │ Webhook
  Percept Receiver (FastAPI, port 8900)
   ├─ Webhook authentication (Bearer token / URL token)
   ├─ Speaker authorization gate (allowlist check)
   ├─ Wake word detection (from DB settings)
   ├─ Intent parser (regex + LLM, injection-resistant)
   ├─ Conversation segmentation (3s command / 60s summary)
   ├─ Entity extraction + relationship graph
   ├─ SQLite persistence (conversations, utterances, speakers, actions)
   ├─ LanceDB vector indexing (NVIDIA NIM embeddings)
   ├─ Security audit log (blocked attempts)
   └─ Action dispatch → OpenClaw / stdout / webhook
        │
  Dashboard (port 8960)
   ├─ Live transcript feed
   ├─ Conversation history + search
   ├─ Analytics (words/day, speakers, actions)
   ├─ Settings management (wake words, contacts, speakers)
   └─ Data export + purge
```

## Integrations

### OpenClaw Skill

Install the **percept-meetings** skill to give your OpenClaw agent meeting context:

```bash
clawhub install percept-meetings
```

Your agent can then search meetings, find action items, and follow up — from Zoom, Granola, and Omi sources. See [ClawHub](https://clawhub.ai) for details.

### Granola Meeting Notes

Import your [Granola](https://granola.ai) meeting notes into Percept's searchable knowledge base:

```bash
percept granola-sync
```

Reads from `~/Library/Application Support/Granola/cache-v3.json`, maps documents + transcripts into Percept's conversations table. Your Omi ambient audio and Granola structured notes become one unified, searchable knowledge base — all queryable through the MCP tools or CLI.

Supports `--since 2026-02-01`, `--dry-run`, and Enterprise API mode (`GRANOLA_API_KEY`).

### Zoom Cloud Recordings

Import Zoom meeting transcripts automatically:

```bash
# Sync last 7 days of recordings
percept zoom-sync --days 7

# Import a specific meeting or VTT file
percept zoom-import <meeting_id>
percept zoom-import /path/to/meeting.vtt --topic "Weekly Standup"
```

Requires a Zoom Server-to-Server OAuth app ([setup guide](docs/zoom-setup.md)). Also supports a webhook server for auto-import when recordings complete:

```bash
percept zoom-serve --port 8902
```

### ChatGPT Custom GPT

Expose Percept as a ChatGPT Actions API for any Custom GPT:

```bash
# Start the API server
percept chatgpt-api --port 8901

# Export OpenAPI schema for Custom GPT import
percept chatgpt-api --export-schema openapi.json
```

5 REST endpoints: `/api/search`, `/api/transcripts`, `/api/speakers`, `/api/entities`, `/api/status`. Bearer token auth via `PERCEPT_API_TOKEN`.

### Browser Audio Capture — Give Any AI Agent Ears for the Browser

**Any audio playing in a browser tab, captured and understood by your AI agent.** Meetings, podcasts, YouTube, webinars, earnings calls, online courses, customer support calls — if it plays in Chrome, your agent hears it.

No API keys. No OAuth. No per-platform integrations. One extension captures everything.

**Works with any AI agent framework** — Claude, ChatGPT, OpenClaw, LangChain, CrewAI, or your own. If your agent can make HTTP requests or run shell commands, it can receive browser audio.

```
Any Browser Tab Audio → Chrome Extension → PCM16 @ 16kHz → Your AI Pipeline
```

#### Use cases
- 🎙️ **Meetings** — Zoom, Meet, Teams auto-detected and captured
- 🎓 **Learning** — YouTube tutorials, Coursera, Udemy → searchable notes your agent can reference
- 🎧 **Podcasts & webinars** — Capture and summarize while you listen
- 📈 **Competitive intel** — Earnings calls, product demos, investor presentations → structured insights
- 💬 **Customer calls** — Browser-based support tools (Zendesk, Intercom) → auto-summarize, extract action items
- 📺 **Any audio content** — If it plays in a tab, your agent gets a transcript

#### Auto-detected meeting platforms
Google Meet • Zoom (web) • Microsoft Teams • Webex • Whereby • Around • Cal.com • Riverside • StreamYard • Ping • Daily.co • Jitsi • Discord — meetings are auto-flagged, but capture works on **any tab**.

#### Quick start

**Option 1: Chrome Extension (recommended — one click, persistent capture)**

1. `chrome://extensions/` → Developer mode → Load unpacked → select `src/browser_capture/extension/`
2. Join any meeting in Chrome
3. Click the Percept icon → **Start Capturing This Tab**
4. Audio streams to `http://localhost:8900/audio/browser` as base64 PCM16 JSON
5. Close the popup — capture continues in the background

**Option 2: CLI via Chrome DevTools Protocol**

```bash
pip install aiohttp

# List open tabs (meeting tabs flagged with 🎙️)
percept capture-browser tabs

# Auto-detect and capture meeting tabs
percept capture-browser capture

# Continuous watch mode — auto-starts when you join a meeting
percept capture-browser watch --interval 15

# Check what's capturing / stop
percept capture-browser status
percept capture-browser stop
```

Requires Chrome running with `--remote-debugging-port=9222`.

#### Standalone skill (for any OpenClaw agent)

```bash
clawhub install browser-audio-capture
```

This installs the Chrome extension + CLI as a skill that any OpenClaw agent can use — regardless of model (Claude, GPT, Gemini, Llama, etc.).

#### Audio output format

Audio POSTs to your endpoint as JSON:

```json
{
  "sessionId": "browser_1709234567890",
  "audio": "<base64 PCM16>",
  "sampleRate": 16000,
  "format": "pcm16",
  "source": "browser_extension",
  "tabUrl": "https://meet.google.com/abc-defg-hij",
  "tabTitle": "Weekly Standup"
}
```

Point it at any transcription service — Whisper, Deepgram, AssemblyAI, NVIDIA Riva — or pipe it straight into your agent's context. The endpoint is configurable in `offscreen.js` (`PERCEPT_URL`).

## Supported Hardware

| Device | Status | Notes |
|--------|--------|-------|
| **Omi Pendant** | ✅ Live | Primary device. BLE to phone, all-day battery. "Critical to our story" |
| **Apple Watch** | 🔜 Beta | WatchOS app built (push-to-talk, raise-to-speak). Needs real device testing |
| **Browser (CDP)** | ✅ Live | Chrome extension captures audio from any browser tab — meetings, YouTube, podcasts, courses, anything |
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
percept speakers list          # Show authorized + known speakers
percept speakers authorize SPEAKER_0  # Authorize a speaker
percept speakers revoke SPEAKER_0     # Revoke a speaker
percept config set webhook_secret <token>  # Set webhook auth token
percept security-log           # View blocked attempts

# Meeting source connectors
percept granola-sync           # Import from Granola (local cache)
percept granola-sync --api     # Import via Granola Enterprise API
percept zoom-sync --days 7     # Sync recent Zoom recordings
percept zoom-import <id>       # Import specific Zoom meeting
percept zoom-import file.vtt   # Import local VTT transcript
percept chatgpt-api            # Start ChatGPT Actions API (port 8901)

# Browser audio capture
percept capture-browser tabs     # List tabs (flags meetings)
percept capture-browser capture  # Start capturing (auto-detects meetings)
percept capture-browser watch    # Auto-detect mode (continuous)
percept capture-browser status   # Show active captures
percept capture-browser stop     # Stop all captures
```

> See [CLI Reference](docs/cli-reference.md) for full details.

## MCP Server (Claude Desktop / Anthropic Ecosystem)

Percept exposes all capabilities as MCP (Model Context Protocol) tools, so Claude can natively search your conversations, check transcripts, and more.

```bash
# Start MCP server (stdio transport)
percept mcp
```

### Claude Desktop Configuration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "percept": {
      "command": "/path/to/percept/.venv/bin/python",
      "args": ["/path/to/percept/run_mcp.py"]
    }
  }
}
```

> Restart Claude Desktop after editing. The Percept tools will appear automatically.

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `percept_search` | Full-text search across conversations |
| `percept_transcripts` | List recent transcripts |
| `percept_actions` | Voice command history |
| `percept_speakers` | Known speakers with word counts |
| `percept_status` | Pipeline health check |
| `percept_security_log` | Blocked attempts log |
| `percept_conversations` | Conversations with summaries |
| `percept_listen` | Live transcript stream |

### MCP Resources

- `percept://status` — Current pipeline status
- `percept://speakers` — Known speakers list

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
| `authorized_speakers` | Speaker allowlist for command authorization | Security |
| `security_log` | Blocked attempts (unauthorized, invalid auth, injection) | Security |
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
2. 🧪 **Try it** — install, use it for a day, [file issues](https://github.com/GetPercept/percept/issues)
3. 🔧 **Build** — language packs, hardware integrations, new action types
4. 📣 **Share** — blog about it, tweet about it

See [Contributing Guide](docs/contributing.md) for dev setup and PR guidelines.

## License

[MIT](LICENSE) — do whatever you want with it.

---

<p align="center">
  <em>"Fei-Fei Li gave AI eyes with ImageNet. We're giving AI agents ears."</em>
</p>
<!-- mcp-name: io.github.getpercept/percept -->
