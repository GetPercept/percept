# Percept Watch — Walkie-Talkie Audio Relay for AI Agents

Push-to-talk on Apple Watch → iPhone → Percept AI endpoint.

## Architecture

```
┌─────────────────┐    WatchConnectivity    ┌──────────────────┐     HTTP POST      ┌─────────────┐
│   Apple Watch    │ ──────────────────────► │   iPhone App     │ ──────────────────► │  Percept    │
│                  │   PCM16 chunks (1s)     │                  │   multipart/form   │  API        │
│  • Push-to-talk  │   sendMessageData /     │  • Audio relay   │   audio + metadata │             │
│  • Raise-to-speak│   transferFile          │  • Settings UI   │                    │  receiver.py│
│  • Complication  │                         │  • Webhook config│                    │  :8900      │
└─────────────────┘                         └──────────────────┘                    └─────────────┘
```

## Audio Format

| Parameter   | Value          |
|-------------|----------------|
| Encoding    | PCM16 (Int16)  |
| Sample Rate | 16,000 Hz      |
| Channels    | 1 (mono)       |
| Chunk Size  | 1 second       |
| Bytes/Chunk | 32,000         |

## Trigger Modes

1. **Tap & Hold** — Press and hold the big red button on Watch. Release to send.
2. **Raise to Speak** — Raise wrist to mouth (detected via CoreMotion). Auto-starts recording.
3. **Complication** — Tap the watch face complication to launch app and record.

## Setup

### Prerequisites
- Xcode 15+
- Apple Watch paired with iPhone
- Apple Developer account (for device deployment)
- `xcodegen` (`brew install xcodegen`)

### Build

```bash
cd percept/watch-app
./setup-xcode.sh          # Generates .xcodeproj
open PerceptWatch.xcodeproj
```

In Xcode:
1. Select your team under Signing & Capabilities for both targets
2. Add App Group `group.com.percept.watch` to both targets
3. Build scheme `PerceptWatch` → deploy to paired Apple Watch
4. Build scheme `PerceptCompanion` → deploy to iPhone

### Configure

In the iPhone companion app:
- **Webhook URL**: Where audio chunks are POSTed (default: `http://localhost:8900/audio`)
- **Auth Token**: Bearer token for Percept API
- **Trigger Modes**: Enable/disable each mode

## API

Each audio chunk is POSTed as `multipart/form-data`:

**Part 1: `metadata`** (application/json)
```json
{
  "timestamp": 1708384200.123,
  "duration": 1.0,
  "deviceId": "A1B2C3D4-...",
  "sampleRate": 16000,
  "channels": 1,
  "encoding": "pcm16",
  "sequenceNumber": 0,
  "sessionId": "E5F6G7H8-..."
}
```

**Part 2: `audio`** (application/octet-stream)
Raw PCM16 bytes, 32KB per 1-second chunk.

## Project Structure

```
watch-app/
├── Shared/                     # Shared between Watch & iPhone
│   ├── AudioConfig.swift       # Audio format constants
│   ├── AudioUploader.swift     # HTTP upload to webhook
│   ├── PerceptSettings.swift   # UserDefaults-backed config
│   └── WatchConnectivityManager.swift  # WCSession wrapper
├── PerceptWatch/               # watchOS app
│   ├── PerceptWatchApp.swift   # App entry point
│   ├── RecordingView.swift     # Main UI (push-to-talk button)
│   ├── AudioRecorder.swift     # AVAudioEngine capture
│   ├── WaveformView.swift      # Recording animation
│   ├── RaiseToSpeakDetector.swift  # CoreMotion gesture detection
│   └── PerceptComplication.swift   # Watch face complication
├── PerceptCompanion/           # iOS companion app
│   ├── PerceptCompanionApp.swift   # App entry point
│   ├── CompanionView.swift     # Main UI (status dashboard)
│   ├── SettingsView.swift      # Configuration screen
│   └── AudioRelayService.swift # Watch→API audio forwarding
├── project.yml                 # xcodegen project definition
├── setup-xcode.sh              # One-command project setup
└── README.md
```

## TODO (Stretch Goals)

- [ ] **Apple Health integration** — Attach heart rate data to audio chunks for context
- [ ] **Siri Shortcut** — "Hey Siri, tell Jarvis..." triggers recording
- [ ] **Background workout audio** — Extended recording during workout sessions
- [ ] **On-device VAD** — Voice Activity Detection to auto-trim silence
- [ ] **Response playback** — Play agent's audio response on Watch speaker
