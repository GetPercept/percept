# API Reference

Percept exposes two HTTP servers: the **Receiver** (port 8900) for webhooks, and the **Dashboard API** (port 8960) for the web UI.

## Receiver API (port 8900)

### `GET /health`

Health check.

```bash
curl http://localhost:8900/health
```

```json
{
  "status": "ok",
  "service": "percept",
  "uptime": 1708456800.0,
  "model": "base"
}
```

### `POST /webhook/transcript`

Receive real-time transcript segments from Omi.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `session_id` | string | `""` | Omi session ID |
| `uid` | string | `"default"` | Device/user ID |

**Request body:** JSON array of segments, or `{"segments": [...], "session_id": "..."}`.

```bash
curl -X POST http://localhost:8900/webhook/transcript?uid=my-device \
  -H "Content-Type: application/json" \
  -d '[
    {
      "text": "Hey Jarvis, remind me to call Rob",
      "speaker": "SPEAKER_00",
      "speakerId": 0,
      "is_user": true,
      "start": 0.0,
      "end": 3.5
    }
  ]'
```

**Response:**

```json
{"status": "ok", "segments_received": 1}
```

**What happens internally:**

1. Segments are accumulated per session
2. After 3s of silence (`SILENCE_TIMEOUT`), the buffer is flushed
3. If a wake word is detected, the command is parsed and dispatched to the agent
4. All segments are appended to the live file and conversation log

### `GET /webhook/transcript`

Omi sends a GET request to validate the webhook URL.

```json
{"status": "ok"}
```

### `POST /webhook/audio`

Receive raw PCM16 audio bytes for local transcription.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `uid` | string | `"default"` | Device/user ID |
| `sample_rate` | int | `16000` | Audio sample rate |

**Request body:** Raw PCM16 bytes (`application/octet-stream`).

Audio is buffered (10s chunks) and transcribed via faster-whisper in the background.

### `POST /webhook/memory`

Receive a completed memory/conversation object from Omi (sent when a conversation is finalized).

**Request body:** Omi memory JSON with `transcript_segments` and `structured` fields.

### `GET /conversations`

List saved conversation markdown files.

```bash
curl http://localhost:8900/conversations
```

```json
{
  "conversations": [
    "2026-02-20_14-53.md",
    "2026-02-20_13-57.md",
    "2026-02-20_13-52.md"
  ]
}
```

### `GET /status`

Pipeline status.

```json
{
  "active_buffers": 0,
  "current_conversation_segments": 12,
  "completed_conversations": 3,
  "buffer_sizes": {}
}
```

### `GET /context`

Current conversation context.

```json
{
  "active_speakers": ["David", "Sarah"],
  "conversation_duration_sec": 342.5,
  "segments_count": 24,
  "active_conversations": 1
}
```

### `GET /day-summary`

Aggregate stats for today.

```json
{
  "total_conversations": 7,
  "total_words": 3241,
  "speakers_seen": ["David", "Sarah"],
  "key_topics": ["budget", "timeline", "launch"],
  "date": "2026-02-20"
}
```

### `GET /tasks`

Extract action items from recent transcripts.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `hours` | float | `1.0` | How far back to scan |

```json
{
  "tasks": [
    {
      "text": "send the updated proposal to Mike",
      "action": "send",
      "time": "14:30",
      "context": "..."
    }
  ],
  "hours_scanned": 1.0
}
```

---

## Dashboard API (port 8960)

### `GET /`

Serves the dashboard HTML page.

### `GET /api/health`

Dashboard + receiver health.

```json
{
  "dashboard_uptime": 3600.0,
  "percept_online": true,
  "percept": {
    "status": "ok",
    "service": "percept",
    "model": "base"
  }
}
```

### `GET /api/conversations`

All conversations with parsed metadata (title, duration, segments, topics, people, transcript, actions).

<details>
<summary>Sample response</summary>

```json
[
  {
    "file": "2026-02-20_14-53.md",
    "title": "Conversation — 2026-02-20 14:53",
    "duration_s": 245.2,
    "segments": 18,
    "topics": ["budget", "timeline"],
    "people": ["Mike"],
    "transcript": [
      {"start": "0.0", "end": "3.5", "speaker": "SPEAKER_00", "text": "Let's talk about the budget."}
    ],
    "word_count": 1204,
    "date": "2026-02-20",
    "time": "14:53",
    "actions": []
  }
]
```

</details>

### `GET /api/summaries`

All conversation summaries.

### `GET /api/speakers`

Current speaker registry.

```json
{
  "SPEAKER_0": {"name": "David", "is_owner": true},
  "SPEAKER_00": {"name": "David", "is_owner": true},
  "SPEAKER_1": {"name": "Unknown", "is_owner": false}
}
```

### `GET /api/contacts`

Contact registry.

```json
{
  "john": {"email": "user@example.com", "phone": "+1XXXXXXXXXX", "aliases": ["johnny"]}
}
```

### `GET /api/live`

Last 100 lines of the live transcript stream.

```json
{
  "lines": ["--- 2026-02-20 14:30:00 ---", "[SPEAKER_00] Hey, how's it going?"],
  "total_lines": 342
}
```

### `GET /api/analytics`

Aggregate analytics: total words, words by period, speaker breakdown, segments per hour, detected actions.

<details>
<summary>Sample response</summary>

