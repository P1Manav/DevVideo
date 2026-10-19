"""
TTS audio chain: normalization, padding, timing calculation, and multi-backend fallback chain.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..schema import Scene

if TYPE_CHECKING:
    from .engines import TTSBackend

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 44100
LEAD_PAD_SECONDS = 0.25
TAIL_PAD_SECONDS = 0.35


def _estimate_speech_duration(text: str, wpm: float = 150.0) -> float:
    """Estimate speech duration in seconds from word count."""
    words = len(text.split())
    return max(2.0, (words / wpm) * 60.0)


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
    rate_multiplier: float = 1.0,
) -> tuple[str, str, float, list[Path]]:
    """
    Execute speech synthesis across all scenes with automatic probing and fallback.
    Guarantees no mixed voices across scenes (restarts on backend failure).
    Supports rate_multiplier for bounded duration repair.
    Returns (tts_used, fallback_reason, calibrated_wpm, audio_paths).
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    voice_name = voice or "en-US-AriaNeural"

    base_rate_pct = 8
    eff_pct = int(base_rate_pct + (rate_multiplier - 1.0) * 100)
    rate_pct_str = f"+{eff_pct}%" if eff_pct >= 0 else f"{eff_pct}%"
    pyttsx3_rate = int(195 * rate_multiplier)
    espeak_speed = int(165 * rate_multiplier)
    piper_scale = round(1.0 / rate_multiplier, 3)
    silent_wpm = 150.0 * rate_multiplier

    import sys
    from . import engines

    tts_mod = sys.modules.get("src.tts")
    edge_cls = getattr(tts_mod, "EdgeTTS", engines.EdgeTTS) if tts_mod else engines.EdgeTTS
    piper_cls = getattr(tts_mod, "PiperTTS", engines.PiperTTS) if tts_mod else engines.PiperTTS
    espeak_cls = getattr(tts_mod, "EspeakTTS", engines.EspeakTTS) if tts_mod else engines.EspeakTTS
    pyttsx3_cls = getattr(tts_mod, "Pyttsx3TTS", engines.Pyttsx3TTS) if tts_mod else engines.Pyttsx3TTS
    silent_cls = getattr(tts_mod, "SilentTTS", engines.SilentTTS) if tts_mod else engines.SilentTTS

    candidate_backends: list[TTSBackend] = []
    if requested_backend == "edge":
        candidate_backends = [
            edge_cls(voice=voice_name, rate=rate_pct_str),
            piper_cls(length_scale=piper_scale),
            espeak_cls(speed=espeak_speed),
            pyttsx3_cls(rate=pyttsx3_rate),
            silent_cls(wpm=silent_wpm),
        ]
    elif requested_backend == "piper":
        candidate_backends = [
            piper_cls(length_scale=piper_scale),
            espeak_cls(speed=espeak_speed),
            pyttsx3_cls(rate=pyttsx3_rate),
            silent_cls(wpm=silent_wpm),
        ]
    elif requested_backend == "espeak":
        candidate_backends = [
            espeak_cls(speed=espeak_speed),
            pyttsx3_cls(rate=pyttsx3_rate),
            silent_cls(wpm=silent_wpm),
        ]
    elif requested_backend == "pyttsx3":
        candidate_backends = [
            pyttsx3_cls(rate=pyttsx3_rate),
            silent_cls(wpm=silent_wpm),
        ]
    elif requested_backend == "silent":
        candidate_backends = [silent_cls(wpm=silent_wpm)]
    else:  # "auto"
        candidate_backends = [
            edge_cls(voice=voice_name, rate=rate_pct_str),
            piper_cls(length_scale=piper_scale),
            espeak_cls(speed=espeak_speed),
            pyttsx3_cls(rate=pyttsx3_rate),
            silent_cls(wpm=silent_wpm),
        ]

    fallback_reasons: list[str] = []
    tts_used = "silent"
    audio_paths: list[Path] = []

    for backend in candidate_backends:
        if not backend.probe():
            fallback_reasons.append(f"{backend.name} probe failed or unavailable")
            continue

        audio_paths = []
        backend_succeeded = True
        logger.info(f"Synthesizing {len(scenes)} scenes with TTS backend: {backend.name}")

        for scene in scenes:
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
                for p in audio_paths:
                    p.unlink(missing_ok=True)
                break

        if backend_succeeded:
            tts_used = backend.name
            break

    if os.environ.get("DEVVIDEO_REQUIRE_VOICE") == "1" and tts_used == "silent":
        raise RuntimeError("DEVVIDEO_REQUIRE_VOICE=1 was set, but all voice backends failed.")

    calibrated_wpm = 165.0
    if scenes and scenes[0].duration_seconds > 0.6:
        raw_speech_dur = scenes[0].duration_seconds - (LEAD_PAD_SECONDS + TAIL_PAD_SECONDS)
        words = len(scenes[0].narration.split())
        if raw_speech_dur > 0.5:
            calibrated_wpm = round((words / raw_speech_dur) * 60.0, 1)

    reason_str = (
        "; ".join(fallback_reasons)
        if tts_used != requested_backend and requested_backend != "auto"
        else ""
    )
    if requested_backend == "auto" and tts_used != "edge" and fallback_reasons:
        reason_str = f"auto selected {tts_used}: {fallback_reasons[0]}"

    return tts_used, reason_str, calibrated_wpm, audio_paths
