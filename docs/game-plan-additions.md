# Percept Game Plan v3 — Additions

## INSERT AFTER SECTION 2 (The Problem), BEFORE SECTION 3 (The Solution)

---

# 2.5. Why Now

Three years ago, this product was impossible. Three years from now, every major platform will have built it. February 2026 is the narrow window where all the prerequisites exist and none of the incumbents have assembled them.

### The hardware unlocked

Consumer wearable mics crossed the quality-price threshold in late 2025. The Omi pendant ($69, open-source, BLE streaming, 16kHz PCM) gives developers raw audio access that AirPods, Pixel Buds, and Galaxy Buds explicitly deny. Brilliant Labs' Frame ($349, open-source glasses with Python SDK) ships in Q1 2026. For the first time, developers can build ambient audio pipelines on hardware that people actually wear — without jailbreaking anything.

### The agent ecosystem exploded

OpenClaw hit 175K GitHub stars in its first two weeks (January 2026). Anthropic's MCP protocol became the de facto standard for LLM tool integration, with 500+ community servers. OpenAI shipped custom Actions for ChatGPT. Every foundation model company is racing to add agent capabilities — but every agent they build is deaf. The ecosystem is massive, hungry for input modalities, and has no standard way to receive ambient audio.

### The acquisition wave validated the category

Meta acquired Limitless for ~$200–400M in December 2025 (50-person team, 50K pendant devices). PlayAI was acquired for its voice synthesis stack. ElevenLabs reached $6.6B valuation on voice AI alone. The market has decided that voice is a critical AI infrastructure layer — but every acquisition so far has been a closed, single-platform play. Nobody owns the open, multi-platform layer.

### Local compute caught up

Apple Silicon M-series chips run faster-whisper (Whisper medium) at 10x real-time. NVIDIA's Parakeet ASR hits 98% accuracy with sub-second latency on consumer GPUs. Two years ago, real-time local transcription required cloud APIs and round-trip latency. Today, the entire pipeline — capture, transcribe, extract, act — runs on a laptop with no network dependency. This makes "audio never leaves your hardware" a real promise, not marketing.

### The regulatory window

The EU AI Act (effective August 2025) and proposed US AI transparency rules are creating compliance pressure around cloud-processed audio. Enterprises are actively seeking local-first alternatives for meeting intelligence. A product that processes audio on-premise and sends only structured context packets to agents — never raw audio — is positioned on the right side of every regulation being drafted.

### Why not earlier, why not later

**Not earlier:** Wearable mics were either closed (Apple) or terrible (pre-Omi open hardware). Agent ecosystems didn't exist — MCP launched late 2024, OpenClaw launched January 2026. Local ASR wasn't fast enough for real-time.

**Not later:** Once Anthropic, OpenAI, or Apple ships native ambient listening (likely 12–18 months), the window for an independent open standard closes. The play is to become the standard *before* the platforms build their own — so they adopt or acquire rather than compete. Percept Protocol published now, adopted by 5–10 projects by month 6, becomes the path of least resistance for any platform that wants voice input without building from scratch.

---

## INSERT INTO SECTION 8 (Business Model), AFTER pricing table

---

# Self-Host vs. Hosted: The Conversion Logic

The core tension in any open-source business: why pay when the code is free? Percept resolves this by making self-host excellent for individuals and making hosted essential for teams and scale.

### What's always free (MIT, self-host)

| Capability | Details |
|---|---|
| Full pipeline | Omi → transcription → CIL → agent output |
| All meeting connectors | Zoom, Granola, Omi, webhook API |
| All output adapters | CLI, MCP, ChatGPT Actions, OpenClaw skill |
| Local transcription | faster-whisper (base/small/medium models) |
| Entity extraction & relationship graphs | Full CIL on SQLite + FTS5 |
| Speaker identification | Local voiceprint matching |
| Semantic search | LanceDB + local or NVIDIA NIM embeddings |
| Dashboard | Local web UI (port 8960) |
| Unlimited conversations | No caps, no telemetry, no phone-home |

