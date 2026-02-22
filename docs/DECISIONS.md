# Architecture Decision Records

Percept's key technical and strategic decisions, with rationale. Prevents re-litigating settled choices.

---

## ADR-001: Project Scope (2026-02-16)
**Decision:** Build as standalone project with own repo, separate from main workspace.
**Rationale:** Retain clean IP ownership, dedicated documentation, private GitHub repo. Eventually may become OpenClaw skill/integration but keeping isolated during dogfooding phase.

## ADR-002: Audio-First Approach (2026-02-16)
**Decision:** Start with Omi pendant (audio only), defer vision (Omi Glass) to Phase 2.
**Rationale:** Audio captures 80% of the value (meetings, conversations, context). $89 vs $299 hardware. Simpler pipeline. Prove the concept before adding complexity.

## ADR-003: Local Whisper Over Cloud API (2026-02-16)
**Decision:** Use local faster-whisper rather than OpenAI Whisper API as the default transcriber.
**Alternatives:** OpenAI Whisper API, Deepgram, Google Speech-to-Text
**Rationale:** Privacy is THE selling point. Audio never leaves the Mac. Also cheaper at scale — API costs ~$0.006/min, local is free after setup. M-series Apple Silicon gives excellent real-time performance with int8 quantization.
**Trade-offs:** Slightly lower accuracy than cloud models, requires local compute resources.

## ADR-004: Three-Tier Transcriber Strategy (2026-02-16)
**Decision:** Local (faster-whisper) → NVIDIA (Parakeet NIM) → Cloud (Deepgram) fallback chain.
**Rationale:** Local-first for privacy and zero cost. NVIDIA for superior accuracy when API key available (tested successfully via gRPC). Cloud as final fallback for users without GPU or NVIDIA access. Each tier is a clean class swap.

## ADR-005: Omi Pendant as Primary Hardware (2026-02-16)
**Decision:** Omi pendant is THE primary form factor. Not laptop mic, not AirPods.
**Quote:** David: "Critical to our story."
**Rationale:** Purpose-built wearable with all-day battery, BLE to phone, open-source firmware. Creates a tangible product story. Differentiates from "just another transcription app."

## ADR-006: Watch App as Second Form Factor (2026-02-21)
**Decision:** Include Apple Watch app at launch, but Omi pendant remains primary.
**Rationale:** Watch provides push-to-talk and raise-to-speak interaction models. Proves Percept works across hardware. But Omi is the story — prove it there first, Watch is bonus.
**Trade-offs:** Additional engineering surface, WatchOS audio constraints, needs real device testing.

## ADR-007: GTM = OpenClaw Ecosystem, Not VectorCare (2026-02-16)
**Decision:** Percept is an OpenClaw play, NOT a VectorCare product.
**Quote:** David: "Lets not use VectorCare as our GTM."
**Rationale:** VectorCare is a separate business with its own brand. OpenClaw already has node pairing, camera tools, agent framework. Wearable audio is a natural extension. Community = built-in GTM.

## ADR-008: Stealth Mode Until Demo Is Undeniable (2026-02-17)
**Decision:** Private development, no public launch until the demo speaks for itself.
**Quote:** David: "Keep it under the radar until we have it all going."
**Rationale:** Prove it works first with daily dogfooding, then show receipts. Film undeniable demo. Then blitz HN + Reddit + PH + OpenClaw Discord simultaneously.
**Trade-offs:** Slower community building, risk of competitor launching first (Limitless already acquired by Meta).

## ADR-009: SQLite Over Postgres (2026-02-21)
**Decision:** SQLite as the sole persistence layer for all structured data.
**Alternatives:** PostgreSQL, MongoDB, Redis, file-based JSON
**Rationale:** Local-first philosophy — zero deps, single file, no server process. WAL mode handles concurrent reads. FTS5 gives full-text search for free. Perfect for single-user ambient device. Postgres adds deployment complexity that contradicts the "pip install and go" story.
**Trade-offs:** No multi-user/multi-device sync (future problem), no PostGIS, 1 writer at a time.

## ADR-010: LanceDB Over ChromaDB for Vectors (2026-02-21)
**Decision:** LanceDB for semantic vector storage.
**Alternatives:** ChromaDB, Pinecone, Weaviate, Qdrant, pgvector
**Rationale:** Rust core (fast), truly serverless (no process to manage), disk-efficient, zero-copy versioning, supports multimodal embeddings. ChromaDB requires a running server. Pinecone/Weaviate are cloud-only or heavy. LanceDB fits the local-first, zero-dependency philosophy perfectly.

