# Percept Browser Audio Capture — Chrome Extension

**Give any AI agent ears for the browser.** One extension captures audio from any Chrome tab — meetings, YouTube, podcasts, webinars, courses, earnings calls, customer support tools — and streams it to your AI pipeline.

## Why This Exists

Your AI agent is deaf to everything happening in your browser. Meeting platforms each have their own API (if they have one at all). YouTube has no transcript API for live content. Podcasts, webinars, courses — no programmatic access.

This extension captures audio directly from any browser tab using Chrome's `tabCapture` API and streams PCM16 audio to a local HTTP endpoint. Your AI agent receives structured audio chunks it can transcribe, summarize, search, or act on — from anything playing in Chrome.

### What can your agent do with browser audio?
- **Train your agent on any subject** → Play lectures, podcasts, tutorials. Your agent builds a searchable knowledge graph — entities, relationships, key concepts. Ask questions later: "What did they say about X in lecture 3?"
- **Meetings** → Auto-summarize, extract action items, follow up
- **YouTube/tutorials** → Searchable notes, reference anything you've watched
- **Podcasts/webinars** → Capture insights while you listen
- **Earnings calls** → Extract financial signals, competitor intel
- **Online courses** → Structured knowledge base of everything you've learned
- **Customer calls** → Sentiment analysis, objection tracking, auto-CRM updates

## Works With Any AI Framework

The extension sends audio via HTTP POST. Any framework that can receive HTTP requests gets meeting audio:

- **OpenClaw** — Install as a skill: `clawhub install browser-audio-capture`
- **Claude** (via MCP or tool use) — Point at the `/audio/browser` endpoint
- **ChatGPT** (via Actions API) — Connect to the Percept REST API
- **LangChain / CrewAI / AutoGen** — HTTP POST → your agent's audio pipeline
- **Custom agents** — Any language, any framework, just `POST /audio/browser`

## Install

1. Open `chrome://extensions/`
2. Enable **Developer mode** (top right toggle)
3. Click **Load unpacked**
4. Select this folder

## Use

1. Join a meeting in Chrome (Zoom, Google Meet, Teams, Webex, etc.)
2. Click the **Percept icon** in the toolbar
3. Click **Start Capturing This Tab**
4. Audio streams to `http://localhost:8900/audio/browser`
5. **Close the popup** — capture continues in the background via offscreen document

To stop: click the Percept icon again → **Stop Capturing**

## Supported Platforms

Works with any meeting that runs in a browser tab:

Google Meet • Zoom (web) • Microsoft Teams • Webex • Whereby • Around • Cal.com • Riverside • StreamYard • Ping • Daily.co • Jitsi • Discord

Plus any future platform — no updates needed. If it plays audio in a tab, we capture it.

## Audio Format

```json
{
  "sessionId": "browser_1709234567890",
  "audio": "<base64 encoded PCM16>",
  "sampleRate": 16000,
  "format": "pcm16",
  "source": "browser_extension",
  "tabUrl": "https://meet.google.com/abc-defg-hij",
  "tabTitle": "Weekly Standup"
}
```

- **Encoding:** PCM16 (16-bit signed integers)
- **Sample rate:** 16kHz (optimal for speech recognition)
- **Chunk interval:** Every 3 seconds
- **Transport:** HTTP POST with JSON body

## Configure Endpoint

Edit `offscreen.js`, line 7:

```js
const PERCEPT_URL = "http://127.0.0.1:8900";  // Change to your endpoint
```

## Architecture

```
Tab Audio → chrome.tabCapture (popup, user gesture)
         → streamId passed to background service worker
         → offscreen document (persists after popup closes)
         → AudioContext + ScriptProcessor → PCM16 conversion
         → base64 encode → HTTP POST every 3s
         → Your AI pipeline
```

**Why offscreen?** Chrome MV3 kills popup contexts when you click away. The offscreen document runs independently, so capture continues while you use the meeting.

## Requirements

- Chrome 116+ (offscreen document support)
- A running HTTP endpoint to receive audio (default: `localhost:8900`)

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Button won't click | Reload extension on `chrome://extensions/`. MV3 requires external JS files |
| No audio arriving | Check your receiver is running. Extension POSTs to `/audio/browser` |
| Capture stops | Did you close Chrome? Offscreen doc dies with the browser |
| Wrong account | Extension runs in whatever Chrome profile it's installed in |
| Need to update | Remove extension entirely, then Load unpacked again (Chrome caches aggressively) |
