# Percept — The Context Layer for AI Agents

Give your AI agent ears, eyes, and awareness.

Percept connects your real-world data to your AI agent through hardware capture, tool connectors, and a knowledge graph that enables your agent to take initiative.

## What It Does

- **🎧 Hear** — Omi pendant captures ambient audio. Chrome extension captures browser audio. Meetings, conversations, podcasts — all transcribed and searchable.
- **⌚ Interact** — Apple Watch app with push-to-talk, raise-to-speak, and complications.
- **🔗 Connect** — Gmail, GitHub, Linear, Calendar, Slack connectors sync your work context.
- **🧠 Understand** — Knowledge graph connects people, projects, conversations, and events across all sources.
- **⚡ Act** — Initiative engine detects patterns and triggers actions without being asked.

## Quick Start

```bash
pip install getpercept
percept serve          # Start the audio pipeline
percept sync           # Sync all connected tools
percept status         # Check what your agent knows
```

## Architecture

```
Hardware (Omi, Watch, Chrome)  → Audio Pipeline → Transcription
Tool Connectors (Gmail, GitHub, Linear) → Data Sync
                    ↓
    Knowledge Graph (entities, relationships, temporal)
                    ↓
    Initiative Engine (patterns → actions)
                    ↓
    Your AI Agent (OpenClaw, Claude, GPT, LangChain)
```

## Package Structure

```
percept/
├── percept/                 # Python package
│   ├── audio/               # Audio pipeline (receiver, transcriber, context)
│   ├── core/                # Knowledge graph (graph DB, ingest, query, temporal)
│   ├── connectors/          # SDK + Gmail, GitHub, Linear, Calendar, Slack
│   ├── pipeline/            # Orchestration (sync → KG → signals → initiatives)
│   ├── initiatives/         # Rules engine, pattern matching, actions
│   ├── mesh/                # Team agent shared context
│   ├── memory/              # Entity extraction, FTS5 search
│   ├── mcp/                 # MCP server for Claude Desktop
│   └── cli.py               # Unified CLI entry point
├── src/                     # Legacy audio module (original package root)
├── watch-app/               # Apple Watch app (Swift)
├── extension/               # Chrome extension (browser audio capture)
├── web/                     # Landing page
├── docs/                    # Documentation
└── tests/                   # Test suite
```

## Connectors

| Connector | Status | What It Captures |
|-----------|--------|-----------------|
| Omi Pendant | ✅ Live | Ambient audio, meetings, conversations |
| Apple Watch | ✅ TestFlight | Push-to-talk, raise-to-speak |
| Chrome Extension | ✅ Built | Browser tab audio (meetings, YouTube, podcasts) |
| Gmail | ✅ Live | Emails, threads, contacts |
| GitHub | ✅ Live | PRs, issues, commits, reviews |
| Linear | ✅ Live | Tickets, projects, team activity |
| Calendar | 🔶 Ready | Events, attendees (needs Google API enabled) |
| Slack | 📋 Planned | Messages, channels, threads |

## CLI Commands

```bash
percept sync                    # Run all connectors → KG → initiatives
percept sync --connector gmail  # Single connector
percept status                  # KG stats + connector health + initiatives
percept query "..."             # Search the knowledge graph
percept serve                   # Start the audio pipeline + API
percept connectors              # List installed connectors
percept initiatives             # List triggered initiatives
```

## Works With Any AI Framework

Percept is framework-agnostic. It provides context via:

- **CLI** — `percept sync`, `percept query`
- **MCP Server** — 8 tools for Claude Desktop integration
- **REST API** — HTTP endpoints for any framework
- **Python SDK** — `from percept.core.graph.database import GraphDB`

## License

MIT
