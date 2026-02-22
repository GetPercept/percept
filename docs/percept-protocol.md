# Percept Protocol

> This document extends [protocol/PROTOCOL.md](../protocol/PROTOCOL.md) with integration examples.

## Overview

The Percept Protocol is a JSON-based message format for voice-to-action handoff between ambient audio pipelines and agent runtimes. It defines six event types covering the full lifecycle:

```
Audio → TranscriptEvent → ConversationEvent → SummaryEvent
                ↓
          IntentEvent → ActionRequest → ActionResponse
```

## Event Types

| Type | Description |
|------|-------------|
| `transcript` | Raw transcription segments with speaker/timing |
| `conversation` | Conversation boundary (silence-delimited) |
| `intent` | Parsed voice command with entities |
| `action_request` | Structured action ready for agent execution |
| `action_response` | Execution result (success/fail/needs_human) |
| `summary` | Auto-generated conversation summary |

## Transport

- **Default:** JSON Lines on stdout (one JSON object per line)
- **Optional:** WebSocket at `ws://localhost:{PORT}/events`
- **Optional:** Webhook (POST to configured URL)

```bash
# Filter events by type
percept listen --format json | jq 'select(.type == "intent")'
```

## Integration Guide: Consuming Percept Events

### 1. Pipe from stdout

The simplest integration — pipe Percept's JSON output into your agent:

```bash
percept listen --agent stdout --format json | python my_agent.py
```

In `my_agent.py`:

```python
import json
import sys

for line in sys.stdin:
    event = json.loads(line)
    
    if event["type"] == "intent":
        intent = event["intent"]
        entities = event["entities"]
        print(f"Voice command: {intent} → {entities}")
        
        if intent == "email":
            send_email(entities["to"], entities["body"])
        elif intent == "reminder":
            set_reminder(entities["task"], entities["when"])
    
    elif event["type"] == "summary":
        print(f"Meeting summary: {event['summary_text']}")
        notify_user(event["summary_text"])
```

### 2. Webhook consumer

Configure Percept to POST events to your server:

```bash
percept listen --agent webhook --webhook-url https://my-server.com/percept-events
```

Your server receives individual events:

```python
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/percept-events")
async def handle_event(request: Request):
    event = await request.json()
    
    if event["type"] == "action_request":
        # Execute the action
        result = execute_action(event["intent"], event["params"])
        return {"status": "executed", "result": result}
    
    return {"status": "ok"}
```

### 3. Direct Python import

Use Percept's components in your own pipeline:

```python
from src.transcriber import Transcriber, Segment, Conversation
from src.context import extract_context

config = {
    "whisper": {"model_size": "base", "device": "auto", "compute_type": "int8", "language": "en", "beam_size": 5},
    "audio": {"sample_rate": 16000, "silence_threshold_seconds": 30}
}

transcriber = Transcriber(config)
segments = transcriber.transcribe_audio(pcm_bytes)

conv = Conversation(segments=segments, started_at=time.time(), last_activity=time.time())
context = extract_context(conv)

print(context["action_items"])
print(context["topics"])
print(context["people"])
```

## Event Examples

### TranscriptEvent

```json
{
  "type": "transcript",
  "timestamp": "2026-02-20T14:30:00.000Z",
  "session_id": "sess_abc123",
  "segments": [
    {"speaker": "David", "text": "Hey Jarvis, email Sarah about the budget", "start": 0.0, "end": 4.2, "confidence": 0.94}
  ]
}
```

### IntentEvent

```json
{
  "type": "intent",
  "timestamp": "2026-02-20T14:30:05.000Z",
  "session_id": "sess_abc123",
  "wake_word_detected": true,
  "raw_text": "Hey Jarvis, email Sarah about the budget",
  "intent": "email",
  "entities": {"to": "Sarah", "body": "about the budget"},
  "confidence": 0.89
}
```

### ActionRequest

```json
{
  "type": "action_request",
  "timestamp": "2026-02-20T14:30:06.000Z",
  "request_id": "req_x7y8z9",
  "intent": "email",
  "params": {"to": "sarah@example.com", "subject": "Budget", "body": "Hi Sarah, following up on the budget discussion."},
  "requires_confirmation": true
}
```

### SummaryEvent

```json
{
  "type": "summary",
  "timestamp": "2026-02-20T14:36:00.000Z",
  "session_id": "sess_abc123",
  "duration": 300,
  "speakers": ["David", "Mike"],
  "summary_text": "David and Mike discussed the Q2 budget. Agreed to finalize by Friday.",
  "action_items": ["Finalize Q2 budget by Friday", "Email updated numbers to team"],
  "key_topics": ["Q2 budget", "timeline"]
}
```

## JSON Schemas

Formal schema files are in `protocol/schemas/`:

- [`transcript_event.json`](../protocol/schemas/transcript_event.json)
- [`conversation_event.json`](../protocol/schemas/conversation_event.json)
- [`intent_event.json`](../protocol/schemas/intent_event.json)
- [`action_request.json`](../protocol/schemas/action_request.json)
- [`action_response.json`](../protocol/schemas/action_response.json)
- [`summary_event.json`](../protocol/schemas/summary_event.json)

---

Next: [API Reference](api-reference.md) | [Architecture](architecture.md)
