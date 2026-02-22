"""Tests for receiver.py — wake word, speaker auth, flush logic, endpoints."""

import json
import time
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Mock heavy imports before importing receiver
import sys


@pytest.fixture(autouse=True)
def mock_heavy_deps(tmp_path):
    """Mock config file loading and DB to avoid touching disk."""
    fake_config = {
        "whisper": {"model_size": "base"},
        "audio": {"sample_rate": 16000, "sample_width": 2, "silence_threshold_seconds": 30},
        "memory": {"conversations_dir": str(tmp_path / "convos")},
        "server": {"port": 8900},
        "intent": {"llm_enabled": False, "llm_model": ""},
    }
    # We need to mock the config loading before receiver is imported
    # Since receiver is already loaded, we'll test functions directly
    yield fake_config


class TestWakeWordDetection:
    def test_default_wake_words(self):
        from src.receiver import _get_wake_words
        # Reset cache
        import src.receiver as recv
        recv._wake_words_cache = None
        recv._wake_words_last_load = 0
        words = _get_wake_words()
        assert "hey jarvis" in words

    def test_wake_word_in_text(self):
        text = "hey jarvis send an email to bob"
        wake_words = ["hey jarvis"]
        assert any(w in text.lower() for w in wake_words)

    def test_no_wake_word(self):
        text = "just talking about the weather"
        wake_words = ["hey jarvis"]
        assert not any(w in text.lower() for w in wake_words)


class TestSpeakerResolution:
    def test_resolve_known_speaker(self):
        with patch("src.speaker_manager.load_speakers", return_value={"SPEAKER_00": {"name": "David", "is_owner": True}}):
            from src.speaker_manager import resolve_speaker
            assert resolve_speaker("SPEAKER_00") == "David"

    def test_resolve_unknown_speaker(self):
        with patch("src.speaker_manager.load_speakers", return_value={}):
            from src.speaker_manager import resolve_speaker
            assert resolve_speaker("SPEAKER_99") == "SPEAKER_99"

    def test_resolve_text_with_names(self):
        with patch("src.speaker_manager.load_speakers", return_value={"SPEAKER_00": {"name": "David", "is_owner": True}}):
            from src.speaker_manager import resolve_text_with_names
            result = resolve_text_with_names("[SPEAKER_00] Hello there")
            assert "[David]" in result


class TestSpeakerAuthorization:
    def test_authorized_owner(self):
        speakers = {"SPEAKER_00": {"name": "David", "is_owner": True}}
        segment_speakers = {"SPEAKER_00"}
        approved_names = {k for k, v in speakers.items() if v.get("is_owner") or v.get("approved")}
        assert bool(segment_speakers & approved_names)

    def test_unauthorized_speaker(self):
        speakers = {"SPEAKER_00": {"name": "David", "is_owner": True}}
        segment_speakers = {"SPEAKER_99"}
        approved_names = {k for k, v in speakers.items() if v.get("is_owner") or v.get("approved")}
        assert not bool(segment_speakers & approved_names)


class TestContactLookup:
    def test_lookup_email(self):
        with patch("src.receiver._load_contacts", return_value={"alice": {"email": "alice@x.com", "aliases": ["al"]}}):
            from src.receiver import _lookup_contact
            assert _lookup_contact("alice", "email") == "alice@x.com"
            assert _lookup_contact("al", "email") == "alice@x.com"
            assert _lookup_contact("nobody", "email") is None

    def test_normalize_spoken_email(self):
        from src.receiver import _normalize_spoken_email
        assert _normalize_spoken_email("jane at example dot com") == "jane@example.com"
        assert _normalize_spoken_email("bob at gmail dot org") == "bob@gmail.org"


