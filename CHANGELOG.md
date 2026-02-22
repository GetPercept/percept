# Changelog

All notable changes to Percept are documented here, in reverse chronological order.

---

## [0.3.0] — 2026-02-21 — Context Intelligence Layer

### Added
- **SQLite persistence** — Full database layer (`src/database.py`) with 11 tables: conversations, utterances, speakers, contacts, actions, projects, entity_mentions, relationships, settings. WAL mode, foreign keys, FTS5 full-text search on utterances with porter stemming
- **Settings from DB** — Wake words, silence timeouts, conversation end timeout, transcriber config, TTL settings, ports — all managed via `settings` table with defaults. Wake words reload from DB every 60s
- **Entity extractor** (`src/entity_extractor.py`) — Two-pass pipeline: fast regex (emails, phones, URLs, dates, names, orgs) + optional LLM semantic extraction. Extracts person, org, project, product, location, event entities
- **Entity resolution** — 5-tier cascade: exact match (contacts/speakers) → fuzzy match (SequenceMatcher ≥0.85) → contextual match (relationship graph traversal) → recency match (pronoun resolution) → semantic search (vector store fallback). Confidence thresholds: ≥0.8 auto, 0.5-0.8 soft, <0.5 needs_human
- **Relationship graph** — `relationships` table with weighted edges (source, target, type, evidence). Auto-builds from co-occurring entities: person↔person (mentioned_with), person↔org (works_on), person↔project (works_on). Linear decay for stale relationships
- **Context engine** (`src/context_engine.py`) — Context Packet Assembly: combines conversation data, resolved entities, relationship graph, and recent context into a single JSON packet for agent action resolution
- **Utterances table** — Atomic speech units with speaker, timestamps, confidence, is_command flag. FTS5 triggers for automatic index sync on insert/update/delete
- **Vector store** (`src/vector_store.py`) — NVIDIA NIM embeddings (`nvidia/nv-embedqa-e5-v5`) + LanceDB. Overlapping chunk indexing (500 chars, 50 overlap), batch embedding (20/request), asymmetric passage/query types. Summaries indexed separately as high-signal vectors
- **Dashboard settings page** — Full CRUD API for settings, speakers, contacts. Export all data as JSON. Purge by TTL or manually
- **Dashboard search** — FTS5 keyword search with LanceDB vector search fallback (`/api/search`)
- **Dashboard entities/relationships** — Browse extracted entities and relationship graph
- **CLI: `percept search`** — Semantic search over all indexed conversations with date filtering
- **CLI: `percept audit`** — Data statistics across all tables + storage size
- **CLI: `percept purge`** — Delete by age, conversation ID, TTL expiry, or all (with --confirm)
- **Backfill scripts** — `scripts/backfill_db.py` (migrate file-based conversations to SQLite), `scripts/backfill_utterances.py` (populate utterances from conversations), `scripts/index_vectors.py` (bulk vector indexing)
- **TTL auto-purge** — Configurable retention periods: utterances 30d, summaries 90d, relationships 180d. `ttl_expires` column on conversations
- **Relationship decay** — Stale relationships (>7 days) decay linearly, zero-weight edges auto-deleted

### Changed
- Wake words now loaded from database instead of hardcoded list
- Receiver saves conversations and utterances to SQLite alongside markdown files
- Receiver indexes new conversations in vector store automatically
- Intent parser saves parsed intents to database
- Action dispatch records action status (pending → executed/failed) in database
- Speaker word/segment counts tracked in database per flush
- Entity extraction runs on every conversation end (auto-summary trigger)

---

## [0.2.0] — 2026-02-20 — Full Pipeline Live

