# Getting Started

Get Percept running in under 5 minutes.

## Prerequisites

- **Python 3.10+**
- **Omi pendant** (or any device that can POST transcripts via webhook)
- **macOS or Linux** (Windows via WSL)

## Installation

### Option A: pip install

```bash
pip install getpercept
```

### Option B: From source

```bash
git clone https://github.com/davidemanuelDEV/percept.git
cd percept
pip install -r requirements.txt
```

Requirements are minimal:

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
faster-whisper>=1.0.0
numpy
```

## Omi Setup

1. **Get an Omi pendant** from [omi.me](https://omi.me)
2. Install the **Omi app** on your phone
3. Pair your pendant via Bluetooth
4. In the Omi app, go to **Developer Settings**
5. Set your **Transcript Webhook URL** to:

```
https://your-server:8900/webhook/transcript
```

> **💡 Tip:** For local development, you'll need a tunnel. See [Cloudflare Tunnel](#cloudflare-tunnel-setup) below.

## First Run

```bash
# From source:
cd percept
python -m src.cli serve

# Or if installed via pip:
percept serve
```

You should see:

```
⦿ Percept Server
  Receiver:  port 8900
  Dashboard: port 8960
  ● Dashboard started on http://localhost:8960
```

## Verify It's Working

```bash
percept status
```

```
⦿ Percept Status

  ● Server        running on port 8900
  ○ Live stream   no data

  Today
  Conversations:  0
  Words captured: 0
  Summaries:      0
```

## Cloudflare Tunnel Setup

Omi needs a public URL to send webhooks to your local Percept server.

```bash
# Install cloudflared
brew install cloudflared

# Create a tunnel
cloudflared tunnel --url http://localhost:8900
```

Cloudflared will output a URL like `https://random-name.trycloudflare.com`. Use that as your Omi webhook URL:

```
https://random-name.trycloudflare.com/webhook/transcript
```

> **⚠️ Warning:** The free tunnel URL changes on restart. For a permanent URL, set up a [named tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).

## Your First Voice Command

With Percept running and Omi streaming:

1. Say: **"Hey Jarvis, remind me to check email"**
2. Percept detects the wake word "Jarvis"
3. Parses the intent as a `reminder` action
4. Forwards to your agent (OpenClaw or webhook)
5. You get a text/notification with the reminder

Check the logs:

```
[TRANSCRIPT] [SPEAKER_00] Hey Jarvis, remind me to check email.
[WAKE] Wake word detected! Forwarding to OpenClaw
[DISPATCH] VOICE_ACTION: {"action": "reminder", "task": "check email", "when": ""}
[OPENCLAW] Sent successfully
```

## Dashboard

Open `http://localhost:8960` to see the Percept dashboard with:

- **Live transcript feed** — real-time stream of incoming speech
- **Conversation history** — searchable archive with speaker labels and summaries
- **Speaker registry** — known speakers with word counts and relationships
- **Analytics** — words/day, segments/hour, speaker breakdown, action history
- **Settings** — manage wake words, speakers, contacts, transcriber config
- **Search** — FTS5 keyword search with LanceDB vector search fallback
- **Entity graph** — browse extracted entities and relationships
- **Data management** — export all data as JSON, purge by age or TTL

## Troubleshooting

### Server won't start

```
Error: uvicorn not installed
```

Fix: `pip install uvicorn[standard] fastapi`

### No transcripts arriving

1. Check Omi is connected (green light on pendant)
2. Verify your webhook URL is correct in the Omi app
3. Test the endpoint: `curl http://localhost:8900/health`
4. Check tunnel is running if using Cloudflare

### Wake word not detected

- Speak clearly: **"Hey Jarvis"** with a pause before your command
- The default wake word is `jarvis` (case-insensitive)
- Customize in `config/config.json` or via CLI: `percept config --set wake_word=alexa`

### Whisper model too slow

Switch to a smaller model:

```bash
percept config --set whisper.model_size=tiny
```

Available models: `tiny`, `base` (default), `small`, `medium`, `large-v3`

---

Next: [Configuration](configuration.md) | [CLI Reference](cli-reference.md)
