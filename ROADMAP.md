# Roadmap

Percept is evolving fast. Here's where we're headed.

## ✅ Shipped

- **Core Pipeline** — Omi → transcription → wake word → agent action
- **Wake Word Commands** — "Hey Jarvis, send an email..." triggers real actions
- **Meeting Summaries** — auto-generated conversation recaps with action items
- **Speaker Resolution** — know who's talking
- **Entity Extraction** — people, orgs, locations, topics pulled from conversations
- **Relationship Graph** — connections between entities tracked over time
- **Full-Text Search** — search across all conversations
- **Dashboard** — real-time transcripts, analytics, settings, search
- **5 OpenClaw Skills** — available on ClawHub
- **Apple Watch App** — push-to-talk companion (in testing)

## 🔜 Next Up

- **CLI-First Design** — `pip install getpercept && percept listen`. Any agent that can run shell commands gets ears. OpenClaw, Claude, ChatGPT, Manus, LangChain — all of them
- **Semantic Search** — vector embeddings for "find conversations about..." queries
- **More Hardware** — any Bluetooth mic, smart glasses, ESP32 devices. If it has a microphone, Percept should work with it
- **Speaker Intelligence** — voice fingerprinting, speaker-aware search ("what did David say about the budget?")
- **Security Hardening** — webhook auth, E2E encryption, dashboard auth ([#1](https://github.com/GetPercept/percept/issues/1))

## 🔮 Future

- **Predictive Context** — your agent knows what you need before you ask
- **Knowledge Graph Queries** — multi-hop reasoning across conversations
- **Multi-Agent Support** — multiple agents sharing context appropriately
- **MCP Integration** — for frameworks that support Model Context Protocol
- **Domain-Specific Tuning** — healthcare, legal, finance verticals

## Philosophy

- **CLI is the universal interface** — every agent can exec
- **Local-first** — your conversations stay on your machine
- **Hardware-agnostic** — we're not locked to one device
- **Open source** — the community builds faster than any one team

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get involved. Check [Issues](https://github.com/GetPercept/percept/issues) for things to work on.

We're especially looking for help with:
- New hardware integrations
- Transcription engine alternatives
- CLI improvements
- Documentation and examples
