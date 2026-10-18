"""
Unit tests for the TTS module.

Tests:
- Silent TTS: WAV validity, duration proportional to word count
- Audio padding: 0.25s lead and 0.35s tail pads
- Beat timing calculation: distributes speech duration proportionally
- Multi-backend chain: probing in order, fallback, atomic restart on scene failure (no mixed voices)
- DEVVIDEO_REQUIRE_VOICE enforcement
"""

import os
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.schema import Beat, Evidence, OnScreen, Scene
from src.tts import (
    SilentTTS,
    Pyttsx3TTS,
    calculate_beat_timings,
    get_audio_duration,
    get_tts_backend,
    normalize_and_pad_audio,
    synthesize_scenes_chain,
    _estimate_speech_duration,
)


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

        with wave.open(str(out), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 44100

    def test_duration_proportional_to_words(self, tmp_path):
        tts = SilentTTS()
        short_out = tmp_path / "short.wav"
        long_out = tmp_path / "long.wav"

        tts.synthesize("Short text here.", short_out)
        tts.synthesize(
            "This is a much longer text with many more words to speak aloud for testing duration.",
            long_out,
        )

        short_dur = get_audio_duration(short_out)
        long_dur = get_audio_duration(long_out)
        assert long_dur > short_dur


class TestDurationEstimate:
    def test_150wpm_baseline(self):
        dur = _estimate_speech_duration(" ".join(["word"] * 150))
        assert abs(dur - 60.0) < 0.1

    def test_minimum_duration(self):
        dur = _estimate_speech_duration("One")
        assert dur >= 2.0


class TestBeatTimings:
    def test_calculate_beat_timings_proportional(self):
        """Beats within a scene have monotonic start/end times within total duration."""
        scene = Scene(
            id="s1",
            beats=[
                Beat(say="First sentence with five words.", caption="First"),
                Beat(say="Second sentence with many more words to take longer duration.", caption="Second"),
            ],
            on_screen=OnScreen(type="text", content="test"),
            evidence=Evidence(file="README.md", quote="test"),
        )
        total_duration = 5.0
        calculate_beat_timings(scene, total_duration)

        assert len(scene.beats) == 2
        b1, b2 = scene.beats
        assert b1.start_seconds == 0.25  # Lead pad
        assert b1.end_seconds == b2.start_seconds
        assert b2.end_seconds == 5.0  # Includes tail pad
        assert (b2.end_seconds - b2.start_seconds) > (b1.end_seconds - b1.start_seconds)


class TestTTSChain:
    def test_synthesize_chain_atomic_restart_on_failure(self, tmp_path):
        """Simulated backend failure on scene 2 restarts from scene 1 with next backend (no mixed voices)."""
        scene1 = Scene(
            id="s1",
            narration="First scene narration text.",
            on_screen=OnScreen(type="text", content="s1"),
            evidence=Evidence(file="README.md", quote="test"),
        )
        scene2 = Scene(
            id="s2",
            narration="Second scene narration text.",
            on_screen=OnScreen(type="text", content="s2"),
            evidence=Evidence(file="README.md", quote="test"),
        )
        scenes = [scene1, scene2]

        # Mock a flaky backend that succeeds on probe and scene 1 but fails on scene 2
        mock_flaky = MagicMock()
        mock_flaky.name = "flaky"
        mock_flaky.probe.return_value = True

        call_count = 0
        def fake_synthesize(text, out_path):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Simulated network drop on scene 2")
            SilentTTS().synthesize(text, out_path)

        mock_flaky.synthesize.side_effect = fake_synthesize

        # Mock fallback backend
        mock_fallback = MagicMock()
        mock_fallback.name = "fallback"
        mock_fallback.probe.return_value = True
        mock_fallback.synthesize.side_effect = lambda text, out_path: SilentTTS().synthesize(text, out_path)

        with patch("src.tts.EdgeTTS", return_value=mock_flaky), \
             patch("src.tts.EspeakTTS", return_value=mock_fallback):
            tts_used, fallback_reason, wpm, paths = synthesize_scenes_chain(
                scenes,
                audio_dir=tmp_path / "audio",
                requested_backend="auto",
            )

        assert tts_used == "fallback"
        assert "flaky failed on scene s2" in fallback_reason
        assert len(paths) == 2
        for p in paths:
            assert p.exists()

    def test_require_voice_fails_on_silent(self, tmp_path, monkeypatch):
        """DEVVIDEO_REQUIRE_VOICE=1 causes error if only silent TTS is available."""
        monkeypatch.setenv("DEVVIDEO_REQUIRE_VOICE", "1")
        scenes = [
            Scene(
                id="s1",
                narration="Test narration text.",
                on_screen=OnScreen(type="text", content="s1"),
                evidence=Evidence(file="README.md", quote="test"),
            )
        ]
        with pytest.raises(RuntimeError, match="DEVVIDEO_REQUIRE_VOICE"):
            synthesize_scenes_chain(scenes, audio_dir=tmp_path / "audio", requested_backend="silent")