### Added
- **Omi webhook integration** — `/webhook/transcript` endpoint receives real-time segments from Omi pendant via Cloudflare tunnel (`percept.clawdoor.com`)
- **Intent parser** (`src/intent_parser.py`) — Two-tier hybrid: expanded regex patterns (7 action types with multiple trigger phrases each) + LLM fallback via OpenClaw. Cache layer (5min TTL) for LLM results
- **Spoken number parsing** — Converts spoken numbers to integers: "thirty" → 30, "forty five" → 45, compound "twenty five" → 25. Duration parsing: "thirty minutes" → 1800s, "an hour and a half" → 5400s
- **Action dispatcher** — 7 action types: email, text, reminder, search, calendar, note, order. Contact resolution, spoken email normalization ("david at vectorcare dot com" → david@vectorcare.com)
- **Wake word detection** — Checks flushed transcript for configurable wake words. Extracts command text after wake word
- **Conversation tracking** — Two-tier accumulation: short-term buffer (3s silence → command flush) + long-term buffer (60s silence → auto-summary)
- **Auto-summaries** — After 60s silence, sends full transcript to OpenClaw for AI-powered summary. Includes calendar context matching via `gog cal list`. Delivered via iMessage
- **On-demand summaries** — "Hey Jarvis, summarize this conversation" triggers immediate summary without ending conversation
- **Speaker identification** — "Hey Jarvis, that was Sarah" maps last non-owner speaker ID to name. Speaker registry in `data/speakers.json`
- **Day summary** — "Hey Jarvis, day summary" aggregates today's conversations, words, speakers, key topics
- **Task extraction** — `/tasks` endpoint and "Hey Jarvis, any tasks" voice command. Regex-based detection of action verbs + intent phrases in recent transcripts
- **Ambient question detection** — Detects factual questions in ambient speech (DISABLED — too noisy with regex approach, TODO: re-enable with AI filtering)
- **Contact resolution** — `data/contacts.json` with name/alias → email/phone lookup
- **Live transcript file** — Rolling `/tmp/percept-live.txt` with timestamped speaker-labeled text
- **Conversation markdown files** — Saved to `data/conversations/` with metadata headers
- **Dashboard** (`dashboard/server.py`) — Full web UI on port 8960: live feed, conversations, speakers, contacts, analytics, actions
- **Dashboard analytics** — Words by period (today/week/month/all), segments per hour, speaker word counts, action history
- **Landing page** — `landing/index.html` served on port 8950 for getpercept.ai
- **Protocol specification** — `protocol/PROTOCOL.md` with 6 event types (transcript, conversation, intent, action_request, action_response, summary). JSON Schema files for each
- **CLI tool** (`src/cli.py`) — 9 commands: serve, listen, status, transcripts, actions, search, config, audit, purge. Color output, composable JSON piping
- **Direct iMessage fallback** — `_send_imessage()` for direct delivery when OpenClaw is unavailable
- **LaunchAgent** — `com.percept.receiver` for persistent background operation

### Infrastructure
- **Cloudflare tunnel** — `percept.clawdoor.com` routed through clawdoor-api tunnel
- **Domain** — getpercept.ai purchased and configured
- **GitHub** — Private repo at `davidemanuelDEV/percept`

---

## [0.1.0] — 2026-02-16 — Audio Pipeline Foundation

### Added
- **Receiver** (`src/receiver.py`) — FastAPI server on port 8900 accepting PCM16 audio via `/webhook/audio`
- **Transcriber** (`src/transcriber.py`) — faster-whisper wrapper with base model, int8 compute, VAD filtering. Conversation tracking with silence-based segmentation
- **Context extraction** (`src/context.py`) — Keyword-based extraction of action items, people, and topics. Markdown conversation file writer
- **Config** — `config/config.json` with server, whisper, and audio settings
- **Watch app prototype** — Apple Watch app structure with push-to-talk, raise-to-speak, complication. Mock mode for simulator. Shared audio config, WatchConnectivity relay, companion iPhone app
- **NVIDIA Parakeet ASR** — Tested successfully via gRPC. NIM API key obtained. Three-tier transcriber strategy defined: local → NVIDIA → cloud
- **Project scaffolding** — Requirements, .gitignore, run.sh, research notes directory

---

## Pre-history

- **2026-02-16:** David orders Omi pendant ($89). Architecture designed. Business model decided (Open Source Core + Hosted API). "NOT a VectorCare product" — David explicit
- **2026-02-17:** getpercept.ai domain purchased. NVIDIA Inception application submitted. GTM playbook drafted
- **2026-02-20:** Pipeline goes live end-to-end. David demos to team: "That's really fucking amazing"
- **2026-02-21:** CIL Technical Spec v1.0 written by David. SQLite persistence implemented. Vector store built. Full documentation update for Peter (OpenClaw) review
