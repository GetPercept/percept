# OpenClaw Integration

Percept is designed as a first-class [OpenClaw](https://openclaw.ai) skill, but works fully standalone.

## What is OpenClaw?

OpenClaw is an open-source agent runtime — a persistent AI assistant that runs on your machine with access to tools, memory, and communication channels. Think of it as the brain; Percept gives it ears.

## Installing as an OpenClaw Skill

```bash
openclaw skill install percept
```

This registers Percept's voice pipeline as an available skill in your OpenClaw agent.

## How Voice Commands Route Through OpenClaw

```
You speak → Omi → Percept Receiver → Wake word detected
                                          │
                                    Parse command
                                          │
                              openclaw agent --message "VOICE_ACTION: {...}"
                                          │
                                    OpenClaw agent session
                                          │
                                    Agent executes action
                                          │
                                    Result delivered (iMessage, etc.)
```

When Percept detects a wake word, it:

1. Extracts the command text after the wake word
2. Parses it into a structured `VOICE_ACTION` JSON (email, text, reminder, etc.)
3. Calls `openclaw agent --message` with the action payload
4. OpenClaw's agent interprets the action and executes it
5. Results are delivered back to you via your configured channel (iMessage, Discord, etc.)

For auto-summaries, Percept sends a `CONVERSATION_SUMMARY` prompt with the full transcript, and OpenClaw generates and delivers a human-readable summary.

## Configuration

Percept forwards to OpenClaw by default. The relevant code in `src/receiver.py`:

```python
proc = await asyncio.create_subprocess_exec(
    "/opt/homebrew/bin/openclaw", "agent", "--message", msg, "--to", "+14153414104",
    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    env=env,
)
```

To customize the delivery channel or target:

```bash
# Set agent mode
export PERCEPT_AGENT=openclaw

# Or use CLI
percept listen --agent openclaw
```

## Skill Pack Components

Percept provides five logical capabilities as an OpenClaw skill:

| Component | What It Does |
|-----------|-------------|
| **percept-listen** | Core audio pipeline — receives webhooks, transcribes, detects wake words |
| **percept-voice-cmd** | Parses voice commands into structured actions for the agent |
| **percept-summarize** | Auto-summarizes conversations after 60s silence |
| **percept-speaker-id** | Tracks and names speakers ("that was Sarah") |
| **percept-ambient** | Logs all ambient conversation for context and search |

All five run as part of the single `percept serve` process.

## Using Percept WITHOUT OpenClaw

Percept works standalone. You have three options:

### 1. stdout mode

Pipe JSON events to any consumer:

```bash
percept listen --agent stdout --format json | your-consumer
```

### 2. Webhook mode

Forward events to any HTTP endpoint:

```bash
percept listen --agent webhook --webhook-url https://your-agent.com/voice
```

### 3. Direct integration

Import Percept's components in your Python code:

```python
from src.transcriber import Transcriber, Segment, Conversation
from src.context import extract_context, save_conversation

# Use the transcriber directly
config = {...}
t = Transcriber(config)
segments = t.transcribe_audio(pcm_data)
```

---

Next: [Architecture](architecture.md) | [Getting Started](getting-started.md)