```json
{
  "total_words": 12450,
  "today_words": 3241,
  "week_words": 8900,
  "month_words": 12450,
  "total_duration_s": 7200,
  "speaker_words": {"SPEAKER_00": 8000, "SPEAKER_01": 4450},
  "segments_per_hour": {"14": 24, "13": 18},
  "actions": [],
  "conversation_count": 15,
  "summary_count": 8
}
```

</details>

### `GET /api/utterances?conversation_id=ID`

Get utterances for a specific conversation.

### `GET /api/search?q=QUERY&limit=20`

Full-text search across utterances (FTS5), with automatic fallback to vector search (LanceDB) if no FTS5 results found.

```json
{"results": [...], "query": "budget", "source": "fts5"}
```

### `GET /api/relationships?entity_id=NAME`

Get relationship graph for an entity. Returns weighted edges with types (mentioned_with, works_on, client_of).

### `GET /api/entities`

List all known entities with mention counts and last-mentioned timestamps.

### `GET /api/audit`

Data statistics across all tables + storage size.

### `GET /api/vector-stats`

Vector store statistics (total chunks, total conversations indexed).

### `GET /api/settings`

Get all runtime settings (wake words, timeouts, transcriber config, TTL settings).

### `POST /api/settings`

Update runtime settings. Body: JSON object of key-value pairs.

### `GET /api/settings/speakers`

Get all speakers with word counts, segment counts, relationships.

### `POST /api/settings/speakers`

Update speaker names/relationships. Body: `{"SPEAKER_ID": {"name": "...", "relationship": "..."}}`

### `GET /api/settings/contacts`

Get all contacts from the database.

### `POST /api/settings/contacts`

Add a contact. Body: `{"name": "...", "email": "...", "phone": "...", "relationship": "..."}`

### `DELETE /api/settings/contacts/{id}`

Delete a contact by ID.

### `POST /api/purge`

Purge old data. Body: `{"ttl_utterances_days": 30, "ttl_summaries_days": 90}`

### `GET /api/export`

Export all data as JSON (conversations, speakers, contacts, actions, relationships, settings, audit stats). Returns as downloadable `percept-export.json`.

---

## Authentication

Percept uses **three layers of security** on all inbound endpoints:

### 1. Webhook Token Authentication

All webhook and audio endpoints require a token. Set it with:

```bash
percept config set webhook_secret YOUR_SECRET_TOKEN
```

Then authenticate requests using either method:

- **URL parameter:** `POST /webhook/transcript?token=YOUR_SECRET_TOKEN`
- **Bearer header:** `Authorization: Bearer YOUR_SECRET_TOKEN`

Requests without a valid token receive `401 Unauthorized`.

### 2. Speaker Authorization

Only authorized speakers can trigger voice commands. Manage the allowlist:

```bash
percept speakers authorize SPEAKER_0    # Add a speaker
percept speakers revoke SPEAKER_0       # Remove a speaker
percept speakers list                   # Show all speakers
```

Unauthorized speakers are logged and their transcripts are recorded but commands are **not executed**.

### 3. Command Safety Classifier

The intent parser includes an injection classifier that blocks attempts to:
- Exfiltrate credentials or environment variables
- Execute system commands (SSH, shell access)
- Dump sensitive data (IP addresses, tokens)

Blocked attempts are logged to the security audit log:

```bash
percept security-log    # View all blocked attempts
```

### Dashboard Authentication

The dashboard (port 8960) uses password authentication. Set the password in your config:

```json
{
  "dashboard": {
    "password": "your-dashboard-password"
  }
}
```

> **Recommendation:** Always run Percept behind a reverse proxy (e.g., Cloudflare Tunnel) with HTTPS for production deployments.

---

## MCP Tools (Model Context Protocol)

Percept includes a built-in MCP server (`src/mcp_server.py`) that exposes all capabilities as Claude-native tools.

### Starting the MCP Server

```bash
percept mcp                    # Via CLI
python -m src.mcp_server       # Standalone
```

### Tools

#### `percept_search(query: str, limit: int = 10) → JSON`
Full-text search across utterances (FTS5) with fallback to conversation-level search. Supports FTS5 syntax (AND, OR, NOT, phrases).

#### `percept_transcripts(today_only: bool = False, limit: int = 20) → JSON`
List recent transcripts with metadata (date, speakers, word count, summary, preview).

#### `percept_actions(limit: int = 20) → JSON`
List voice command history with intent, parameters, status, and execution results.

#### `percept_speakers() → JSON`
List all known speakers with word counts, segment counts, activity timestamps, and authorization status.

#### `percept_status() → JSON`
Pipeline health check: server status, live stream status, today's stats, database audit.

#### `percept_security_log(limit: int = 20) → JSON`
View blocked attempts — unauthorized speakers, invalid webhook auth, injection detection.

#### `percept_conversations(limit: int = 20) → JSON`
List conversations with summaries, durations, speakers, and topics.

#### `percept_listen(limit: int = 50) → JSON`
Get latest live transcript events from the real-time stream file.

### Resources

| URI | Description |
|-----|-------------|
| `percept://status` | Current pipeline status (JSON) |
| `percept://speakers` | Known speakers list (JSON) |

---

Next: [Architecture](architecture.md) | [Percept Protocol](percept-protocol.md)
