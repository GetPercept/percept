"""Tests for IntentParser — regex patterns, spoken numbers, LLM fallback."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.intent_parser import (
    IntentParser, ParseResult, parse_spoken_duration, _parse_spoken_number,
)


# --- Spoken number parsing ---

class TestSpokenNumbers:
    def test_basic_numbers(self):
        assert _parse_spoken_number("five") == 5
        assert _parse_spoken_number("twenty") == 20

    def test_compound_numbers(self):
        assert _parse_spoken_number("twenty five") == 25
        assert _parse_spoken_number("thirty two") == 32

    def test_digit_string(self):
        assert _parse_spoken_number("42") == 42

    def test_special(self):
        assert _parse_spoken_number("a") == 1
        assert _parse_spoken_number("an") == 1
        assert _parse_spoken_number("half") == 30

    def test_unknown(self):
        assert _parse_spoken_number("blorp") is None


class TestSpokenDuration:
    def test_thirty_minutes(self):
        assert parse_spoken_duration("thirty minutes") == 1800

    def test_five_hours(self):
        assert parse_spoken_duration("five hours") == 18000

    def test_digit_duration(self):
        assert parse_spoken_duration("2 hours") == 7200
        assert parse_spoken_duration("45 minutes") == 2700

    def test_half_an_hour(self):
        assert parse_spoken_duration("half an hour") == 1800

    def test_an_hour(self):
        assert parse_spoken_duration("an hour") == 3600

    def test_hour_and_a_half(self):
        result = parse_spoken_duration("an hour and a half")
        assert result == 5400

    def test_no_match(self):
        assert parse_spoken_duration("blah blah") is None

    def test_forty_five_minutes(self):
        assert parse_spoken_duration("forty five minutes") == 2700


# --- Regex intent parsing ---

# We need to mock the lazy receiver imports
@pytest.fixture(autouse=True)
def mock_receiver_helpers():
    """Mock the _lazy_receiver imports to avoid circular dependency."""
    mock_lookup = MagicMock(return_value=None)
    mock_normalize = MagicMock(side_effect=lambda x: x)
    mock_context = MagicMock(return_value="")
    with patch("src.intent_parser._lazy_receiver", return_value=(mock_lookup, mock_normalize, mock_context)):
        yield mock_lookup, mock_normalize


class TestEmailIntent:
    def test_basic_email(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("email alice about the meeting")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "email"

    def test_send_an_email(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("send an email to bob saying hello")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "email"


class TestTextIntent:
    def test_text_someone(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("text mom saying I'll be late")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "text"

    def test_tell_command(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("tell Bob that the meeting is cancelled")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "text"


class TestReminderIntent:
    def test_reminder_with_time(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("remind me in thirty minutes to call Bob")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "reminder"
        assert data.get("when_seconds") == 1800

    def test_reminder_simple(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("remind me to buy milk")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "reminder"
        assert "milk" in data["task"]

    def test_dont_forget(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("don't forget to send the report")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "reminder"


class TestSearchIntent:
    def test_search(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("search for best restaurants nearby")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "search"

    def test_look_up(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("look up the weather in San Francisco")
        assert "VOICE_ACTION" in result

    def test_who_is(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("who is Elon Musk")
        assert "VOICE_ACTION" in result


class TestOrderIntent:
    def test_order(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("order pizza from Dominos for delivery")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "order"

    def test_shopping_list(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("add milk to the shopping list")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "order"


class TestCalendarIntent:
    def test_schedule(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("schedule a meeting with John on Friday")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "calendar"

    def test_set_up_meeting(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("set up a meeting with Alice at 3pm")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "calendar"


class TestNoteIntent:
    def test_note(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("note that the deadline is Friday")
        assert "VOICE_ACTION" in result
        data = json.loads(result.split("VOICE_ACTION: ")[1])
        assert data["action"] == "note"

    def test_remember(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("remember the meeting is at 3pm")
        assert "VOICE_ACTION" in result

    def test_save_this(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("save this important info")
        assert "VOICE_ACTION" in result


class TestNoMatch:
    def test_unrecognized(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = parser.parse("the weather is nice today")
        assert result.startswith("VOICE:")


class TestParseResult:
    def test_to_voice_action(self):
        pr = ParseResult(intent="email", params={"to": "a@b.com"}, raw_text="test")
        va = pr.to_voice_action()
        data = json.loads(va.split("VOICE_ACTION: ")[1])
        assert data["action"] == "email"
        assert data["to"] == "a@b.com"


class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_llm_fallback_called(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=True)
        # Mock _try_llm to return a result
        mock_result = ParseResult(intent="email", params={"to": "test@test.com"}, raw_text="test", source="llm")
        with patch.object(parser, "_try_llm", new_callable=AsyncMock, return_value=mock_result):
            with patch.object(parser, "_save_to_db"):
                result = await parser.parse_async("ambiguous command here")
                assert "VOICE_ACTION" in result

    @pytest.mark.asyncio
    async def test_llm_disabled(self, mock_receiver_helpers):
        parser = IntentParser(llm_enabled=False)
        result = await parser.parse_async("ambiguous command here")
        assert result.startswith("VOICE:")
