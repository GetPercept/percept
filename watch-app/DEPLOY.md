# Percept Watch App — Deployment Guide

## Prerequisites

- **Xcode 16+** installed (currently using Xcode 26.2)
- **Apple Developer Account** signed in to Xcode (david@caretech360.com, Individual)
- **iPhone** paired with your Apple Watch, connected to Mac via USB or WiFi
- **Apple Watch** paired with the iPhone (watchOS 10.0+)
- **Percept server** running and accessible at `https://percept.clawdoor.com`

## Architecture

The Watch app has two deployment paths for audio:

1. **Direct upload** (preferred) — Watch sends audio chunks directly to `https://percept.clawdoor.com/audio` over WiFi/cellular
2. **iPhone relay** — Watch sends audio to iPhone companion app via WatchConnectivity, iPhone forwards to server

The app automatically picks the best path: direct upload when the Watch has internet, iPhone relay when it's nearby.

## Step-by-Step Deployment

### 1. Open the Project in Xcode

```bash
open /Users/jarvis/.openclaw/workspace/percept/watch-app/PerceptWatch.xcodeproj
```

### 2. Set Up Signing

1. Select the **PerceptWatch** project in the navigator
2. Select the **PerceptWatch** target
3. Go to **Signing & Capabilities**
4. Check **"Automatically manage signing"**
5. Select **Team**: "David Emanuel" (david@caretech360.com)
6. Repeat for the **PerceptCompanion** target
7. Xcode will create provisioning profiles automatically

> **Note:** With a free Individual account, apps expire after **7 days**. You'll need to re-deploy weekly. A paid $99/year account removes this limit.

### 3. Connect Your Devices

1. Connect iPhone to Mac via **USB cable**
2. On iPhone: Trust this computer when prompted
3. Apple Watch should appear automatically since it's paired with the iPhone

### 4. Select the Watch as Destination

1. In Xcode's toolbar, click the **destination selector** (next to the scheme)
2. Select your **Apple Watch** under "Devices"
3. If it doesn't appear, go to **Window → Devices and Simulators** and check it's detected

### 5. Build and Run

1. Select the **PerceptWatch** scheme
2. Press **⌘R** (Run)
3. First install takes 1-2 minutes
4. The app will appear on your Watch

### 6. Grant Permissions

On first launch, the Watch will ask for **microphone permission** — tap Allow.

## Usage

- **Quick tap** the mic button: Toggle continuous recording on/off
- **Long press** (hold): Walkie-talkie mode — records while holding, sends on release
- Audio is streamed as 1-second PCM16 chunks to the Percept server

## Configuration

The default server URL is `https://percept.clawdoor.com/audio`. To change it:

1. Open the iPhone **Percept Companion** app
2. Go to Settings
3. Update the Webhook URL

Settings sync to the Watch via WatchConnectivity.

## Bundle Identifiers

- **iPhone Companion**: `com.percept.companion`
- **Watch App**: `com.percept.companion.watchkitapp`
- **App Group**: `group.com.percept.watch`

## Troubleshooting

### "Untrusted Developer" on Watch
Go to Watch **Settings → General → Device Management** → Trust the developer profile.

### Watch not appearing in Xcode
1. Make sure iPhone is connected via USB
2. On iPhone: Settings → Developer → ensure it's enabled
3. Restart Xcode
4. Check **Window → Devices and Simulators**

### Build fails with signing errors
1. Ensure you're signed in: **Xcode → Settings → Accounts**
2. Delete old provisioning profiles: `~/Library/MobileDevice/Provisioning Profiles/`
3. Clean build: **Product → Clean Build Folder** (⇧⌘K)

### Audio not reaching server
1. Check Watch has WiFi or cellular connectivity
2. Verify `https://percept.clawdoor.com` is accessible
3. Check the Cloudflare tunnel is running on the Mac Mini
4. If Watch is WiFi-only, ensure iPhone companion app is running as fallback relay

### App expired (7-day limit)
Re-deploy from Xcode. This is a free account limitation.

### "No space on device"
Delete unused apps from the Watch to free space. Watch apps are limited to ~50MB.
