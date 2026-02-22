"""Whisper transcription pipeline using faster-whisper."""

import io
import wave
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    text: str
    start: float
    end: float
    speaker: str = "SPEAKER_00"


@dataclass
class Conversation:
    segments: list[Segment] = field(default_factory=list)
    started_at: float = 0.0
    last_activity: float = 0.0

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments)


class Transcriber:
    def __init__(self, config: dict):
        cfg = config["whisper"]
        self.model = WhisperModel(
            cfg["model_size"],
            device=cfg.get("device", "auto"),
            compute_type=cfg.get("compute_type", "int8"),
        )
        self.language = cfg.get("language", "en")
        self.beam_size = cfg.get("beam_size", 5)
        self.silence_threshold = config["audio"]["silence_threshold_seconds"]
        self.sample_rate = config["audio"]["sample_rate"]

        # Active conversation tracking
        self.current_conversation = Conversation(started_at=time.time(), last_activity=time.time())
        self.completed_conversations: list[Conversation] = []

        logger.info(f"Transcriber initialized: model={cfg['model_size']}, device={cfg.get('device','auto')}")

    def pcm16_to_wav(self, pcm_data: bytes, sample_rate: int = 16000) -> bytes:
        """Convert raw PCM16 bytes to WAV format."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        buf.seek(0)
        return buf.read()

    def transcribe_audio(self, pcm_data: bytes, sample_rate: int = 16000) -> list[Segment]:
        """Transcribe PCM16 audio data, returning timestamped segments."""
        if len(pcm_data) < sample_rate * 2 * 2:  # Less than 2 seconds
            logger.debug("Audio too short, skipping")
            return []

        wav_data = self.pcm16_to_wav(pcm_data, sample_rate)
        audio_stream = io.BytesIO(wav_data)

        segments_out = []
        try:
            segments, info = self.model.transcribe(
                audio_stream,
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500),
            )
            for seg in segments:
                text = seg.text.strip()
                if text:
                    segments_out.append(Segment(
                        text=text,
                        start=round(seg.start, 2),
                        end=round(seg.end, 2),
                    ))
            logger.info(f"Transcribed {len(segments_out)} segments ({info.duration:.1f}s audio)")
        except Exception as e:
            logger.error(f"Transcription error: {e}")

        return segments_out

    def process_chunk(self, pcm_data: bytes, sample_rate: int = 16000) -> tuple[list[Segment], Conversation | None]:
        """Process an audio chunk. Returns (segments, completed_conversation_or_None).

        If silence gap exceeds threshold, finalizes current conversation and starts new one.
        """
        now = time.time()
        completed = None

        # Check for conversation break
        if self.current_conversation.segments and (now - self.current_conversation.last_activity) > self.silence_threshold:
            completed = self.current_conversation
            self.completed_conversations.append(completed)
            self.current_conversation = Conversation(started_at=now, last_activity=now)
            logger.info(f"Conversation break detected. Completed conversation with {len(completed.segments)} segments")

        segments = self.transcribe_audio(pcm_data, sample_rate)
        if segments:
            self.current_conversation.segments.extend(segments)
            self.current_conversation.last_activity = now

        return segments, completed

    # Placeholder for future speaker diarization
    def diarize(self, pcm_data: bytes, sample_rate: int = 16000) -> list[Segment]:
        """TODO: Add pyannote speaker diarization."""
        logger.warning("Diarization not implemented — returning single-speaker segments")
        return self.transcribe_audio(pcm_data, sample_rate)
