"""Audio buffer manager — accumulates PCM16 chunks by sessionId and triggers transcription after silence."""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

SILENCE_TIMEOUT = 3.0  # seconds of no new chunks before transcription
MAX_BUFFER_DURATION = 30.0  # max seconds of audio per session (prevent memory leaks)
SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # 16-bit mono = 2 bytes per sample


@dataclass
class AudioSession:
    session_id: str
    chunks: dict[int, bytes] = field(default_factory=dict)  # sequenceNumber -> bytes
    created_at: float = field(default_factory=time.time)
    last_chunk_at: float = field(default_factory=time.time)
    flush_task: asyncio.Task | None = None
    flushed: bool = False


class AudioBufferManager:
    """Buffers audio chunks by sessionId; triggers callback after silence."""

    def __init__(self, on_complete: Callable[[str, bytes], Awaitable[None]]):
        """Initialize AudioBufferManager."""
        self._sessions: dict[str, AudioSession] = {}
        self._on_complete = on_complete

    def _get_or_create(self, session_id: str) -> AudioSession:
        """Get or create an audio buffer session for the given key."""
        if session_id not in self._sessions:
            self._sessions[session_id] = AudioSession(session_id=session_id)
        return self._sessions[session_id]

    async def add_chunk(self, session_id: str, sequence_number: int, audio_bytes: bytes) -> None:
        """Add a chunk and reset the silence timer."""
        session = self._get_or_create(session_id)

        if session.flushed:
            # Session already completed, start fresh
            self._sessions.pop(session_id, None)
            session = self._get_or_create(session_id)

        session.chunks[sequence_number] = audio_bytes
        session.last_chunk_at = time.time()

        # Check max buffer duration
        total_bytes = sum(len(c) for c in session.chunks.values())
        total_duration = total_bytes / BYTES_PER_SECOND
        if total_duration >= MAX_BUFFER_DURATION:
            logger.warning(f"Session {session_id} hit max buffer ({total_duration:.1f}s), flushing now")
            if session.flush_task:
                session.flush_task.cancel()
            await self._flush(session_id)
            return

        # Reset silence timer
        if session.flush_task:
            session.flush_task.cancel()
        session.flush_task = asyncio.create_task(self._silence_timer(session_id))

    async def _silence_timer(self, session_id: str):
        """Wait for silence, then flush."""
        await asyncio.sleep(SILENCE_TIMEOUT)
        await self._flush(session_id)

    async def _flush(self, session_id: str):
        """Assemble chunks in order and invoke callback."""
        session = self._sessions.get(session_id)
        if not session or session.flushed:
            return

        session.flushed = True
        if session.flush_task:
            session.flush_task.cancel()
            session.flush_task = None

        # Assemble in sequence order
        ordered_chunks = [session.chunks[k] for k in sorted(session.chunks.keys())]
        combined = b"".join(ordered_chunks)

        total_duration = len(combined) / BYTES_PER_SECOND
        logger.info(f"Flushing session {session_id}: {len(ordered_chunks)} chunks, {total_duration:.1f}s")

        # Clean up
        self._sessions.pop(session_id, None)

        if combined:
            try:
                await self._on_complete(session_id, combined)
            except Exception as e:
                logger.error(f"Audio completion callback failed for {session_id}: {e}")

    @property
    def active_sessions(self) -> int:
        """Return the number of active audio buffer sessions."""
        return len(self._sessions)

    def get_session_info(self, session_id: str) -> dict | None:
        """Return info dict for a session, or None if not found."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        total_bytes = sum(len(c) for c in session.chunks.values())
        return {
            "session_id": session_id,
            "chunks": len(session.chunks),
            "total_bytes": total_bytes,
            "duration_s": round(total_bytes / BYTES_PER_SECOND, 1),
            "age_s": round(time.time() - session.created_at, 1),
        }
