"""
TTS engines: implementations of speech synthesis backends.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Protocol

from .chain import (
    LEAD_PAD_SECONDS,
    TAIL_PAD_SECONDS,
    TARGET_SAMPLE_RATE,
    normalize_and_pad_audio,
)

logger = logging.getLogger(__name__)


class TTSBackend(Protocol):
    """Interface for text-to-speech backends."""
    name: str

    def probe(self) -> bool:
        """Run a short real synthesis probe to verify backend availability."""
        ...

    def synthesize(self, text: str, output_path: Path) -> dict[str, Any]:
        """Synthesize text to audio file. Returns metadata (e.g. word boundaries)."""
        ...


class EdgeTTS:
    """Microsoft Edge TTS via edge-tts package."""
    name = "edge"

    def __init__(self, voice: str = "en-US-AriaNeural", rate: str = "+0%") -> None:
        self.voice = voice
        self.rate = rate

    def probe(self) -> bool:
        try:
            import edge_tts
        except ImportError:
            return False

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            def _run_probe():
                async def _inner():
                    comm = edge_tts.Communicate("Hello", self.voice, rate=self.rate)
                    await asyncio.wait_for(comm.save(str(tmp_path)), timeout=12.0)
                asyncio.run(_inner())

            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_run_probe)
                fut.result(timeout=15.0)
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
            comm = edge_tts.Communicate(text, self.voice, rate=self.rate)
            try:
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        with open(raw_mp3, "ab") as f:
                            f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        word_boundaries.append(chunk)
            except Exception:
                if not raw_mp3.exists() or raw_mp3.stat().st_size == 0:
                    await comm.save(str(raw_mp3))

        try:
            last_err = None
            for attempt in range(2):
                try:
                    if raw_mp3.exists():
                        raw_mp3.unlink(missing_ok=True)
                    asyncio.run(asyncio.wait_for(_run(), timeout=25.0))
                    if raw_mp3.exists() and raw_mp3.stat().st_size > 0:
                        break
                except Exception as e:
                    last_err = e
            if not raw_mp3.exists() or raw_mp3.stat().st_size == 0:
                raise RuntimeError(f"Edge TTS synthesis failed after retries: {last_err}")
            normalize_and_pad_audio(raw_mp3, output_path)
        finally:
            raw_mp3.unlink(missing_ok=True)

        return {"word_boundaries": word_boundaries}


class PiperTTS:
    """Piper local neural TTS (fast, local ONNX runtime)."""
    name = "piper"

    def __init__(self, model_path: str | Path | None = None, length_scale: float = 1.0) -> None:
        self.model_path = Path(model_path) if model_path else (
            Path(os.environ.get("PIPER_MODEL", "")) if os.environ.get("PIPER_MODEL") else None
        )
        self.length_scale = length_scale

    def probe(self) -> bool:
        if not self.model_path or not self.model_path.exists():
            default_models = list(Path("models").glob("*.onnx")) if Path("models").exists() else []
            if default_models:
                self.model_path = default_models[0]
            else:
                return False

        if not shutil.which("piper"):
            try:
                import piper  # noqa: F401
            except ImportError:
                return False

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self.synthesize("Hello", tmp_path)
            return tmp_path.exists() and tmp_path.stat().st_size > 0
        except Exception:
            return False
        finally:
            tmp_path.unlink(missing_ok=True)

    def synthesize(self, text: str, output_path: Path) -> dict[str, Any]:
        if not self.model_path or not self.model_path.exists():
            raise RuntimeError("Piper ONNX model file not found")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            raw_wav = Path(tmp.name)
        try:
            if shutil.which("piper"):
                cmd = ["piper", "--model", str(self.model_path), "--output_file", str(raw_wav)]
                res = subprocess.run(cmd, input=text, text=True, capture_output=True, timeout=30)
                if res.returncode != 0:
                    raise RuntimeError(f"piper failed (exit {res.returncode}): {res.stderr[:200]}")
            else:
                from piper.voice import PiperVoice
                voice = PiperVoice.load(str(self.model_path))
                with wave.open(str(raw_wav), "wb") as wf:
                    voice.synthesize(text, wf)
            normalize_and_pad_audio(raw_wav, output_path)
        finally:
            raw_wav.unlink(missing_ok=True)
        return {}


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


def get_tts_backend(requested: str | None = None) -> TTSBackend:
    """Compatibility getter for single TTS backend instance."""
    name = requested or os.environ.get("TTS_BACKEND", "auto")
    if name == "edge":
        return EdgeTTS()
    if name == "piper":
        return PiperTTS()
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
