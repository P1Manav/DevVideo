"""
TTS module: generate audio for each scene's narration.

Backends:
  silent  - generates silence WAV files (word-count based duration)
  edge    - Microsoft Edge TTS (needs internet)
  espeak  - espeak-ng local TTS

Env: TTS_BACKEND = auto | silent | edge | espeak
"""

from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class TTSBackend(Protocol):
    """Interface for TTS backends."""
    name: str

    def synthesize(self, text: str, output_path: Path) -> None:
        """Generate audio file from text."""
        ...


# ---------------------------------------------------------------------------
# Silent backend: generates WAV silence based on word count
# ---------------------------------------------------------------------------

def _estimate_speech_duration(text: str, wpm: float = 150.0) -> float:
    """Estimate speech duration in seconds from word count."""
    words = len(text.split())
    return max(2.0, (words / wpm) * 60.0)


def _generate_silence_wav(duration: float, output_path: Path, sample_rate: int = 22050) -> None:
    """Write a WAV file containing `duration` seconds of silence."""
    n_samples = int(duration * sample_rate)
    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)


class SilentTTS:
    """Generates silence WAV files with duration based on word count."""
    name = "silent"

    def __init__(self, wpm: float = 150.0) -> None:
        self.wpm = wpm

    def synthesize(self, text: str, output_path: Path) -> None:
        duration = _estimate_speech_duration(text, self.wpm)
        _generate_silence_wav(duration, output_path)
        logger.debug(f"Silent TTS: {duration:.1f}s -> {output_path}")


# ---------------------------------------------------------------------------
# Edge TTS backend (needs internet)
# ---------------------------------------------------------------------------

class EdgeTTS:
    """Microsoft Edge TTS via edge-tts package."""
    name = "edge"

    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        self.voice = voice

    def synthesize(self, text: str, output_path: Path) -> None:
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError("edge-tts not installed. pip install edge-tts")

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(str(output_path))

        asyncio.run(_run())
        logger.debug(f"Edge TTS -> {output_path}")


# ---------------------------------------------------------------------------
# eSpeak backend (local, no internet)
# ---------------------------------------------------------------------------

class EspeakTTS:
    """Local TTS using espeak-ng."""
    name = "espeak"

    def synthesize(self, text: str, output_path: Path) -> None:
        wav_path = output_path.with_suffix(".wav")
        result = subprocess.run(
            ["espeak-ng", "-w", str(wav_path), text],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"espeak-ng failed: {result.stderr[:200]}")

        # Convert to mp3-compatible format if needed
        if output_path.suffix == ".wav":
            return
        # For mp3, we'd need ffmpeg conversion - keep as wav for simplicity
        wav_path.rename(output_path)


# ---------------------------------------------------------------------------
# Auto-selection
# ---------------------------------------------------------------------------

def get_tts_backend(requested: str | None = None) -> TTSBackend:
    """Select a TTS backend based on TTS_BACKEND env var or explicit request."""
    backend_name = requested or os.environ.get("TTS_BACKEND", "auto")

    if backend_name == "silent":
        return SilentTTS()

    if backend_name == "edge":
        return EdgeTTS()

    if backend_name == "espeak":
        return EspeakTTS()

    if backend_name == "auto":
        # Try edge-tts first (best quality), then espeak, then silent
        try:
            import edge_tts
            return EdgeTTS()
        except ImportError:
            pass

        if shutil.which("espeak-ng"):
            return EspeakTTS()

        logger.info("Auto-selected silent TTS (no TTS engine available)")
        return SilentTTS()

    raise ValueError(f"Unknown TTS backend: {backend_name!r}")


# ---------------------------------------------------------------------------
# Utility: get audio duration via ffprobe
# ---------------------------------------------------------------------------

def get_audio_duration(path: Path) -> float:
    """Get the duration of an audio file in seconds using ffprobe."""
    if shutil.which("ffprobe"):
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass

    # Fallback: read WAV header
    try:
        with wave.open(str(path), "r") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / rate
    except Exception:
        pass

    # Last resort: estimate from file size
    logger.warning(f"Could not determine duration of {path}, estimating from size")
    size = path.stat().st_size
    return size / (22050 * 2)  # 16-bit mono at 22050 Hz