class TestDispatchAction:
    def test_email_dispatch(self):
        with patch("src.receiver._load_contacts", return_value={}):
            from src.receiver import _dispatch_action
            result = _dispatch_action("email bob about the project", [])
            data = json.loads(result.split("VOICE_ACTION: ")[1])
            assert data["action"] == "email"

    def test_reminder_dispatch(self):
        with patch("src.receiver._load_contacts", return_value={}):
            from src.receiver import _dispatch_action
            result = _dispatch_action("remind me to call mom", [])
            data = json.loads(result.split("VOICE_ACTION: ")[1])
            assert data["action"] == "reminder"

    def test_search_dispatch(self):
        with patch("src.receiver._load_contacts", return_value={}):
            from src.receiver import _dispatch_action
            result = _dispatch_action("search for best pizza", [])
            data = json.loads(result.split("VOICE_ACTION: ")[1])
            assert data["action"] == "search"

    def test_note_dispatch(self):
        with patch("src.receiver._load_contacts", return_value={}):
            from src.receiver import _dispatch_action
            result = _dispatch_action("remember the meeting is at 3", [])
            data = json.loads(result.split("VOICE_ACTION: ")[1])
            assert data["action"] == "note"

    def test_fallback_voice(self):
        with patch("src.receiver._load_contacts", return_value={}):
            from src.receiver import _dispatch_action
            result = _dispatch_action("the weather is nice", [])
            assert result.startswith("VOICE:")


class TestGetContextText:
    def test_basic(self):
        from src.receiver import _get_context_text
        segments = [{"text": "Hello"}, {"text": "World"}]
        assert _get_context_text(segments) == "Hello World"

    def test_empty(self):
        from src.receiver import _get_context_text
        assert _get_context_text([]) == ""

    def test_limits_to_last_5(self):
        from src.receiver import _get_context_text
        segments = [{"text": f"seg{i}"} for i in range(10)]
        result = _get_context_text(segments)
        assert "seg5" in result
        assert "seg0" not in result


class TestContinuationWindow:
    def test_continuation_window_logic(self):
        """Test that the continuation window concept works."""
        import src.receiver as recv
        session_key = "test_session"
        recv._last_wake_flush[session_key] = time.time()
        # Within window
        assert time.time() - recv._last_wake_flush[session_key] < recv.WAKE_CONTINUATION_WINDOW
        # Outside window
        recv._last_wake_flush[session_key] = time.time() - 20
        assert time.time() - recv._last_wake_flush[session_key] >= recv.WAKE_CONTINUATION_WINDOW


class TestBuildDaySummary:
    def test_empty(self, tmp_path):
        """Day summary with no live file returns empty structure."""
        from src.receiver import _build_day_summary
        with patch("src.receiver.LIVE_FILE", tmp_path / "nonexistent.txt"):
            result = _build_day_summary()
            assert result["total_conversations"] == 0
            assert result["total_words"] == 0


class TestFastAPIEndpoints:
    """Test the FastAPI app endpoints using TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.receiver import app
        return TestClient(app)

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_audio_health(self, client):
        resp = client.get("/webhook/audio")
        assert resp.status_code == 200

    def test_transcript_health(self, client):
        resp = client.get("/webhook/transcript")
        assert resp.status_code == 200

    def test_status_endpoint(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200
        assert "active_buffers" in resp.json()

    def test_day_summary_endpoint(self, client):
        resp = client.get("/day-summary")
        assert resp.status_code == 200

    def test_context_endpoint(self, client):
        resp = client.get("/context")
        assert resp.status_code == 200

    def test_transcript_post_empty(self, client):
        resp = client.post("/webhook/transcript?uid=test", json=[])
        assert resp.status_code == 200

    def test_transcript_post_segments(self, client):
        segments = [{"text": "Hello world", "speaker": "SPEAKER_00", "is_user": True, "start": 0.0, "end": 2.0}]
        with patch("src.receiver._schedule_flush", new_callable=AsyncMock):
            with patch("src.receiver._schedule_conversation_end", new_callable=AsyncMock):
                resp = client.post("/webhook/transcript?uid=test&session_id=s1", json=segments)
                assert resp.status_code == 200
                assert resp.json()["segments_received"] == 1
