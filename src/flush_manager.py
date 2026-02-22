"""Segment accumulation, flush scheduling, and wake word detection for Percept.

Handles the buffering of transcript segments, silence timeout detection,
command continuation windows, and wake word matching.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

# Timing constants
SILENCE_TIMEOUT = 2        # seconds before flushing accumulated segments
COMMAND_TIMEOUT = 2        # extended wait when wake word detected
CONVERSATION_END_TIMEOUT = 20  # seconds of silence → conversation over
WAKE_CONTINUATION_WINDOW = 10  # seconds after wake flush to treat new speech as command


class FlushManager:
    """Manages segment accumulation and flush scheduling.

    Tracks per-session segment buffers, schedules flushes after silence,
    extends timeouts when wake words are detected, and manages the
    command continuation window.

    Args:
        wake_words_fn: Callable returning list of current wake words.
        on_flush: Async callback invoked with (session_key, segments) on flush.
        silence_timeout: Seconds of silence before flushing.
        command_timeout: Extra seconds to wait when wake word is in buffer.
        continuation_window: Seconds after wake flush to keep treating speech as command.
    """

    def __init__(self, wake_words_fn, on_flush, silence_timeout=SILENCE_TIMEOUT,
                 command_timeout=COMMAND_TIMEOUT, continuation_window=WAKE_CONTINUATION_WINDOW):
        self.wake_words_fn = wake_words_fn
        self.on_flush = on_flush
        self.silence_timeout = silence_timeout
        self.command_timeout = command_timeout
        self.continuation_window = continuation_window

        self.accumulated_segments: dict[str, list] = defaultdict(list)
        self.last_segment_time: dict[str, float] = {}
        self.flush_tasks: dict[str, asyncio.Task] = {}
        self.last_wake_flush: dict[str, float] = {}

    def add_segments(self, session_key: str, segments: list[dict]):
        """Add transcript segments and schedule a flush.

        Args:
            session_key: Session/user identifier.
            segments: List of segment dicts with text, speaker, is_user, start, end.
        """
        for s in segments:
            self.accumulated_segments[session_key].append({
                "text": s.get("text", ""),
                "speaker": s.get("speaker", "SPEAKER_00"),
                "is_user": s.get("is_user", False),
                "start": s.get("start", 0.0),
                "end": s.get("end", 0.0),
                "start_time": time.time(),
            })
        self.last_segment_time[session_key] = time.time()

        # Cancel previous flush and reschedule
        if session_key in self.flush_tasks:
            self.flush_tasks[session_key].cancel()
        self.flush_tasks[session_key] = asyncio.create_task(self._schedule_flush(session_key))

    def has_wake_word(self, text: str) -> bool:
        """Check if text contains any wake word.

        Args:
            text: Text to check (case-insensitive).

        Returns:
            True if any wake word is found in the text.
        """
        wake_words = self.wake_words_fn()
        return any(w in text.lower() for w in wake_words)

    def in_continuation_window(self, session_key: str) -> bool:
        """Check if session is within the command continuation window.

        Args:
            session_key: Session identifier.

        Returns:
            True if within the continuation window of a previous wake flush.
        """
        last = self.last_wake_flush.get(session_key, 0)
        return (time.time() - last) < self.continuation_window

    async def _schedule_flush(self, session_key: str):
        """Wait for silence, extend if wake word detected, then flush.

        Args:
            session_key: Session identifier.
        """
        await asyncio.sleep(self.silence_timeout)

        # Check for wake word — extend timeout to capture full command
        texts = [s["text"] for s in self.accumulated_segments.get(session_key, [])]
        full_text = " ".join(texts).lower()
        if self.has_wake_word(full_text):
            waited = 0
            last_count = len(self.accumulated_segments.get(session_key, []))
            while waited < self.command_timeout:
                await asyncio.sleep(1)
                waited += 1
                new_count = len(self.accumulated_segments.get(session_key, []))
                if new_count > last_count:
                    last_count = new_count
                    waited = 0

        await self._flush(session_key)

    async def _flush(self, session_key: str):
        """Execute the flush — pop segments and call the callback.

        Args:
            session_key: Session identifier.
        """
        segments = self.accumulated_segments.pop(session_key, [])
        self.last_segment_time.pop(session_key, None)
        self.flush_tasks.pop(session_key, None)

        if not segments:
            return

        # Track wake flush timing
        texts = [s["text"] for s in segments]
        full_text = " ".join(texts).lower()
        if self.has_wake_word(full_text) or self.in_continuation_window(session_key):
            self.last_wake_flush[session_key] = time.time()

        await self.on_flush(session_key, segments)
