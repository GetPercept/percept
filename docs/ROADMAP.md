# Percept Roadmap

Last updated: 2026-02-21

---

## Phase 1: Foundation ✅ DONE

**SQLite persistence + basic pipeline (Feb 16-21)**

- [x] FastAPI receiver with Omi webhook integration
- [x] faster-whisper transcription (base model, int8, M-series optimized)
- [x] Wake word detection ("Hey Jarvis", configurable from DB)
- [x] Intent parser (regex + LLM fallback, 7 action types)
- [x] Spoken number parsing ("thirty minutes" → 1800s)
- [x] Action dispatcher → OpenClaw CLI
- [x] Speaker identification + contacts registry
- [x] Conversation tracking (3s command / 60s summary)
- [x] Auto-summaries with calendar context matching
- [x] SQLite persistence (11 tables, WAL, FTS5, foreign keys)
- [x] Settings management from DB
- [x] Entity extraction (two-pass: regex + LLM)
- [x] Entity resolution (5-tier cascade)
- [x] Relationship graph (weighted edges, decay)
- [x] Context Packet Assembly
- [x] Dashboard (port 8960) with settings, analytics, search
- [x] Landing page (port 8950, getpercept.ai)
- [x] Percept Protocol spec (6 event types, JSON Schema)
- [x] CLI tool (9 commands)
- [x] Cloudflare tunnel (percept.clawdoor.com)
- [x] LaunchAgent for background operation
- [x] Watch app prototype (mock mode for simulator)
- [x] NVIDIA Parakeet ASR tested via gRPC

## Phase 2: Semantic Search 🔄 IN PROGRESS

**NVIDIA NeMo Retriever embeddings + vector search**

- [x] LanceDB vector store integration
- [x] NVIDIA NIM embedding API (`nv-embedqa-e5-v5`)
- [x] Conversation chunk indexing (500 char, 50 overlap)
- [x] Batch embedding (20/request, rate limited)
- [x] Semantic search CLI command
- [x] Dashboard search with vector fallback
- [x] Intent parser uses semantic context for ambiguous references
- [x] Bulk indexing script (`scripts/index_vectors.py`)
- [ ] Offline embedding fallback (all-MiniLM-L6-v2)
- [ ] Auto-indexing reliability (handle API failures gracefully)
- [ ] Embedding quality evaluation on real conversations

## Phase 3: Safety & Guardrails 📋 PLANNED

**NVIDIA NeMo Guardrails**

- [ ] Content filtering on transcripts (PII detection)
- [ ] Action confirmation guardrails (high-stakes actions require confirmation)
- [ ] Sensitive topic detection and handling
- [ ] Rate limiting on agent actions
- [ ] Audit trail for all actions taken

## Phase 4: Speaker Intelligence 🔮 FUTURE

**Speaker Diarization NIM + pyannote voiceprints**

- [ ] pyannote speaker diarization integration
- [ ] 192-dim voice embeddings (voiceprints)
- [ ] Cosine similarity speaker matching
- [ ] Running average voiceprint updates
- [ ] NVIDIA Speaker Diarization NIM (when available)
- [ ] Automatic "who's talking" without manual "that was Sarah"

---

## Tracks

### Watch App
- [x] Architecture designed (push-to-talk, raise-to-speak, complication)
- [x] Project scaffolding with xcodegen
- [x] Mock mode for simulator testing
- [ ] **Real device testing** — needs physical Apple Watch
- [ ] Audio pipeline validation on device
- [ ] WatchConnectivity reliability testing
- [ ] App Store TestFlight distribution

### Landing Page
- [x] Built and served on port 8950
- [x] Domain: getpercept.ai
- [ ] Waitlist form integration
- [ ] SEO optimization
- [ ] Blog/content section

### Open Source Launch
- [x] Private GitHub repo (davidemanuelDEV/percept)
- [x] MIT license
- [x] Comprehensive documentation (9 doc files + README + CHANGELOG)
- [x] Protocol specification with JSON Schemas
- [ ] **Make repo public** (after demo is undeniable)
- [ ] PyPI package (`pip install getpercept`)
- [ ] GitHub Actions CI
- [ ] Test suite
- [ ] HN launch post
- [ ] Reddit launch (r/machinelearning, r/selfhosted, r/openai)
- [ ] Product Hunt launch
- [ ] OpenClaw Discord announcement

### ClawHub Skill Pack
5 skills planned for OpenClaw marketplace:
- [ ] `percept-listen` — Core audio pipeline
- [ ] `percept-summarize` — Auto conversation summaries
- [ ] `percept-voice-cmd` — Voice command parsing + dispatch
- [ ] `percept-speaker-id` — Speaker identification + tracking
- [ ] `percept-ambient` — Ambient conversation logging + search

### NVIDIA Integration
- [x] Parakeet ASR tested (gRPC)
- [x] NIM API key obtained (expires Aug 2026)
- [x] NeMo Retriever embeddings (nv-embedqa-e5-v5) integrated
- [ ] NVIDIA Inception application (pending)
- [ ] NeMo Guardrails integration
- [ ] Speaker Diarization NIM (when released)

---

## Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| End-to-end pipeline live | Feb 20 | ✅ Done |
| SQLite persistence | Feb 21 | ✅ Done |
| CIL spec written | Feb 21 | ✅ Done |
| Vector search working | Feb 21 | ✅ Done |
| Demo video filmed | TBD | ⬜ |
| Repo goes public | TBD | ⬜ |
| 1K GitHub stars | Month 1 post-launch | ⬜ |
| First external contributor | Month 1 post-launch | ⬜ |
| Hosted API beta | Month 3 post-launch | ⬜ |
| $25K MRR | Month 6 post-launch | ⬜ |
