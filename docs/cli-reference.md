# CLI Reference

```
percept <command> [options]
```

## Commands

### `percept serve`

Start the full Percept server (webhook receiver + dashboard).

```bash
percept serve [--port 8900] [--dashboard-port 8960] [--webhook-url URL]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--port` | `8900` | Receiver port (webhooks land here) |
| `--dashboard-port` | `8960` | Dashboard web UI port |
| `--webhook-url` | — | Forward events to this URL |

**Example:**

```bash
percept serve --port 9000 --dashboard-port 9060
```

```
⦿ Percept Server
  Receiver:  port 9000
  Dashboard: port 9060
  ● Dashboard started on http://localhost:9060
```

---

### `percept listen`

Start the receiver and output protocol events. Use this for piping into other tools.

```bash
percept listen [--agent openclaw|stdout|webhook] [--format json|text] \
               [--wake-word "Hey Jarvis"] [--port 8900] [--webhook-url URL]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--agent` | `openclaw` | Where to send actions: `openclaw`, `stdout`, `webhook` |
| `--format` | `json` | Output format for stdout: `json` or `text` |
| `--wake-word` | `Hey Jarvis` | Wake word phrase |
| `--port` | `8900` | Server port |
| `--webhook-url` | — | Webhook URL (when `--agent webhook`) |

**Examples:**

```bash
# Pipe JSON events to jq
percept listen --agent stdout --format json | jq 'select(.type == "intent")'

# Output text to a file
percept listen --agent stdout --format text >> /tmp/percept.log

# Forward to a custom webhook
percept listen --agent webhook --webhook-url https://my-agent.com/voice
```

---

### `percept status`

Show pipeline health and today's stats.

```bash
percept status
```

**Sample output:**

```
⦿ Percept Status

  ● Server        running on port 8900
  ● Live stream   active (updated 12s ago)

  Today
  Conversations:  7
  Words captured: 3,241
  Summaries:      3
  Last event:     2m ago
```

---

### `percept transcripts`

List recent transcript files.

```bash
percept transcripts [--today] [--search QUERY] [--limit N]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--today` | off | Show only today's transcripts |
| `--search` | — | Full-text search within transcripts |
| `--limit` | `20` | Max results |

**Examples:**

```bash
# Today's transcripts
percept transcripts --today

# Search for a keyword
percept transcripts --search "budget"
```

**Sample output:**

```
📝 Recent Transcripts

  2026-02-20 14:53   1,204 words  **Duration:** 245.2s | **Segments:** 18
  2026-02-20 13:57     342 words  **Duration:** 60.1s | **Segments:** 6
  2026-02-20 13:52     128 words  **Duration:** 30.0s | **Segments:** 3
```

---

### `percept actions`

List recent voice actions.

```bash
percept actions
```

**Sample output:**

```
⚡ Recent Actions

  ● 2026-02-20T14:30  email       executed
  ● 2026-02-20T14:25  reminder    executed
  ○ 2026-02-20T13:50  calendar    needs_human
```

> **Note:** Actions are stored in `data/actions/` as JSON files. If no actions directory exists yet, this command shows an empty list.

---

### `percept config`

Show or edit the configuration file.

```bash
# Show config
percept config

# Set a value
percept config --set KEY=VALUE
```

| Flag | Description |
|------|-------------|
| `--set KEY=VALUE` | Set a config value. Supports dotted keys. |
| `--show` | Explicitly show config (default behavior) |

**Examples:**

```bash
# View all config
percept config

# Change whisper model
percept config --set whisper.model_size=small

# Change port
percept config --set server.port=9000

# Toggle language
percept config --set whisper.language=es
```

Values are auto-parsed: `true`/`false` → bool, numbers → int/float, everything else → string.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error / missing command |

## Piping & Composability

Percept's `listen` command outputs JSON Lines, making it composable with standard Unix tools:

```bash
# Filter only intent events
percept listen --agent stdout --format json | jq 'select(.type == "intent")'

# Count words per minute
percept listen --agent stdout --format text | wc -w

# Log everything to file while also forwarding to agent
percept listen --agent stdout --format json | tee /tmp/percept.jsonl | my-agent-consumer

# Grep for a specific speaker
percept listen --agent stdout --format json | jq 'select(.segments[]?.speaker == "David")'
```

> **💡 Tip:** When using `--agent stdout`, status messages go to stderr so they don't pollute your JSON pipe.

---

---

## `percept search`

Semantic search over all indexed conversations.

```bash
percept search "what did we talk about pricing?"
percept search "meetings with the team" --limit 5
percept search "copper thesis" --date 2026-02-20
```

**Options:**
- `query` — search query (required, positional)
- `--limit N` — max results (default: 10)
- `--date YYYY-MM-DD` — filter to specific date

**Output:** Ranked list of matching conversation excerpts with dates, speakers, and distance scores (lower = more relevant).

**Prerequisites:** Run `scripts/index_vectors.py` first to build the vector index.

---

## `percept audit`

Show data statistics across all tables.

```bash
percept audit
```

**Output:**
```
📊 Percept Data Audit

  Conversations:       184
  Utterances:          488
  Speakers:              4
  Contacts:              3
  Actions:              28
  Projects:              0
  Entity Mentions:      32
  Relationships:         1
  Storage:        0.36 MB
```

---

## `percept purge`

Delete data from the database.

```bash
percept purge --older-than 90          # Conversations > 90 days old
percept purge --conversation ID        # Specific conversation + related data
percept purge --all --confirm          # Everything (requires --confirm)
percept purge                          # Only TTL-expired conversations
```

**Options:**
- `--older-than N` — delete conversations older than N days
- `--conversation ID` — delete a specific conversation and all related utterances, entities, actions
- `--all` — delete all data (requires `--confirm`)
- `--confirm` — required safety flag for `--all`

**Cascade:** Purging a conversation also deletes its utterances, entity mentions, and actions.

---

Next: [API Reference](api-reference.md) | [Configuration](configuration.md)
