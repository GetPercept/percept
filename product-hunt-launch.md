# Product Hunt Launch — Percept

## Tagline (60 chars max)
`Give your AI agent ears — open-source ambient voice intelligence`

## One-liner (alt)
`Open-source voice pipeline that turns wearables into AI agent ears`

## Description

### Hook (first 2 lines — this is what shows in the feed)
Percept is an open-source ambient voice pipeline that connects wearable microphones to AI agents. Speak naturally, and your agent executes commands, summarizes meetings, identifies speakers, and builds a searchable knowledge graph — all processed locally.

### The Problem
AI agents are powerful but deaf. They live in text boxes. Meanwhile, you're in meetings, walking around, having conversations full of context your agent never sees. Copy-pasting transcripts is tedious. Existing tools just transcribe — they don't *understand*.

### The Solution
Percept adds a **Context Intelligence Layer** between your voice and your AI:

🎙️ **Ambient voice pipeline** — Wear an Omi pendant or Apple Watch. Speak naturally. Your agent listens.

🧠 **Context Intelligence** — Not just transcription. Entity extraction, relationship graphs, speaker identification, and semantic search transform speech into structured, actionable context.

🔌 **Works with your stack** — MCP server for Claude Desktop, OpenClaw integration, Zoom/Granola/Chrome connectors. pip install and go.

🔒 **Local-first** — Everything runs on your machine. SQLite, local whisper models, optional NVIDIA NIM for quality. Your conversations never leave your hardware.

### What you can do today:
- Say "Hey Jarvis, remind me to check email" → agent creates reminder
- Walk out of a meeting → auto-summary sent to your phone
- Ask Claude "what did Sarah say about the Q3 budget?" → semantic search across all conversations
- Capture any meeting (Zoom, Google Meet, Teams) via browser extension

### Built with:
- faster-whisper (local ASR, M-series optimized)
- NVIDIA NIM embeddings + LanceDB vector search
- MCP protocol (8 tools, Claude Desktop verified)
- SQLite + FTS5 (14 tables, WAL mode)
- FastAPI + Cloudflare tunnel

### Install:
```
pip install getpercept
percept serve
```

## Topics/Tags
- Artificial Intelligence
- Developer Tools
- Open Source
- Voice Recognition  
- MCP

## Maker Comment (post after launch)
Hey PH! 👋

I built Percept because I wanted my AI agent to actually know what's happening in my life — not just what I type into a chat box.

I wear an Omi pendant all day. Every conversation, every meeting, every random idea gets captured. But raw transcripts are useless without structure. So I built a Context Intelligence Layer that extracts entities, maps relationships, resolves speakers, and makes everything searchable.

The MCP integration is the magic — ask Claude "what commitments did I make this week?" and it searches across every conversation you've had.

Everything runs locally on your Mac. MIT licensed. Would love feedback on what connectors to build next.

## First Day Comments to Seed

### Comment 1 (technical)
"The MCP server integration is the sleeper feature here. 8 tools that give Claude Desktop access to your entire conversation history with semantic search. `pip install getpercept` and you're running."

### Comment 2 (use case)
"Been using this for 2 weeks with an Omi pendant. The auto-summaries after meetings are genuinely useful — it identifies who said what and sends a summary to my phone. Speaker identification gets better over time."

### Comment 3 (open source angle)
"Refreshing to see a local-first approach. Everything runs on SQLite + local whisper. No cloud dependency, no subscription. The NVIDIA NIM integration is optional for higher quality embeddings."

## Media Assets Needed
- [ ] Hero image (1270x760) — dashboard screenshot + Omi pendant photo
- [ ] Gallery image 1: MCP integration with Claude Desktop
- [ ] Gallery image 2: Dashboard showing conversation analytics
- [ ] Gallery image 3: CLI in action
- [ ] Demo video (existing demo.mp4 + demo-mcp.mov — combine into 2min)
- [ ] Maker avatar

## Launch Timing
- **Best days:** Tuesday-Thursday
- **Target:** Thursday this week (Mar 6) or Tuesday next week (Mar 11)
- **Launch time:** 12:01 AM PT (Product Hunt resets at midnight PT)
- **Critical hours:** First 4 hours determine ranking

## Pre-Launch Checklist
- [x] PyPI package live (`pip install getpercept`)
- [x] GitHub repo public
- [x] README with demo videos
- [x] MCP server shipped
- [x] Meeting connectors shipped
- [x] Reddit posts live (r/ClaudeAI)
- [ ] Product Hunt maker profile updated
- [ ] Hero image created
- [ ] Gallery images prepared
- [ ] Combined demo video (2 min max)
- [ ] Ship page created (pre-launch followers)
- [ ] Notify existing community (Discord, Reddit, X)
- [ ] Schedule launch post on X (@getpercept)
- [ ] Prepare 10 upvotes from network in first hour

## Post-Launch (first 24h)
- Reply to every comment within 30 min
- Post update at 4h, 8h, 16h marks
- Share on X, Reddit, Discord, LinkedIn
- Submit to awesome-mcp-servers if not already
- HN "Show HN" post (same day or next day)
