# Contributing to Percept

Welcome! Percept gives AI agents ears — ambient voice intelligence for OpenClaw and beyond. 🦞

## Quick Links

- **GitHub:** https://github.com/GetPercept/percept
- **X/Twitter:** [@getpercept](https://x.com/getpercept)
- **OpenClaw Discord:** https://discord.gg/qkhbAGHRBT

## Maintainers

- **GetPercept Team** - Creator
  - GitHub: [@getpercept](https://github.com/getpercept) · X: [@jarv31168](https://x.com/jarv31168)

## How to Contribute

1. **Bugs & small fixes** → Open a PR directly
2. **New features / architecture changes** → Open a GitHub Issue or Discussion first
3. **Skills** → Add or improve skills in `skills/`
4. **Docs** → Always welcome, no discussion needed
5. **Questions** → Open an issue or ask in OpenClaw Discord

## Before You PR

- Test locally with your Percept + OpenClaw setup
- Run tests: `cd percept && python -m pytest tests/ -v`
- Keep PRs focused — one thing per PR
- Describe what & why in the PR description

## Development Setup

```bash
# Clone
git clone https://github.com/GetPercept/percept.git
cd percept

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v

# Start the receiver
PYTHONPATH=. python -m uvicorn src.receiver:app --host 0.0.0.0 --port 8900

# Start the dashboard
PYTHONPATH=. python -m uvicorn src.dashboard:app --host 0.0.0.0 --port 8960
```

## Project Structure

```
percept/
├── src/                    # Core source code
│   ├── receiver.py         # FastAPI webhook receiver
│   ├── transcriber.py      # Audio transcription (Whisper, NVIDIA, cloud)
│   ├── intent_parser.py    # Two-tier intent parsing (regex + LLM)
│   ├── action_dispatcher.py # Voice command routing to OpenClaw
│   ├── speaker_manager.py  # Speaker identification & authorization
│   ├── entity_extractor.py # Entity extraction from conversations
│   ├── context_engine.py   # Context Intelligence Layer
│   ├── database.py         # SQLite persistence (11 tables, FTS5)
│   ├── vector_store.py     # LanceDB semantic search
│   ├── flush_manager.py    # Transcript buffering & wake word detection
│   ├── summary_manager.py  # Conversation summarization
│   ├── dashboard.py        # Real-time monitoring dashboard
│   └── cli.py              # Command-line interface
├── skills/                 # ClawHub skill definitions
├── tests/                  # Test suite
├── data/                   # Local data (gitignored)
├── docs/                   # Documentation
└── landing/                # Landing page
```

## Areas We Need Help

### High Priority
- **Hardware integrations** — More wearable devices beyond Omi and Apple Watch
- **Transcriber backends** — Deepgram, AssemblyAI, Azure Speech integrations
- **Speaker diarization** — pyannote voice embeddings for automatic speaker ID
- **Language support** — Non-English wake words, multilingual transcription

### Medium Priority
- **Dashboard improvements** — Better visualizations, entity graph rendering
- **Privacy features** — On-device encryption, selective redaction
- **Agent framework integrations** — Beyond OpenClaw (LangChain, CrewAI, AutoGen)
- **Performance** — Optimize SQLite queries, reduce memory footprint

### Always Welcome
- Bug fixes
- Documentation improvements
- Test coverage
- Code cleanup and refactoring

## AI-Assisted PRs Welcome 🤖

Built with Codex, Claude, or other AI tools? Great — just mark it.

Include in your PR:
- [ ] Mark as AI-assisted in the PR title or description
- [ ] Note the degree of testing
- [ ] Confirm you understand what the code does

AI PRs are first-class citizens. We just want transparency.

## Code Style

- Python 3.9+ compatible (no union types with `|`, use `Optional`, `List`, `Dict`)
- Type hints on all public functions
- Docstrings on all modules and public functions
- SQLite compatible types (no PostgreSQL-specific features)
- Async where appropriate (FastAPI handlers, external API calls)

## Commit Messages

Use conventional commits:
```
feat: add Deepgram transcriber backend
fix: handle empty transcript segments
docs: update setup instructions for Apple Watch
test: add intent parser edge cases
```

## Security

- **Never commit API keys, tokens, or credentials**
- **Audio data stays local** — don't add features that upload raw audio
- **Speaker authorization is a security boundary** — treat it carefully
- Report vulnerabilities via GitHub Issues (private) or email hello@getpercept.ai

## First 50 Contributors 🎁

The first 50 people who contribute meaningfully get **lifetime Pro access** to the hosted Percept API when it launches. Star the repo, submit a PR, or file a detailed bug report — anything that helps counts.

## License

MIT — free forever. See [LICENSE](LICENSE).
