"""PII detection and redaction for Percept transcripts.

Regex-based detection for common PII types: SSN, credit card numbers,
phone numbers, email addresses, and dates of birth.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# PII type constants
PII_SSN = "SSN"
PII_CREDIT_CARD = "CREDIT_CARD"
PII_PHONE = "PHONE"
PII_EMAIL = "EMAIL"
PII_DOB = "DOB"

# Redaction labels
REDACT_MAP = {
    PII_SSN: "[REDACTED_SSN]",
    PII_CREDIT_CARD: "[REDACTED_CC]",
    PII_PHONE: "[REDACTED_PHONE]",
    PII_EMAIL: "[REDACTED_EMAIL]",
    PII_DOB: "[REDACTED_DOB]",
}


@dataclass
class PIIMatch:
    """A single PII detection result."""
    pii_type: str
    value: str
    start: int
    end: int
    confidence: float = 1.0  # 0-1, regex matches are high confidence


@dataclass
class PIIScanResult:
    """Result of scanning text for PII."""
    text: str
    matches: List[PIIMatch] = field(default_factory=list)
    
    @property
    def has_pii(self) -> bool:
        return len(self.matches) > 0
    
    @property
    def pii_types_found(self) -> set:
        return {m.pii_type for m in self.matches}


# Compiled regex patterns
# SSN: 123-45-6789 or 123 45 6789 (not 9 digits with no separators to reduce false positives)
_SSN_PATTERN = re.compile(
    r'\b(\d{3}[-\s]\d{2}[-\s]\d{4})\b'
)

# Credit card: 13-19 digits, optionally separated by spaces or dashes
# Covers Visa, MC, Amex, Discover
_CC_PATTERN = re.compile(
    r'\b(\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,7})\b'
)

# Phone: various US formats
# (123) 456-7890, 123-456-7890, +1 123 456 7890, etc.
_PHONE_PATTERN = re.compile(
    r'(?<!\d)'  # no digit before
    r'(\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})'
    r'(?!\d)'  # no digit after
)

# Email: standard email pattern
_EMAIL_PATTERN = re.compile(
    r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'
)

# Date of birth: spoken and written formats
# "born on January 15, 1990", "DOB: 01/15/1990", "date of birth is 1990-01-15"
_DOB_CONTEXT_PATTERN = re.compile(
    r'(?:born\s+(?:on\s+)?|date\s+of\s+birth\s*(?:is\s*)?|dob\s*[:=]\s*|birthday\s*(?:is\s*)?)'
    r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|'
    r'(?:january|february|march|april|may|june|july|august|september|october|november|december)'
    r'\s+\d{1,2},?\s*\d{2,4}|'
    r'\d{4}[/\-]\d{1,2}[/\-]\d{1,2})',
    re.IGNORECASE
)

# Standalone date patterns that look like DOB (with year in plausible range)
_DATE_PATTERN = re.compile(
    r'\b(\d{1,2}[/\-]\d{1,2}[/\-](?:19|20)\d{2})\b'
)


def _luhn_check(number: str) -> bool:
    """Validate credit card number using Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def scan_text(text: str) -> PIIScanResult:
    """Scan text for PII and return all matches with positions.
    
    Args:
        text: The transcript text to scan.
        
    Returns:
        PIIScanResult with all detected PII matches.
    """
    if not text:
        return PIIScanResult(text=text)
    
    matches: List[PIIMatch] = []
    
    # SSN detection
    for m in _SSN_PATTERN.finditer(text):
        matches.append(PIIMatch(
            pii_type=PII_SSN,
            value=m.group(1),
            start=m.start(1),
            end=m.end(1),
        ))
    
    # Credit card detection (validate with Luhn)
    for m in _CC_PATTERN.finditer(text):
        raw = m.group(1)
        digits_only = re.sub(r'[-\s]', '', raw)
        if len(digits_only) >= 13 and _luhn_check(digits_only):
            matches.append(PIIMatch(
                pii_type=PII_CREDIT_CARD,
                value=raw,
                start=m.start(1),
                end=m.end(1),
            ))
    
    # Phone detection
    for m in _PHONE_PATTERN.finditer(text):
        raw = m.group(1)
        digits_only = re.sub(r'[^\d]', '', raw)
        # Must have 10-11 digits to be a valid US phone
        if 10 <= len(digits_only) <= 11:
            matches.append(PIIMatch(
                pii_type=PII_PHONE,
                value=raw,
                start=m.start(1),
                end=m.end(1),
                confidence=0.8,  # phone numbers can be false positives
            ))
    
    # Email detection
    for m in _EMAIL_PATTERN.finditer(text):
        matches.append(PIIMatch(
            pii_type=PII_EMAIL,
            value=m.group(1),
            start=m.start(1),
            end=m.end(1),
        ))
    
    # Date of birth detection (context-dependent)
    for m in _DOB_CONTEXT_PATTERN.finditer(text):
        matches.append(PIIMatch(
            pii_type=PII_DOB,
            value=m.group(1),
            start=m.start(1),
            end=m.end(1),
        ))
    
    # Sort by position
    matches.sort(key=lambda x: x.start)
    
    return PIIScanResult(text=text, matches=matches)


def redact_text(text: str, scan_result: Optional[PIIScanResult] = None) -> str:
    """Replace detected PII with redaction labels.
    
    Args:
        text: Original text.
        scan_result: Pre-computed scan result. If None, text is scanned first.
        
    Returns:
        Text with PII replaced by redaction labels.
    """
    if scan_result is None:
        scan_result = scan_text(text)
    
    if not scan_result.has_pii:
        return text
    
    # Replace from end to start to preserve positions
    result = text
    for match in reversed(scan_result.matches):
        label = REDACT_MAP.get(match.pii_type, "[REDACTED]")
        result = result[:match.start] + label + result[match.end:]
    
    return result


def scan_and_redact(text: str) -> tuple:
    """Convenience: scan and redact in one call.
    
    Returns:
        (redacted_text, scan_result)
    """
    result = scan_text(text)
    redacted = redact_text(text, result)
    return redacted, result