Self-host Percept is genuinely full-featured. This is intentional — it builds trust, drives adoption, and creates the community that makes the project valuable.

### What's hosted-only

| Feature | Why it can't be self-hosted | Tier |
|---|---|---|
| **Zero-config meeting webhooks** | Self-host requires Cloudflare Tunnel or ngrok setup + DNS. Hosted = paste your Zoom/Omi credentials, done in 60 seconds. | Pro ($49/mo) |
| **Cross-device context sync** | Local-first means your CIL lives on one machine. Hosted syncs your context graph across laptop, phone, and watch — E2E encrypted. | Pro ($49/mo) |
| **Cloud ASR (Deepgram / Parakeet cloud)** | Self-host uses faster-whisper (good, ~95% accuracy). Hosted offers Deepgram Nova-2 or NVIDIA Parakeet (~98% accuracy) with zero GPU requirement. | Pro ($49/mo) |
| **Team shared context** | The killer feature. Multiple team members' meetings in one searchable CIL. Cross-reference who said what across all your team's conversations. Relationship graphs span the whole org. | Team ($99/user/mo) |
| **Persistent web dashboard** | Self-host dashboard requires your machine running. Hosted gives a persistent URL with historical trends, entity timelines, and meeting analytics. | Pro ($49/mo) |
| **Meeting briefing packets** | Before your next call, Percept generates a packet: last 3 conversations with these attendees, open action items, relationship context, entity history. Auto-delivered to your agent or email. | Team ($99/user/mo) |
| **Calendar-aware recording** | Auto-starts recording for scheduled meetings, auto-tags by calendar event, auto-routes summaries to the right channel. | Team ($99/user/mo) |
| **SSO + audit logs** | SAML/OIDC, admin console, per-user permissions, compliance audit trail. | Enterprise ($299/user/mo) |
| **Custom ASR models** | Fine-tuned Whisper on your domain vocabulary (medical, legal, finance). 30%+ accuracy improvement on jargon. | Enterprise ($299/user/mo) |
| **Dedicated infrastructure** | Single-tenant deployment, your cloud or ours, SLA, dedicated support. | Enterprise ($299/user/mo) |

### The conversion triggers

Users don't upgrade because they hit a paywall. They upgrade because their needs change:

1. **Individual → Pro:** "I got a second machine and want my context on both." Or: "I don't want to maintain a Cloudflare Tunnel for my Zoom webhook."

2. **Pro → Team:** "My cofounder started using Percept too and we want shared context across our meetings." This is the natural viral loop — one person on the team starts using it, the value multiplies with each additional user.

3. **Team → Enterprise:** "Legal wants audit logs before we roll this out to the full engineering org." Standard enterprise procurement trigger.

### Unit economics

| | Self-Host | Hosted Pro | Hosted Team |
|---|---|---|---|
| ASR cost | $0 (local) | ~$0.006/min (Deepgram) | ~$0.006/min |
| Storage | $0 (local) | ~$0.02/user/mo (S3) | ~$0.02/user/mo |
| Compute | $0 (local) | ~$2/user/mo (CIL processing) | ~$3/user/mo |
| **Total COGS** | **$0** | **~$5/user/mo** | **~$6/user/mo** |
| **Price** | **$0** | **$49/mo** | **$99/user/mo** |
| **Gross margin** | — | **~90%** | **~94%** |

At 2% free→paid conversion (industry standard for open-source-to-hosted):
- 5,000 active self-host users → 100 paid → ~$6K MRR (conservative)
- 10,000 active self-host users → 200 paid → ~$12K MRR
- 20,000 active self-host users → 400 paid → ~$25K MRR (target)

At 5% conversion (achievable if hosted-only features are genuinely compelling):
- 5,000 active → 250 paid → ~$15K MRR
- 10,000 active → 500 paid → ~$30K MRR

The 20K active user target aligns with Phase 3 distribution: HN Show HN (typically drives 2-5K stars → ~1K active users), Product Hunt (500-2K), plus organic growth from ClawHub/PyPI/awesome-lists over 6 months.
