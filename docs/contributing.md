# Contributing

## Dev Environment Setup

```bash
git clone https://github.com/davidemanuelDEV/percept.git
cd percept

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python -m src.cli serve
```

## Code Structure

```
src/
├── receiver.py        # FastAPI server — webhooks, wake word, action dispatch, summaries
├── transcriber.py     # faster-whisper wrapper, Segment/Conversation models
├── intent_parser.py   # Two-tier intent parser (regex + LLM fallback)
├── database.py        # SQLite persistence (11 tables, FTS5, WAL mode)
├── context_engine.py  # CIL: Context Packet Assembly, entity resolution
├── entity_extractor.py # CIL: Two-pass entity extraction + relationship building
├── vector_store.py    # NVIDIA NIM embeddings + LanceDB semantic search
├── context.py         # Context extraction, conversation file writer
└── cli.py             # CLI commands (9 total)

dashboard/
├── server.py          # Dashboard FastAPI backend (port 8960, 20+ endpoints)
└── index.html         # Dashboard web UI

scripts/
├── backfill_db.py     # Migrate file-based conversations to SQLite
├── backfill_utterances.py  # Populate utterances from conversations
└── index_vectors.py   # Bulk vector indexing
```

### Key files

- **`receiver.py`** is the heart — webhooks, wake word detection, action dispatch, summaries, entity extraction
- **`database.py`** is the persistence layer — 11 tables, settings management, FTS5 search, TTL purge
- **`intent_parser.py`** handles voice command parsing — regex tier + LLM fallback, spoken number support
- **`entity_extractor.py`** does two-pass entity extraction and 5-tier resolution
- **`vector_store.py`** wraps NVIDIA NIM embeddings + LanceDB for semantic search
- **`context_engine.py`** assembles context packets for agent action resolution
- **`cli.py`** is the user-facing entry point with 9 commands

## Running Tests

```bash
# TODO: Test suite coming soon
python -m pytest tests/
```

> **Note:** We need tests! This is a great first contribution. See [Good First Issues](#good-first-issues) below.

## PR Guidelines

1. **Fork** the repo and create a feature branch
2. **Keep PRs small** — one feature or fix per PR
3. **Add/update docs** if you change behavior
4. **Test manually** — run `percept serve` and verify with a sample webhook
5. **Describe what and why** in the PR description

## Code Style

- Python 3.10+ (type hints encouraged)
- Imports: stdlib → third-party → local
- Logging via `logging.getLogger(__name__)`
- Print statements with `flush=True` for real-time log output
- f-strings preferred over `.format()`

## Good First Issues

| Issue | Difficulty | Area |
|-------|-----------|------|
| Add unit tests for `IntentParser._try_regex()` | 🟢 Easy | Testing |
| Add unit tests for `EntityExtractor.extract_fast()` | 🟢 Easy | Testing |
| Add unit tests for `parse_spoken_duration()` | 🟢 Easy | Testing |
| Make `SILENCE_TIMEOUT` configurable from DB settings | 🟢 Easy | Config |
| Make `CONVERSATION_END_TIMEOUT` configurable from DB settings | 🟢 Easy | Config |
| Add `--verbose` flag to CLI commands | 🟢 Easy | CLI |
| Offline embedding fallback (all-MiniLM-L6-v2) | 🟡 Medium | Vectors |
| Add Deepgram transcriber option | 🟡 Medium | Transcription |
| Add pyannote speaker diarization | 🟡 Medium | Audio |
| Add webhook authentication (API key/bearer token) | 🟡 Medium | Security |
| Add WebSocket event streaming | 🔴 Hard | Protocol |
| PII detection in transcripts | 🔴 Hard | Privacy |

## Architecture Docs

Before diving in, read [Architecture](architecture.md) to understand the pipeline and data flow.

---

Thank you for contributing! ⭐
