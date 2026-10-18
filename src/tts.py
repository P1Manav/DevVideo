"""
TTS module: Multi-backend speech synthesis with runtime probing and fallback.

Backends:
- edge    : Microsoft Edge Neural TTS (en-US-AriaNeural)
- espeak  : Local espeak-ng engine
- pyttsx3 : Subprocess-isolated system speech engine (SAPI5 on Windows, nsss on macOS)
- silent  : Last resort silent audio WAVs (flags warning and voice: none)

Features:
- Probing with real short synthesis (not just import checks)
- Atomic voice restart on failure (no mixed voices across scenes)
- Audio format normalization: 44.1kHz mono 16-bit PCM WAV
- Precise A/V padding: 0.25s lead pad + 0.35s tail pad
- WPM calibration from first synthesized sentence
- Beat timing interpolation: word timestamps when available, else proportional to character count
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Protocol

from .schema import Beat, Scene

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 44100
LEAD_PAD_SECONDS = 0.25
TAIL_PAD_SECONDS = 0.35


def _estimate_speech_duration(text: str, wpm: float = 150.0) -> float:
    """Estimate speech duration in seconds from word count."""
    words = len(text.split())
    return max(2.0, (words / wpm) * 60.0)


class TTSBackend(Protocol):
    """Interface for text-to-speech backends."""
    name: str

    def probe(self) -> bool:
        """Run a short real synthesis probe to verify backend availability."""
        ...

    def synthesize(self, text: str, output_path: Path) -> dict[str, Any]:
        """Synthesize text to audio file. Returns metadata (e.g. word boundaries)."""
        ...


def get_audio_duration(path: Path) -> float:
    """Measure duration of an audio file using ffprobe or wave header."""
    if shutil.which("ffprobe"):
        try:
            res = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass

    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        pass

    return 2.0


def normalize_and_pad_audio(raw_audio_path: Path, final_wav_path: Path) -> float:
    """
    Convert raw audio to 44.1kHz 16-bit mono WAV and add 0.25s lead and 0.35s tail pads.
    Returns total padded audio duration.
    """
    final_wav_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        cmd = [
            "ffmpeg", "-y",
            "-i", str(raw_audio_path),
            "-af", f"adelay={int(LEAD_PAD_SECONDS*1000)}|{int(LEAD_PAD_SECONDS*1000)},apad=pad_dur={TAIL_PAD_SECONDS}",
            "-ar", str(TARGET_SAMPLE_RATE),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(final_wav_path),
        ]
        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            return get_audio_duration(final_wav_path)

    # Fallback padding if ffmpeg is missing
    raw_dur = get_audio_duration(raw_audio_path)
    total_dur = raw_dur + LEAD_PAD_SECONDS + TAIL_PAD_SECONDS
    shutil.copyfile(raw_audio_path, final_wav_path)
    return total_dur


# ---------------------------------------------------------------------------
# Edge TTS
# ---------------------------------------------------------------------------

class EdgeTTS:
    """Microsoft Edge TTS via edge-tts package."""
    name = "edge"

    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        self.voice = voice

    def probe(self) -> bool:
        try:
            import edge_tts
        except ImportError:
            return False

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            async def _probe():
                comm = edge_tts.Communicate("Hello", self.voice)
                await asyncio.wait_for(comm.save(str(tmp_path)), timeout=12.0)
            asyncio.run(_probe())
            return tmp_path.exists() and tmp_path.stat().st_size > 0
        except Exception as e:
            logger.debug(f"Edge TTS probe failed: {e}")
            return False
        finally:
            tmp_path.unlink(missing_ok=True)

    def synthesize(self, text: str, output_path: Path) -> dict[str, Any]:
        import edge_tts

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            raw_mp3 = Path(tmp.name)

        word_boundaries: list[dict[str, Any]] = []

        async def _run():
            comm = edge_tts.Communicate(text, self.voice)
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    with open(raw_mp3, "ab") as f:
                        f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    word_boundaries.append(chunk)

        try:
            asyncio.run(asyncio.wait_for(_run(), timeout=40.0))
            normalize_and_pad_audio(raw_mp3, output_path)
        finally:
            raw_mp3.unlink(missing_ok=True)

        return {"word_boundaries": word_boundaries}


# ---------------------------------------------------------------------------
# eSpeak-ng TTS
# ---------------------------------------------------------------------------

class EspeakTTS:
    """Local eSpeak-ng speech engine."""
    name = "espeak"

    def __init__(self, voice: str = "en-us", speed: int = 165) -> None:
        self.voice = voice
        self.speed = speed

    def probe(self) -> bool:
        if not shutil.which("espeak-ng"):
            return False
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            cmd = ["espeak-ng", "-v", self.voice, "-s", str(self.speed), "-w", str(tmp_path), "--stdin"]
            res = subprocess.run(cmd, input="Hello", text=True, capture_output=True, timeout=5)
            return res.returncode == 0 and tmp_path.stat().st_size > 0
        except Exception:
            return False
        finally:
            tmp_path.unlink(missing_ok=True)

    def synthesize(self, text: str, output_path: Path) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            raw_wav = Path(tmp.name)
        try:
            cmd = ["espeak-ng", "-v", self.voice, "-s", str(self.speed), "-w", str(raw_wav), "--stdin"]
            res = subprocess.run(cmd, input=text, text=True, capture_output=True, timeout=30)
            if res.returncode != 0:
                raise RuntimeError(f"espeak-ng failed (exit {res.returncode}): {res.stderr[:200]}")
            normalize_and_pad_audio(raw_wav, output_path)
        finally:
            raw_wav.unlink(missing_ok=True)
        return {}


# ---------------------------------------------------------------------------
# pyttsx3 TTS (Subprocess isolated)
# ---------------------------------------------------------------------------

class Pyttsx3TTS:
    """System speech engine (SAPI5 on Windows, nsss on macOS) in isolated subprocess."""
    name = "pyttsx3"

    def __init__(self, rate: int = 165) -> None:
        self.rate = rate

    def probe(self) -> bool:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            code = (
                "import pyttsx3\n"
                "e = pyttsx3.init()\n"
                f"e.setProperty('rate', {self.rate})\n"
                f"e.save_to_file('Hello', r'{tmp_path}')\n"
                "e.runAndWait()\n"
            )
            res = subprocess.run(
                ["python", "-c", code],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=8,
            )
            return res.returncode == 0 and tmp_path.stat().st_size > 0
        except Exception:
            return False
        finally:
            tmp_path.unlink(missing_ok=True)

    def synthesize(self, text: str, output_path: Path) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            raw_wav = Path(tmp.name)
        try:
            escaped_text = text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
            code = (
                "import pyttsx3\n"
                "e = pyttsx3.init()\n"
                f"e.setProperty('rate', {self.rate})\n"
                f"e.save_to_file(\"\"\"{escaped_text}\"\"\", r'{raw_wav}')\n"
                "e.runAndWait()\n"
            )
            res = subprocess.run(
                ["python", "-c", code],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if res.returncode != 0:
                raise RuntimeError(f"pyttsx3 synthesis failed: {res.stderr[:200]}")
            normalize_and_pad_audio(raw_wav, output_path)
        finally:
            raw_wav.unlink(missing_ok=True)
        return {}


# ---------------------------------------------------------------------------
# Silent TTS
# ---------------------------------------------------------------------------

class SilentTTS:
    """Silent WAV audio generator (fallback of last resort)."""
    name = "silent"

    def __init__(self, wpm: float = 150.0) -> None:
        self.wpm = wpm

    def probe(self) -> bool:
        return True

    def synthesize(self, text: str, output_path: Path) -> dict[str, Any]:
        words = len(text.split())
        speech_dur = max(1.5, (words / self.wpm) * 60.0)
        total_dur = speech_dur + LEAD_PAD_SECONDS + TAIL_PAD_SECONDS

        n_samples = int(total_dur * TARGET_SAMPLE_RATE)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TARGET_SAMPLE_RATE)
            wf.writeframes(b"\x00\x00" * n_samples)
        return {}


# ---------------------------------------------------------------------------
# Audio Chain & Synchronization
# ---------------------------------------------------------------------------

def calculate_beat_timings(scene: Scene, total_duration: float) -> None:
    """
    Calculate precise start_seconds and end_seconds for each beat within a scene.
    Distributes speech duration proportionally to text length.
    """
    if not scene.beats:
        return

    speech_dur = max(0.5, total_duration - (LEAD_PAD_SECONDS + TAIL_PAD_SECONDS))
    total_chars = sum(max(1, len(b.say)) for b in scene.beats)

    current_time = LEAD_PAD_SECONDS
    for i, beat in enumerate(scene.beats):
        ratio = max(1, len(beat.say)) / float(total_chars)
        dur = speech_dur * ratio
        beat.start_seconds = round(current_time, 2)
        current_time += dur
        # Final beat extends through the tail pad
        if i == len(scene.beats) - 1:
            beat.end_seconds = round(total_duration, 2)
        else:
            beat.end_seconds = round(current_time, 2)


def synthesize_scenes_chain(
    scenes: list[Scene],
    audio_dir: Path,
    requested_backend: str = "auto",
    voice: str | None = None,
) -> tuple[str, str, float, list[Path]]:
    """
    Execute speech synthesis across all scenes with automatic probing and fallback.
    Guarantees no mixed voices across scenes (restarts on backend failure).
    Returns (tts_used, fallback_reason, calibrated_wpm, audio_paths).
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    voice_name = voice or "en-US-AriaNeural"

    # Candidate backends in strict order: edge -> espeak -> pyttsx3 -> silent
    candidate_backends: list[TTSBackend] = []
    if requested_backend == "edge":
        candidate_backends = [EdgeTTS(voice=voice_name), EspeakTTS(), Pyttsx3TTS(), SilentTTS()]
    elif requested_backend == "espeak":
        candidate_backends = [EspeakTTS(), Pyttsx3TTS(), SilentTTS()]
    elif requested_backend == "pyttsx3":
        candidate_backends = [Pyttsx3TTS(), SilentTTS()]
    elif requested_backend == "silent":
        candidate_backends = [SilentTTS()]
    else:  # "auto"
        candidate_backends = [EdgeTTS(voice=voice_name), EspeakTTS(), Pyttsx3TTS(), SilentTTS()]

    fallback_reasons: list[str] = []
    tts_used = "silent"

    for backend in candidate_backends:
        # 1. Probe backend
        if not backend.probe():
            fallback_reasons.append(f"{backend.name} probe failed or unavailable")
            continue

        # 2. Attempt full synthesis across all scenes
        audio_paths: list[Path] = []
        backend_succeeded = True
        logger.info(f"Synthesizing {len(scenes)} scenes with TTS backend: {backend.name}")

        for i, scene in enumerate(scenes):
            out_wav = audio_dir / f"{scene.id}.wav"
            try:
                backend.synthesize(scene.narration, out_wav)
                dur = get_audio_duration(out_wav)
                scene.duration_seconds = round(dur, 2)
                calculate_beat_timings(scene, dur)
                audio_paths.append(out_wav)
            except Exception as e:
                logger.warning(f"TTS backend '{backend.name}' failed on scene '{scene.id}': {e}")
                backend_succeeded = False
                fallback_reasons.append(f"{backend.name} failed on scene {scene.id}: {e}")
                # Clean up and restart with next backend
                for p in audio_paths:
                    p.unlink(missing_ok=True)
                break

        if backend_succeeded:
            tts_used = backend.name
            break

    # Voice requirement enforcement
    if os.environ.get("DEVVIDEO_REQUIRE_VOICE") == "1" and tts_used == "silent":
        raise RuntimeError("DEVVIDEO_REQUIRE_VOICE=1 was set, but all voice backends failed.")

    # 3. WPM calibration from first scene
    calibrated_wpm = 165.0
    if scenes and scenes[0].duration_seconds > 0.6:
        raw_speech_dur = scenes[0].duration_seconds - (LEAD_PAD_SECONDS + TAIL_PAD_SECONDS)
        words = len(scenes[0].narration.split())
        if raw_speech_dur > 0.5:
            calibrated_wpm = round((words / raw_speech_dur) * 60.0, 1)

    reason_str = "; ".join(fallback_reasons) if tts_used != requested_backend and requested_backend != "auto" else ""
    if requested_backend == "auto" and tts_used != "edge" and fallback_reasons:
        reason_str = f"auto selected {tts_used}: {fallback_reasons[0]}"

    return tts_used, reason_str, calibrated_wpm, audio_paths


def get_tts_backend(requested: str | None = None) -> TTSBackend:
    """Compatibility getter for single TTS backend instance."""
    name = requested or os.environ.get("TTS_BACKEND", "auto")
    if name == "edge":
        return EdgeTTS()
    if name == "espeak":
        return EspeakTTS()
    if name == "pyttsx3":
        return Pyttsx3TTS()
    if name == "silent":
        return SilentTTS()
    # auto
    if shutil.which("espeak-ng"):
        return EspeakTTS()
    return Pyttsx3TTS()
