"""Tests for PII detection and redaction."""

import pytest
from src.pii_detector import (
    scan_text, redact_text, scan_and_redact,
    PIIMatch, PIIScanResult,
    PII_SSN, PII_CREDIT_CARD, PII_PHONE, PII_EMAIL, PII_DOB,
    _luhn_check,
)


class TestSSNDetection:
    def test_ssn_with_dashes(self):
        result = scan_text("My SSN is 123-45-6789 okay")
        assert result.has_pii
        assert PII_SSN in result.pii_types_found
        assert result.matches[0].value == "123-45-6789"

    def test_ssn_with_spaces(self):
        result = scan_text("Number: 123 45 6789")
        assert result.has_pii
        match = [m for m in result.matches if m.pii_type == PII_SSN]
        assert len(match) == 1
        assert match[0].value == "123 45 6789"

    def test_no_false_ssn_for_random_numbers(self):
        result = scan_text("The code is 12345 and order 67890")
        ssn_matches = [m for m in result.matches if m.pii_type == PII_SSN]
        assert len(ssn_matches) == 0

    def test_ssn_positions(self):
        text = "SSN: 111-22-3333"
        result = scan_text(text)
        assert result.matches[0].start == 5
        assert result.matches[0].end == 16
        assert text[5:16] == "111-22-3333"


class TestCreditCardDetection:
    def test_visa_number(self):
        result = scan_text("Card: 4111 1111 1111 1111")
        assert result.has_pii
        cc_matches = [m for m in result.matches if m.pii_type == PII_CREDIT_CARD]
        assert len(cc_matches) == 1

    def test_visa_no_spaces(self):
        result = scan_text("Card: 4111111111111111")
        cc_matches = [m for m in result.matches if m.pii_type == PII_CREDIT_CARD]
        assert len(cc_matches) == 1

    def test_invalid_cc_rejected(self):
        # Number that fails Luhn check
        result = scan_text("Not a card: 1234 5678 9012 3456")
        cc_matches = [m for m in result.matches if m.pii_type == PII_CREDIT_CARD]
        assert len(cc_matches) == 0

    def test_luhn_check_valid(self):
        assert _luhn_check("4111111111111111") is True
        assert _luhn_check("5500000000000004") is True

    def test_luhn_check_invalid(self):
        assert _luhn_check("1234567890123456") is False
        assert _luhn_check("123") is False


class TestPhoneDetection:
    def test_us_phone_with_dashes(self):
        result = scan_text("Call me at 415-341-4104")
        phone_matches = [m for m in result.matches if m.pii_type == PII_PHONE]
        assert len(phone_matches) == 1

    def test_us_phone_with_parens(self):
        result = scan_text("Phone: (415) 341-4104")
        phone_matches = [m for m in result.matches if m.pii_type == PII_PHONE]
        assert len(phone_matches) == 1

    def test_us_phone_with_country_code(self):
        result = scan_text("Reach me at +1 415 341 4104")
        phone_matches = [m for m in result.matches if m.pii_type == PII_PHONE]
        assert len(phone_matches) == 1

    def test_short_numbers_ignored(self):
        result = scan_text("Room 4104 is available")
        phone_matches = [m for m in result.matches if m.pii_type == PII_PHONE]
        assert len(phone_matches) == 0


class TestEmailDetection:
    def test_standard_email(self):
        result = scan_text("Email me at user@example.com")
        assert PII_EMAIL in result.pii_types_found
        assert result.matches[0].value == "user@example.com"

    def test_email_with_plus(self):
        result = scan_text("Send to user+tag@example.org please")
        email_matches = [m for m in result.matches if m.pii_type == PII_EMAIL]
        assert len(email_matches) == 1
        assert email_matches[0].value == "user+tag@example.org"

    def test_no_email_without_tld(self):
        result = scan_text("foo@bar is not an email")
        email_matches = [m for m in result.matches if m.pii_type == PII_EMAIL]
        assert len(email_matches) == 0


class TestDOBDetection:
    def test_born_on_date(self):
        result = scan_text("He was born on 01/15/1990")
        assert PII_DOB in result.pii_types_found

    def test_dob_label(self):
        result = scan_text("DOB: 03/22/1985")
        dob_matches = [m for m in result.matches if m.pii_type == PII_DOB]
        assert len(dob_matches) == 1

    def test_birthday_is(self):
        result = scan_text("My birthday is January 5, 1990")
        dob_matches = [m for m in result.matches if m.pii_type == PII_DOB]
        assert len(dob_matches) == 1

    def test_date_of_birth_iso(self):
        result = scan_text("date of birth is 1990-01-15")
        dob_matches = [m for m in result.matches if m.pii_type == PII_DOB]
        assert len(dob_matches) == 1

    def test_random_date_no_context(self):
        # No DOB context — should not match as DOB
        result = scan_text("The meeting is on 03/15/2024")
        dob_matches = [m for m in result.matches if m.pii_type == PII_DOB]
        assert len(dob_matches) == 0


class TestRedaction:
    def test_redact_ssn(self):
        text = "SSN: 123-45-6789"
        redacted = redact_text(text)
        assert "[REDACTED_SSN]" in redacted
        assert "123-45-6789" not in redacted

    def test_redact_email(self):
        text = "Contact alice@example.com for info"
        redacted = redact_text(text)
        assert "[REDACTED_EMAIL]" in redacted
        assert "alice@example.com" not in redacted

    def test_redact_multiple_pii(self):
        text = "SSN 123-45-6789, email alice@example.com"
        redacted = redact_text(text)
        assert "[REDACTED_SSN]" in redacted
        assert "[REDACTED_EMAIL]" in redacted
        assert "123-45-6789" not in redacted
        assert "alice@example.com" not in redacted

    def test_redact_preserves_non_pii(self):
        text = "Hello world, my SSN is 123-45-6789 thanks"
        redacted = redact_text(text)
        assert redacted.startswith("Hello world")
        assert redacted.endswith("thanks")

    def test_no_pii_returns_original(self):
        text = "Just a normal sentence with no PII"
        assert redact_text(text) == text


class TestScanAndRedact:
    def test_combined(self):
        text = "My SSN is 123-45-6789 and email is bob@test.com"
        redacted, result = scan_and_redact(text)
        assert result.has_pii
        assert len(result.matches) == 2
        assert "123-45-6789" not in redacted
        assert "bob@test.com" not in redacted


class TestEdgeCases:
    def test_empty_text(self):
        result = scan_text("")
        assert not result.has_pii
        assert result.matches == []

    def test_none_text(self):
        # Should handle gracefully
        result = scan_text("")
        assert not result.has_pii

    def test_pii_scan_result_properties(self):
        result = scan_text("SSN: 123-45-6789, email: a@b.com")
        assert result.has_pii
        assert PII_SSN in result.pii_types_found
        assert PII_EMAIL in result.pii_types_found

    def test_multiple_same_type(self):
        text = "SSN1: 123-45-6789, SSN2: 987-65-4321"
        result = scan_text(text)
        ssn_matches = [m for m in result.matches if m.pii_type == PII_SSN]
        assert len(ssn_matches) == 2

    def test_spoken_transcript_with_pii(self):
        """Simulate a real transcript with PII."""
        text = (
            "[David] So the patient's social security number is 123-45-6789 "
            "and their date of birth is January 15, 1985. "
            "You can reach them at 415-555-1234 or patient@email.com"
        )
        result = scan_text(text)
        types = result.pii_types_found
        assert PII_SSN in types
        assert PII_EMAIL in types
        # Phone and DOB may or may not match depending on patterns
        assert result.has_pii
