"""Command safety classifier — blocks dangerous voice commands via pattern matching."""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dangerous patterns
# ---------------------------------------------------------------------------

# Exfiltration: curl/wget/fetch to external URLs
_EXFIL_PATTERNS = [
    r'\b(curl|wget|fetch|httpie|http)\b.*\b(https?://(?!localhost|127\.0\.0\.1|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01]))\S+)',
    r'\bsend\b.*\b(credentials?|api.?keys?|secrets?|tokens?|passwords?)\b.*\b(to|via|through)\b',
    r'\b(upload|post|push|exfiltrate)\b.*\b(credentials?|api.?keys?|secrets?|env|\.env)\b',
    r'\b(curl|wget|fetch)\b.*\b(webhook|ngrok|requestbin|pipedream|burp)',
]

# Credential/secret access
_CRED_PATTERNS = [
    r'\bread\b.*\b(\.env|\.aws|credentials|api.?key|secret|token|password)\b',
    r'\bcat\b.*\b(\.env|/etc/passwd|/etc/shadow|\.ssh/|id_rsa|\.aws/credentials)',
    r'\bprint\b.*\b(env|environ|os\.environ|api.?key|secret)',
    r'\b(show|display|list|dump|echo)\b.*\b(\$\w*PASSWORD|\$\w*SECRET|\$\w*KEY|\$\w*TOKEN)',
    r'\benv\b.*\bvars?\b.*\b(send|email|text|post)\b',
    r'\b(api.?key|secret.?key|access.?token|private.?key)\b.*\b(send|email|text|post|curl)\b',
    r'\b(send|email|text|post)\b.*\b(api.?keys?|credentials?|secrets?)\b',
    r'\b(dump|export)\b.*\b(env|environ|variables?|credentials?)\b.*\b(send|email|text|post)\b',
    r'\bcat\b.*\.env\b',
    r'\bread\b.*/etc/(passwd|shadow)\b',
    r'\bcat\b.*(id_rsa|\.ssh)',
]

# SSH/network config changes
_NETWORK_PATTERNS = [
    r'\b(sshd_config|authorized_keys)\b',
    r'\b(modify|change|edit|add|write|append)\b.*\b(sshd|sshd_config|authorized_keys)\b',
    r'\b(open|enable|allow|expose)\b.*\bport\b',
    r'\b(iptables|ufw|firewall)\b.*\b(disable|allow|open|delete|flush)\b',
    r'\bchmod\s+777\b',
    r'\b(netcat|nc|ncat)\b.*\b(-l|listen)\b',
    r'\breverse.?shell\b',
]

# Destructive system commands
_DESTRUCTIVE_PATTERNS = [
    r'\brm\s+(-rf?|--recursive)\s+/',
    r'\brm\s+-rf?\s+~',
    r'\bdd\b.*\bif=.*\bof=\s*/dev/',
    r'\bmkfs\b',
    r'\bformat\b.*\b(disk|drive|volume|partition)\b',
    r'\b(shutdown|reboot|halt|poweroff)\b',
    r'\bkill\s+-9\s+1\b',
    r'\b:\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:',  # fork bomb
]

# Sending system info externally
_INFO_LEAK_PATTERNS = [
    r'\b(email|text|send|message)\b.*\b(system.?info|hostname|ifconfig|ip.?addr|whoami|uname)\b',
    r'\b(whoami|hostname|ifconfig|ip\s+addr)\b.*\b(email|text|send|curl|post)\b',
]

# Combined for efficiency
_ALL_DANGEROUS = (
    [("exfiltration", p) for p in _EXFIL_PATTERNS] +
    [("credential_access", p) for p in _CRED_PATTERNS] +
    [("network_change", p) for p in _NETWORK_PATTERNS] +
    [("destructive_command", p) for p in _DESTRUCTIVE_PATTERNS] +
    [("info_leak", p) for p in _INFO_LEAK_PATTERNS]
)

# False-positive safeguards: legitimate queries that contain dangerous keywords
_SAFE_CONTEXT_PATTERNS = [
    r'\b(search|look\s+up|research|what\s+is|tutorial|learn|how\s+to|article|guide)\b',
    r'\b(definition|explain|meaning)\b',
]


@dataclass
class SafetyResult:
    level: str  # "safe", "needs_confirmation", "blocked"
    reason: str = ""
    category: str = ""
    matched_pattern: str = ""


def classify_command_safety(transcript: str, parsed_intent: dict = None) -> SafetyResult:
    """Classify a voice command's safety level.
    
    Args:
        transcript: Raw transcript text
        parsed_intent: Parsed intent dict (action, params, etc.)
    
    Returns:
        SafetyResult with level, reason, and category
    """
    text = transcript.lower().strip()
    
    # Also check parsed intent params
    params_text = ""
    if parsed_intent:
        params_text = " ".join(str(v) for v in parsed_intent.values()).lower()
    
    combined = f"{text} {params_text}"
    
    # First check if this is clearly a safe/informational query
    is_informational = any(re.search(p, text) for p in _SAFE_CONTEXT_PATTERNS)
    
    # Check against all dangerous patterns
    for category, pattern in _ALL_DANGEROUS:
        try:
            if re.search(pattern, combined, re.IGNORECASE):
                # If it's an informational query, only block exfiltration and destructive
                if is_informational and category not in ("exfiltration", "destructive_command"):
                    continue
                
                return SafetyResult(
                    level="blocked",
                    reason=f"Dangerous command detected: {category}",
                    category=category,
                    matched_pattern=pattern[:100],
                )
        except re.error:
            continue
    
    return SafetyResult(level="safe")
