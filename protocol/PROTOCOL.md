# Percept Protocol Specification

**Version:** 0.1.0  
**Status:** Draft  
**Date:** 2026-02-20

---

## Overview

The Percept Protocol defines a JSON-based message format for voice-to-action handoff between ambient audio pipelines and agent runtimes. It covers the full lifecycle: raw transcription → conversation detection → intent parsing → action execution → response.

## Why a Protocol?

Voice pipelines and agent runtimes are separate concerns. A transcription system shouldn't need to know how actions get executed. An agent shouldn't need to parse raw audio.

The Percept Protocol is the contract between them:

- **Unix composable** — default transport is JSON Lines on stdout. Pipe `percept listen` into `jq`, `grep`, or any agent runtime.
- **Runtime agnostic** — works with OpenClaw, LangChain, custom scripts, or a human reading a terminal.
- **Incrementally adoptable** — consume only the event types you care about. Ignore the rest.
- **Observable** — every event is self-describing with timestamps and session IDs. Debugging is reading JSON.

The same protocol works whether your agent is a local CLI, a cloud function, or a person with a webhook dashboard.

---

## Transport

### Default: stdout (JSON Lines)

One JSON object per line, newline-delimited. This is the primary transport.

```
{"type":"transcript","timestamp":"2026-02-20T14:30:00Z","session_id":"abc123",...}
{"type":"intent","timestamp":"2026-02-20T14:30:05Z","session_id":"abc123",...}
```

### Optional: WebSocket

Connect to `ws://localhost:{PORT}/events` to receive events as they occur.

### Optional: Webhook

Configure a URL. Events are POSTed individually as JSON with `Content-Type: application/json`.

---

## Message Types

All messages share a common envelope:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Event type identifier |
| `timestamp` | string | ISO 8601 UTC timestamp |

### 1. TranscriptEvent

Raw transcription output from the audio pipeline.

```json
{
  "type": "transcript",
  "timestamp": "2026-02-20T14:30:00.000Z",
  "session_id": "sess_a1b2c3",
  "segments": [
    {
      "speaker": "David",
      "text": "Hey can you send an email to Mike about the meeting tomorrow",
      "start": 0.0,
      "end": 4.2,
      "confidence": 0.94
    },
    {
      "speaker": "unknown",
      "text": "Sure, what should I say?",
      "start": 4.5,
      "end": 6.1,
      "confidence": 0.91
    }
  ]
}
```

### 2. ConversationEvent

Emitted when a conversation boundary is detected (e.g., silence gap exceeding threshold).

```json
{
  "type": "conversation",
  "timestamp": "2026-02-20T14:35:00.000Z",
  "session_id": "sess_a1b2c3",
  "duration_seconds": 300,
  "segment_count": 24,
  "speakers": ["David", "Mike"],
  "topics": ["meeting", "project timeline"],
  "transcript": "David: Hey can you send an email to Mike about the meeting tomorrow\nMike: Sure, what should I say?\n..."
}
```

### 3. IntentEvent

A parsed voice command, extracted from transcript segments.

```json
{
  "type": "intent",
  "timestamp": "2026-02-20T14:30:05.000Z",
  "session_id": "sess_a1b2c3",
  "wake_word_detected": true,
  "raw_text": "Hey Jarvis, send an email to Mike about the meeting tomorrow",
  "intent": "email",
  "entities": {
    "to": "Mike",
    "body": "about the meeting tomorrow"
  },
  "confidence": 0.89,
  "context": "David and Mike were discussing project timelines for the Q2 launch."
}
```

**Intent values:** `email` | `text` | `reminder` | `search` | `order` | `calendar` | `note` | `unknown`

### 4. ActionRequest

A structured action ready for agent execution. Derived from an IntentEvent.

```json
{
  "type": "action_request",
  "timestamp": "2026-02-20T14:30:06.000Z",
  "request_id": "req_x7y8z9",
  "intent": "email",
  "params": {
    "to": "mike@example.com",
    "subject": "Meeting Tomorrow",
    "body": "Hi Mike, just confirming our meeting tomorrow. Let me know if the time still works."
  },
  "context": "David asked to email Mike about tomorrow's meeting during a conversation about Q2 timelines.",
  "requires_confirmation": true,
  "human_required": false
}
```

### 5. ActionResponse

The agent's response after attempting to execute an action.

```json
{
  "type": "action_response",
  "timestamp": "2026-02-20T14:30:10.000Z",
  "request_id": "req_x7y8z9",
  "status": "executed",
  "result": "Email sent to mike@example.com with subject 'Meeting Tomorrow'",
  "error": null
}
```

**Status values:** `executed` | `pending` | `failed` | `needs_human`

### 6. SummaryEvent

Auto-generated summary after a conversation ends.

```json
{
  "type": "summary",
  "timestamp": "2026-02-20T14:36:00.000Z",
  "session_id": "sess_a1b2c3",
  "duration": 300,
  "speakers": ["David", "Mike"],
  "summary_text": "David and Mike discussed the Q2 project timeline. They confirmed a meeting for tomorrow and agreed to finalize the budget by Friday.",
  "action_items": [
    "Email Mike to confirm meeting",
    "Finalize Q2 budget by Friday"
  ],
  "key_topics": ["Q2 timeline", "meeting", "budget"]
}
```

---

## Event Flow

```
Audio In → TranscriptEvent → ConversationEvent
                ↓                    ↓
          IntentEvent          SummaryEvent
                ↓
         ActionRequest
                ↓
         ActionResponse
```

Not every transcript produces an intent. Not every intent becomes an action. Events are emitted independently as the pipeline processes audio.

---

## Filtering

Consumers can filter by `type` field:

```bash
percept listen --format json | jq 'select(.type == "intent")'
```

---

## Versioning

This spec follows semantic versioning. Breaking changes increment the major version. The protocol version is not embedded in messages (v0.x assumes all consumers are co-deployed). A `version` field will be added at v1.0.

---

## Schema Files

Formal JSON Schema definitions for each message type are in `protocol/schemas/`:

- `transcript_event.json`
- `conversation_event.json`
- `intent_event.json`
- `action_request.json`
- `action_response.json`
- `summary_event.json`

---

## License

MIT
