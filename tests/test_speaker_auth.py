"""Tests for the Speaker Authorization Gate and webhook authentication."""

import json
import time
import pytest


class TestSpeakerAuthorizationDB:
    """Test DB-level authorized speaker management."""

    def test_no_authorized_speakers_allows_all(self, db):
        """Backward compat: no allowlist configured = all allowed."""
        assert not db.has_authorized_speakers()

    def test_authorize_speaker(self, db):
        db.authorize_speaker("SPEAKER_00")
        assert db.has_authorized_speakers()
        assert db.is_speaker_authorized("SPEAKER_00")

    def test_unauthorized_speaker_blocked(self, db):
        db.authorize_speaker("SPEAKER_00")
        assert not db.is_speaker_authorized("SPEAKER_01")

    def test_unknown_speaker_blocked(self, db):
        db.authorize_speaker("SPEAKER_00")
        assert not db.is_speaker_authorized("SPEAKER_99")

    def test_revoke_speaker(self, db):
        db.authorize_speaker("SPEAKER_00")
        assert db.is_speaker_authorized("SPEAKER_00")
        assert db.revoke_speaker("SPEAKER_00")
        assert not db.is_speaker_authorized("SPEAKER_00")

    def test_revoke_nonexistent(self, db):
        assert not db.revoke_speaker("SPEAKER_99")

    def test_list_authorized_speakers(self, db):
        db.authorize_speaker("SPEAKER_00")
        db.authorize_speaker("SPEAKER_01")
        authorized = db.get_authorized_speakers()
        assert len(authorized) == 2
        ids = {s["speaker_id"] for s in authorized}
        assert ids == {"SPEAKER_00", "SPEAKER_01"}

    def test_authorize_idempotent(self, db):
        db.authorize_speaker("SPEAKER_00")
        db.authorize_speaker("SPEAKER_00")  # Should not fail
        authorized = db.get_authorized_speakers()
        assert len(authorized) == 1

    def test_backward_compat_no_config(self, db):
        """When no speakers authorized, has_authorized_speakers returns False."""
        assert not db.has_authorized_speakers()
        # Authorize then revoke all
        db.authorize_speaker("SPEAKER_00")
        assert db.has_authorized_speakers()
        db.revoke_speaker("SPEAKER_00")
        assert not db.has_authorized_speakers()


class TestSecurityLog:
    """Test security event logging."""

    def test_log_unauthorized_speaker(self, db):
        db.log_security_event("SPEAKER_01", "hey jarvis do something", "unauthorized_speaker")
        events = db.get_security_log()
        assert len(events) == 1
        assert events[0]["reason"] == "unauthorized_speaker"
        assert events[0]["speaker_id"] == "SPEAKER_01"
        assert "hey jarvis" in events[0]["transcript_snippet"]

    def test_log_invalid_webhook_auth(self, db):
        db.log_security_event("unknown", "uid=test", "invalid_webhook_auth", "Missing header")
        events = db.get_security_log(reason="invalid_webhook_auth")
        assert len(events) == 1

    def test_log_filter_by_reason(self, db):
        db.log_security_event("SPEAKER_01", "text1", "unauthorized_speaker")
        db.log_security_event("unknown", "text2", "invalid_webhook_auth")
        assert len(db.get_security_log(reason="unauthorized_speaker")) == 1
        assert len(db.get_security_log(reason="invalid_webhook_auth")) == 1
        assert len(db.get_security_log()) == 2

    def test_log_truncates_long_snippet(self, db):
        long_text = "x" * 1000
        db.log_security_event("SPEAKER_01", long_text, "unauthorized_speaker")
        events = db.get_security_log()
        assert len(events[0]["transcript_snippet"]) <= 500


class TestWebhookAuth:
    """Test webhook authentication logic."""

    @pytest.fixture
    def app_client(self, db, monkeypatch):
        """Create test client with mocked DB."""
        # Patch the module-level _db in receiver
        import src.receiver as receiver_mod
        monkeypatch.setattr(receiver_mod, "_db", db)
        
        from fastapi.testclient import TestClient
        return TestClient(receiver_mod.app)

    def test_no_secret_allows_all(self, app_client, db):
        """No webhook_secret configured = accept all requests."""
        resp = app_client.get("/webhook/transcript")
        assert resp.status_code == 200

    def test_valid_bearer_token(self, app_client, db):
        db.set_setting("webhook_secret", "mysecret123")
        resp = app_client.post(
            "/webhook/transcript?session_id=test&uid=test",
            json=[{"text": "hello", "speaker": "SPEAKER_00", "start": 0, "end": 1}],
            headers={"Authorization": "Bearer mysecret123"},
        )
        assert resp.status_code == 200

    def test_invalid_bearer_token_rejected(self, app_client, db):
        db.set_setting("webhook_secret", "mysecret123")
        resp = app_client.post(
            "/webhook/transcript?session_id=test&uid=test",
            json=[{"text": "hello", "speaker": "SPEAKER_00", "start": 0, "end": 1}],
            headers={"Authorization": "Bearer wrongtoken"},
        )
        assert resp.status_code == 401

    def test_missing_auth_header_rejected(self, app_client, db):
        db.set_setting("webhook_secret", "mysecret123")
        resp = app_client.post(
            "/webhook/transcript?session_id=test&uid=test",
            json=[{"text": "hello", "speaker": "SPEAKER_00", "start": 0, "end": 1}],
        )
        assert resp.status_code == 401

    def test_rejected_request_logged(self, app_client, db):
        db.set_setting("webhook_secret", "mysecret123")
        app_client.post(
            "/webhook/transcript?uid=attacker",
            json=[{"text": "hello"}],
        )
        events = db.get_security_log(reason="invalid_webhook_auth")
        assert len(events) == 1
        assert "attacker" in events[0]["transcript_snippet"]
