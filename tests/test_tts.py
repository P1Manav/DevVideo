"""
Unit tests for the TTS module.
"""

import pytest
import wave
from pathlib import Path

from src.tts import SilentTTS, get_tts_backend, _estimate_speech_duration, get_audio_duration


class TestSilentTTS:
    def test_generates_wav(self, tmp_path):
        tts = SilentTTS()
        out = tmp_path / "test.wav"
        tts.synthesize("Hello world, this is a test of the silent TTS backend.", out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_wav_is_valid(self, tmp_path):
        tts = SilentTTS()
        out = tmp_path / "test.wav"
        tts.synthesize("A sentence with several words for testing duration.", out)

        with wave.open(str(out), "r") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 22050

    def test_duration_proportional_to_words(self, tmp_path):
        tts = SilentTTS()
        short_out = tmp_path / "short.wav"
        long_out = tmp_path / "long.wav"

        tts.synthesize("Short text here.", short_out)
        tts.synthesize("This is a much longer text with many more words to speak aloud for testing duration.", long_out)

        short_dur = get_audio_duration(short_out)
        long_dur = get_audio_duration(long_out)
        assert long_dur > short_dur


class TestDurationEstimate:
    def test_150wpm_baseline(self):
        # 150 words at 150 wpm = 60 seconds
        dur = _estimate_speech_duration(" ".join(["word"] * 150))
        assert abs(dur - 60.0) < 0.1

    def test_minimum_duration(self):
        dur = _estimate_speech_duration("One")
        assert dur >= 2.0


class TestTTSBackendSelection:
    def test_explicit_silent(self):
        tts = get_tts_backend("silent")
        assert tts.name == "silent"