## ADR-011: Wake Word Only, No Ambient Question Detection (2026-02-20)
**Decision:** Only respond to explicit wake word ("Hey Jarvis"), not ambient questions.
**Alternatives:** Detect all questions in ambient speech and proactively answer
**Rationale:** Ambient question detection was built and tested — too noisy. Regex-based question detection triggers on rhetorical questions, conversational "you know what I mean?", etc. Creates annoying interruptions. Wake word is a clear intent signal.
**Future:** Re-enable with AI-based filtering that can distinguish factual from rhetorical questions.

## ADR-012: 3-Second Silence Timeout for Commands (2026-02-20)
**Decision:** 3 seconds of silence before flushing transcript to the agent for command processing.
**Alternatives:** 1 second (too aggressive), 5 seconds (too slow), 10 seconds
**Quote:** David said 10s "is an issue" — too long to wait for a response.
**Rationale:** 3s is the sweet spot — long enough to handle natural pauses in speech, short enough for responsive command execution. People naturally pause 1-2s between sentences; 3s means the speaker is done.

## ADR-013: 60-Second Conversation End Timeout (2026-02-20)
**Decision:** 60 seconds of silence triggers auto-summary and marks conversation as ended.
**Alternatives:** 30 seconds (too aggressive in meetings), 120 seconds (wastes time), 300 seconds
**Rationale:** 60s means someone walked away or the meeting paused significantly. Long enough to survive bathroom breaks in meetings, short enough to get timely summaries.

## ADR-014: Open Source Core + Hosted API Business Model (2026-02-16)
**Decision:** Core pipeline is MIT open source. Revenue from hosted API (future).
**Alternatives:** Fully proprietary, freemium SaaS, pure open source with support
**Rationale:** Open source builds trust (privacy-sensitive market), creates community moat, drives adoption. Hosted API for users who don't want to self-host. No pricing cards yet — free self-host + waitlist for hosted version.
**Comparables:** LangChain (100K stars, $10B), n8n (60K stars, $50M), Home Assistant (80K stars)

## ADR-015: Percept Protocol as Framework-Agnostic Standard (2026-02-20)
**Decision:** Define a JSON protocol specification, not just build a product.
**Rationale:** Voice pipelines and agent runtimes are separate concerns. A transcription system shouldn't need to know how actions get executed. The protocol is the contract between them. Unix composable (JSON Lines on stdout), runtime agnostic, incrementally adoptable.

## ADR-016: Anthropic as Natural Acquirer (2026-02-20)
**Decision:** Position Percept for potential acquisition, with Anthropic as the natural fit.
**Rationale:** Anthropic is the only frontier model company without a voice/ambient strategy. OpenAI has GPT-4o voice, Google has Gemini Live, Apple has Siri. Anthropic has... nothing for ambient. Percept fills that gap perfectly.
**Exit range:** $5-50M depending on traction. Limitless→Meta validates market at $200-400M.

## ADR-017: No Pricing Cards Yet (2026-02-20)
**Decision:** Free self-host + waitlist. No pricing page or tier cards.
**Rationale:** Too early to price. Need to prove the product works in daily use first. Waitlist creates scarcity and collects leads. Pricing can be added when hosted API launches.

## ADR-018: NVIDIA Inception for Hardware/Credits (2026-02-17)
**Decision:** Apply to NVIDIA Inception startup program.
**Rationale:** Free GPU credits, preferred NIM API pricing, investor network access. Percept already uses NVIDIA Parakeet ASR (tested) and NIM embeddings (built). Application submitted.

## ADR-019: Context Intelligence Layer (CIL) as the Moat (2026-02-21)
**Decision:** The CIL — not transcription — is Percept's core differentiator.
**Rationale:** Transcription is a commodity (Whisper, Deepgram, etc. all work). The moat is what happens AFTER transcription: entity extraction, relationship graphs, contextual resolution, semantic search, context packets for agents. This is what makes "email the client" actually work — knowing who "the client" is from conversation history.
**CIL spec:** `shared-jarvis/Percept_Context_Intelligence_Layer_Spec.docx`

## ADR-020: NVIDIA NIM Embeddings Primary, MiniLM Fallback (2026-02-21)
**Decision:** NVIDIA `nv-embedqa-e5-v5` as primary embedding model, `all-MiniLM-L6-v2` as offline fallback.
**Rationale:** NVIDIA model has superior quality and asymmetric passage/query embedding support. Free tier generous with Inception. MiniLM runs locally with no API key for users without NVIDIA access. Graceful degradation — if NVIDIA is down, indexing skips silently.

## ADR-021: Utterances as Atomic Unit (2026-02-21)
**Decision:** Individual speech segments (utterances), not whole conversations, are the atomic data unit.
**Rationale:** Per the CIL spec: utterances have speaker, timestamps, confidence. They're the granular unit for FTS5 search, entity extraction, speaker analytics. Conversations are aggregates. This enables "search for what Sarah said about the budget" vs just "search conversations about the budget."
