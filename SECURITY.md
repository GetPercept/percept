# Security

Percept processes ambient audio — potentially every conversation in your office, home, or car. We treat this with the seriousness it deserves.

## Architecture: Local-First by Design

Audio never leaves your machine by default. The entire pipeline runs locally:

```
Microphone → Local transcription (faster-whisper) → Local CIL (SQLite) → Local agent (CLI/MCP)
```

No cloud APIs are called unless you explicitly configure them (e.g., NVIDIA Parakeet, Deepgram). No telemetry. No phone-home. The hosted API (when available) will be opt-in, not default.

## Threat Model

We defend against four categories of attack:

| Threat | Description | Mitigation |
|---|---|---|
| **Unauthorized voice commands** | Someone other than the device owner triggers actions via wake word | Speaker authorization allowlist |
| **Prompt injection via speech** | Attacker speaks crafted text to manipulate the intent parser or downstream LLM | Command safety classifier + pattern detection |
| **Data exfiltration** | Malicious command attempts to send credentials, API keys, or system info externally | 6-category safety classifier blocks exfil patterns |
| **Unauthorized API access** | External requests to the webhook or dashboard without credentials | Token-based webhook auth + dashboard password |

## Speaker Authorization

Percept maintains an allowlist of authorized speakers. When enabled, **only authorized speakers can trigger actions** — all other voices are logged but ignored.

```bash
# Authorize a speaker
percept speakers authorize SPEAKER_0

# Revoke access
percept speakers revoke SPEAKER_0

# List authorized speakers
percept speakers list
```

**How it works:**
- If no speakers are authorized, the allowlist is inactive (all speakers can trigger actions — useful during initial setup)
- Once the first speaker is authorized, the allowlist activates and all other speakers are blocked
- Omi's `is_user` flag (device owner) is treated as an additional authorization signal
- Blocked attempts are logged with timestamp, speaker ID, transcript snippet, and reason

## Command Safety Classifier

Every voice command passes through a safety classifier before execution. The classifier uses pattern matching across six categories:

| Category | Examples Blocked |
|---|---|
| **Exfiltration** | `curl credentials to evil.com`, `send API keys via webhook`, `upload .env to ngrok` |
| **Credential access** | `cat ~/.ssh/id_rsa`, `read /etc/passwd`, `dump environment variables` |
| **Network changes** | `modify sshd_config`, `open port 22`, `chmod 777 everything` |
| **Destructive commands** | `rm -rf /`, `dd if=/dev/zero of=/dev/sda`, `format disk` |
| **Info leaks** | `email hostname and system info to stranger@evil.com` |
| **Prompt injection** | Crafted speech attempting to override system prompts or extract context |

**False-positive protection:** Informational queries containing dangerous keywords are allowed. "Search for SSH tutorial" passes; "modify sshd_config to allow root login" is blocked.

**Pen test results:** 7 injection attempts tested, 7 blocked. Test categories: exfiltration, credential theft, network manipulation, destructive commands, info leaks, prompt override, and context extraction.

## Webhook Authentication

The receiver endpoint requires token-based authentication:

```
POST /webhook/transcript?token=<secret>
# or
Authorization: Bearer <secret>
```

- Requests without a valid token receive `401 Unauthorized`
- Failed auth attempts are logged to the security log
- The token is set via `percept config set webhook_secret <token>` or environment variable

## Dashboard Authentication

The dashboard (port 8960) is password-protected. Set via:

```bash
percept config set dashboard_password <password>
```

## Security Logging

All security events are persisted to the database and queryable via CLI:

```bash
# View recent security events
percept security-log

# Filter by type
percept security-log --reason unauthorized_speaker
percept security-log --reason invalid_webhook_auth
percept security-log --reason injection_detected
```

Each log entry includes:
- Timestamp
- Speaker ID (if applicable)
- Transcript snippet (truncated for privacy)
- Reason category
- Additional details

## Test Coverage

Security features are covered by 24 dedicated tests across two test suites:

- `test_command_safety.py` — 6 test classes covering safe commands, blocked commands, edge cases, parsed intent params, and empty input
- `test_speaker_auth.py` — 18 tests covering authorization, revocation, idempotency, webhook auth, and security logging

Total test suite: 216 tests passing.

## Data Storage

- **SQLite with WAL mode** — database file permissions are restricted to the owning user
- **No encryption at rest by default** — the database lives on your local filesystem with your OS-level permissions. If you need encryption at rest, use full-disk encryption (FileVault, LUKS)
- **FTS5 index** — full-text search indexes conversation content locally. No data is sent to external search services
- **LanceDB vector store** — embeddings stored locally. When using NVIDIA NIM for embedding generation, text is sent to NVIDIA's API; use local embeddings (offline fallback) to avoid this

## Responsible Disclosure

If you find a security vulnerability, please email **security@getpercept.ai** rather than opening a public issue. We'll acknowledge within 48 hours and aim to patch critical issues within 7 days.

## Recommendations for Users

1. **Enable speaker authorization** immediately after identifying your voice (`percept speakers authorize <your_id>`)
2. **Set a strong webhook secret** — don't use defaults
3. **Set a dashboard password** if the machine is network-accessible
4. **Use local transcription** (faster-whisper, the default) unless you specifically need cloud ASR accuracy
5. **Review the security log** periodically (`percept security-log`)
6. **Keep Percept updated** — `git pull && pip install -e .`
