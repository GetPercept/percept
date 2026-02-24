"""Audio transcription module using faster-whisper for raw PCM16 input."""

import logging
import numpy as np
from dataclasses import dataclass
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

@dataclass
class TranscriptionResult:
    text: str
    language: str
    confidence: float


def pcm16_to_float32(pcm_bytes: bytes) -> np.ndarray:
    """Convert raw PCM16 (int16, little-endian) bytes to float32 array normalized to [-1, 1]."""
    if not pcm_bytes:
        return np.array([], dtype=np.float32)
    audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
    return audio_int16.astype(np.float32) / 32768.0


class AudioTranscriber:
    """Transcribe raw PCM16 audio using faster-whisper."""

    def __init__(self, model_size: str = "base", device: str = "auto", compute_type: str = "int8"):
        """Initialize AudioTranscriber with the specified transcription backend."""
        logger.info(f"Loading whisper model: {model_size} (device={device}, compute={compute_type})")
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> TranscriptionResult:
        """Transcribe raw PCM16 bytes. Returns TranscriptionResult."""
        audio = pcm16_to_float32(pcm_bytes)

        # Handle empty/very short audio
        min_samples = sample_rate // 4  # at least 0.25s
        if len(audio) < min_samples:
            return TranscriptionResult(text="", language="en", confidence=0.0)

        # Check for silence (RMS below threshold)
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.005:
            logger.debug("Audio is silence (RMS=%.4f)", rms)
            return TranscriptionResult(text="", language="en", confidence=0.0)

        segments, info = self._model.transcribe(
            audio,
            beam_size=5,
            language="en",
            vad_filter=True,
        )

        texts = []
        for seg in segments:
            texts.append(seg.text.strip())

        full_text = " ".join(texts).strip()
        confidence = round(np.exp(info.language_probability) if hasattr(info, 'language_probability') else 0.0, 3)

        return TranscriptionResult(
            text=full_text,
            language=info.language or "en",
            confidence=confidence,
        )
