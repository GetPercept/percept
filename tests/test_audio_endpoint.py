"""Tests for /audio endpoint, audio buffer, and PCM16 transcription."""

import asyncio
import json
import struct
import time
import pytest
import numpy as np
from unittest.mock import patch, AsyncMock, MagicMock

from src.audio_transcriber import pcm16_to_float32, TranscriptionResult
from src.audio_buffer import AudioBufferManager, SILENCE_TIMEOUT, MAX_BUFFER_DURATION, BYTES_PER_SECOND


# --- PCM16 conversion tests ---

class TestPCM16ToFloat32:
    def test_empty_bytes(self):
        result = pcm16_to_float32(b"")
        assert len(result) == 0
        assert result.dtype == np.float32

    def test_silence(self):
        # 1 second of silence (all zeros)
        pcm = b"\x00\x00" * 16000
        result = pcm16_to_float32(pcm)
        assert len(result) == 16000
        assert np.all(result == 0.0)

    def test_max_positive(self):
        # int16 max = 32767
        pcm = struct.pack("<h", 32767)
        result = pcm16_to_float32(pcm)
        assert len(result) == 1
        assert abs(result[0] - (32767 / 32768.0)) < 1e-5

    def test_max_negative(self):
        pcm = struct.pack("<h", -32768)
        result = pcm16_to_float32(pcm)
        assert result[0] == -1.0

    def test_round_trip_shape(self):
        # 0.5 seconds at 16kHz
        n_samples = 8000
        pcm = struct.pack(f"<{n_samples}h", *([1000] * n_samples))
        result = pcm16_to_float32(pcm)
        assert result.shape == (n_samples,)
        assert result.dtype == np.float32


# --- Audio buffer tests ---

class TestAudioBufferManager:
    @pytest.fixture
    def callback(self):
        return AsyncMock()

    @pytest.fixture
    def manager(self, callback):
        return AudioBufferManager(on_complete=callback)

    @pytest.mark.asyncio
    async def test_single_chunk_flushes_after_silence(self, manager, callback):
        audio = b"\x00\x01" * 16000  # 1 second
        await manager.add_chunk("sess1", 0, audio)
        assert manager.active_sessions == 1

        # Wait for silence timeout + margin
        await asyncio.sleep(SILENCE_TIMEOUT + 0.5)
        callback.assert_awaited_once()
        args = callback.call_args[0]
        assert args[0] == "sess1"
        assert args[1] == audio

    @pytest.mark.asyncio
    async def test_multiple_chunks_ordered(self, manager, callback):
        c0 = b"\x00" * 100
        c1 = b"\x01" * 100
        c2 = b"\x02" * 100
        # Add out of order
        await manager.add_chunk("sess2", 2, c2)
        await manager.add_chunk("sess2", 0, c0)
        await manager.add_chunk("sess2", 1, c1)

        await asyncio.sleep(SILENCE_TIMEOUT + 0.5)
        callback.assert_awaited_once()
        combined = callback.call_args[0][1]
        assert combined == c0 + c1 + c2  # ordered by sequence number

    @pytest.mark.asyncio
    async def test_silence_timer_resets(self, manager, callback):
        await manager.add_chunk("sess3", 0, b"\x00" * 100)
        await asyncio.sleep(SILENCE_TIMEOUT - 1)
        # Add another chunk before timeout
        await manager.add_chunk("sess3", 1, b"\x01" * 100)
        await asyncio.sleep(SILENCE_TIMEOUT - 1)
        # Should NOT have flushed yet
        callback.assert_not_awaited()
        # Now wait for full timeout
        await asyncio.sleep(1.5)
        callback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_max_buffer_forces_flush(self, manager, callback):
        # Fill to max buffer
        chunk_size = BYTES_PER_SECOND * 10  # 10 seconds per chunk
        for i in range(4):  # 40 seconds > MAX_BUFFER_DURATION (30s)
            await manager.add_chunk("sess4", i, b"\x00" * chunk_size)
            if callback.await_count > 0:
                break

        # Should have flushed due to max buffer
        assert callback.await_count >= 1


# --- Endpoint integration tests ---

class TestAudioEndpoint:
    @pytest.fixture
    def client(self, db, monkeypatch):
        """Create test client with mocked auth (uses in-memory DB)."""
        from fastapi.testclient import TestClient
        import src.receiver as receiver_mod
        # Use in-memory DB so we don't corrupt production settings
        monkeypatch.setattr(receiver_mod, "_db", db)
        db.set_setting("webhook_secret", "test-token-123")
        return TestClient(receiver_mod.app)

    def _make_multipart(self, session_id="s1", seq=0, audio_bytes=None, token="test-token-123"):
        if audio_bytes is None:
            audio_bytes = b"\x00\x01" * 16000
        metadata = json.dumps({
            "sessionId": session_id,
            "sequenceNumber": seq,
            "sampleRate": 16000,
            "channels": 1,
            "encoding": "pcm16",
            "duration": 1.0,
            "deviceId": "watch-test",
            "timestamp": time.time(),
        })
        files = {
            "metadata": ("metadata.json", metadata, "application/json"),
            "audio": ("audio.raw", audio_bytes, "application/octet-stream"),
        }
        return files, token

    def test_auth_rejected_without_token(self, client):
        files, _ = self._make_multipart()
        resp = client.post("/audio", files=files)
        assert resp.status_code == 401

    def test_auth_accepted_with_query_token(self, client):
        files, token = self._make_multipart()
        resp = client.post(f"/audio?token={token}", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert data["sessionId"] == "s1"
        assert data["sequenceNumber"] == 0

    def test_auth_accepted_with_bearer_header(self, client):
        files, token = self._make_multipart()
        resp = client.post("/audio", files=files, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_missing_audio_part(self, client):
        metadata = json.dumps({"sessionId": "s1", "sequenceNumber": 0})
        files = {"metadata": ("metadata.json", metadata, "application/json")}
        resp = client.post("/audio?token=test-token-123", files=files)
        assert resp.status_code == 400

    def test_missing_metadata_part(self, client):
        files = {"audio": ("audio.raw", b"\x00" * 100, "application/octet-stream")}
        resp = client.post("/audio?token=test-token-123", files=files)
        assert resp.status_code == 400

    def test_sequential_chunks_accepted(self, client):
        for seq in range(3):
            files, token = self._make_multipart(session_id="multi", seq=seq,
                                                 audio_bytes=b"\x00\x01" * 16000)
            resp = client.post(f"/audio?token={token}", files=files)
            assert resp.status_code == 200
            assert resp.json()["sequenceNumber"] == seq
