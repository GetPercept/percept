# Percept Documentation

## Guides

| Doc | Description |
|-----|-------------|
| [Getting Started](getting-started.md) | Install, configure Omi, first voice command, Cloudflare tunnel |
| [Configuration](configuration.md) | Config file, wake words, transcriber, CIL settings, vector store, environment variables |
| [CLI Reference](cli-reference.md) | Every command (serve, listen, status, transcripts, actions, search, audit, purge, config) |
| [API Reference](api-reference.md) | Receiver webhooks (port 8900), Dashboard API (port 8960), all endpoints |

## Architecture

| Doc | Description |
|-----|-------------|
| [Architecture](architecture.md) | Pipeline diagram, CIL design, data flow, vector store, extending Percept |
| [Percept Protocol](percept-protocol.md) | JSON event protocol (6 types), transports, integration examples |
| [OpenClaw Integration](openclaw-integration.md) | Skill pack, voice command routing, standalone usage |

## Project

| Doc | Description |
|-----|-------------|
| [Decisions](DECISIONS.md) | 21 Architecture Decision Records — what we chose and why |
| [Roadmap](ROADMAP.md) | 4 phases, current status, tracks (Watch, launch, NVIDIA, ClawHub) |
| [Contributing](contributing.md) | Dev setup, code structure, PR guidelines, good first issues |

## Also See

| File | Location | Description |
|------|----------|-------------|
| [Protocol Spec](../protocol/PROTOCOL.md) | `protocol/` | Full protocol specification with JSON Schema |
| [Watch App](../watch-app/README.md) | `watch-app/` | Apple Watch push-to-talk app documentation |
| [CHANGELOG](../CHANGELOG.md) | Root | Version history and all features built |
| [GTM Playbook](../GTM.md) | Root | Go-to-market strategy |
| [CIL Spec](../../shared-jarvis/Percept_Context_Intelligence_Layer_Spec.docx) | `shared-jarvis/` | Context Intelligence Layer technical specification (David, Feb 21) |
