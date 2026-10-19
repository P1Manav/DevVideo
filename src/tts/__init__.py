"""
TTS package: speech synthesis backends and audio synchronization chain.
"""

from .chain import (
    LEAD_PAD_SECONDS,
    TAIL_PAD_SECONDS,
    TARGET_SAMPLE_RATE,
    _estimate_speech_duration,
    calculate_beat_timings,
    get_audio_duration,
    normalize_and_pad_audio,
    synthesize_scenes_chain,
)
from .engines import (
    EdgeTTS,
    EspeakTTS,
    PiperTTS,
    Pyttsx3TTS,
    SilentTTS,
    TTSBackend,
    get_tts_backend,
)

__all__ = [
    "LEAD_PAD_SECONDS",
    "TAIL_PAD_SECONDS",
    "TARGET_SAMPLE_RATE",
    "calculate_beat_timings",
    "get_audio_duration",
    "normalize_and_pad_audio",
    "synthesize_scenes_chain",
    "EdgeTTS",
    "EspeakTTS",
    "PiperTTS",
    "Pyttsx3TTS",
    "SilentTTS",
    "TTSBackend",
    "get_tts_backend",
]
