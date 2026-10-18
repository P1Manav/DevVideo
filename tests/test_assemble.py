"""
Unit tests for assemble.py, subtitle generation, chapters, index, and search_demo.
"""

import json
from pathlib import Path
from PIL import Image

import pytest
from src.assemble import (
    assemble_video_from_timeline,
    concat_audio_files,
    format_timestamp,
    generate_chapters,
    generate_index_jsonl,
    generate_subtitles,
    generate_thumbnail,
)
from src.schema import Beat, Evidence, OnScreen, Scene
from src.tts import SilentTTS
from tools.search_demo import search_index, tokenize


def _create_sample_scenes() -> list[Scene]:
    s1 = Scene(
        id="title",
        kind="title",
        title="Welcome to VidSearch",
        narration="Welcome to VidSearch, an AI video retrieval engine.",
        duration_seconds=4.0,
        evidence=Evidence(file="README.md", quote="VidSearch engine"),
        on_screen=OnScreen(type="title", content="VidSearch"),
        beats=[
            Beat(say="Welcome to VidSearch", caption="Welcome to VidSearch", start_seconds=0.25, end_seconds=2.0),
            Beat(say="an AI video retrieval engine", caption="an AI video retrieval engine", start_seconds=2.0, end_seconds=4.0),
        ],
    )
    s2 = Scene(
        id="terminal",
        kind="terminal",
        title="Quickstart CLI",
        narration="Install with pip and run the command line interface.",
        duration_seconds=5.0,
        evidence=Evidence(file="README.md", quote="Install with pip"),
        on_screen=OnScreen(type="terminal", content="pip install vidsearch"),
        beats=[
            Beat(say="Install with pip", caption="pip install vidsearch", start_seconds=0.25, end_seconds=2.5),
            Beat(say="and run the command line interface", caption="python -m vidsearch.cli", start_seconds=2.5, end_seconds=5.0),
        ],
    )
    return [s1, s2]


class TestTimestampFormatting:
    def test_format_timestamp_vtt(self):
        assert format_timestamp(0.0, vtt=True) == "00:00:00.000"
        assert format_timestamp(65.432, vtt=True) == "00:01:05.432"
        assert format_timestamp(3661.1, vtt=True) == "01:01:01.100"

    def test_format_timestamp_srt(self):
        assert format_timestamp(0.0, vtt=False) == "00:00:00,000"
        assert format_timestamp(65.432, vtt=False) == "00:01:05,432"


class TestSubtitles:
    def test_generate_vtt_and_srt(self, tmp_path):
        scenes = _create_sample_scenes()
        vtt_path = tmp_path / "transcript.vtt"
        srt_path = tmp_path / "transcript.srt"

        generate_subtitles(scenes, vtt_path, srt_path)

        assert vtt_path.exists()
        assert srt_path.exists()

        vtt_text = vtt_path.read_text(encoding="utf-8")
        assert vtt_text.startswith("WEBVTT")
        assert "Welcome to VidSearch" in vtt_text
        assert "00:00:00.250 -->" in vtt_text

        srt_text = srt_path.read_text(encoding="utf-8")
        assert "1\n00:00:00,250 -->" in srt_text
        assert "pip install vidsearch" in srt_text


class TestChapters:
    def test_generate_chapters(self, tmp_path):
        scenes = _create_sample_scenes()
        chapters_path = tmp_path / "chapters.json"

        generate_chapters(scenes, chapters_path)
        assert chapters_path.exists()

        data = json.loads(chapters_path.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0]["title"] == "Welcome to VidSearch"
        assert data[0]["start_time"] == 0.0
        assert data[0]["end_time"] == 4.0
        assert data[1]["start_time"] == 4.0
        assert data[1]["end_time"] == 9.0


class TestIndexJsonlAndSearchDemo:
    def test_generate_index_and_search(self, tmp_path):
        scenes = _create_sample_scenes()
        index_path = tmp_path / "index.jsonl"

        generate_index_jsonl(scenes, index_path)
        assert index_path.exists()

        lines = index_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 4

        rec0 = json.loads(lines[0])
        assert rec0["beat_id"] == "title_0"
        assert "VidSearch" in rec0["text"]
        assert rec0["start_seconds"] == 0.25

        # Test search demo
        matches = search_index(index_path, "pip command line", top_k=2)
        assert len(matches) > 0
        top_score, top_rec = matches[0]
        assert top_score > 0.0
        assert top_rec["scene_id"] == "terminal"

        # Search for non-existent terms
        empty_matches = search_index(index_path, "quantum biology", top_k=2)
        assert len(empty_matches) == 0


class TestVideoAssembly:
    def test_concat_audio_files(self, tmp_path):
        wav1 = tmp_path / "w1.wav"
        wav2 = tmp_path / "w2.wav"
        silent = SilentTTS()
        silent.synthesize("test1 with multiple words to generate audio duration", wav1)
        silent.synthesize("test2 with multiple words to generate audio duration", wav2)

        out_wav = tmp_path / "narration.wav"
        dur = concat_audio_files([wav1, wav2], out_wav)
        assert out_wav.exists()
        assert dur >= 3.0

    def test_assemble_video_from_timeline(self, tmp_path):
        # Create 2 simple dummy frames
        f1 = tmp_path / "f1.png"
        f2 = tmp_path / "f2.png"
        Image.new("RGB", (1280, 720), color=(10, 20, 30)).save(f1)
        Image.new("RGB", (1280, 720), color=(30, 40, 50)).save(f2)

        wav = tmp_path / "audio.wav"
        SilentTTS().synthesize("speech with multiple words to make audio long enough", wav)

        timeline = [(f1, 2.0), (f2, 2.0)]
        out_mp4 = tmp_path / "video.mp4"

        final_dur = assemble_video_from_timeline(timeline, wav, out_mp4)
        assert out_mp4.exists()
        assert 3.5 <= final_dur <= 4.5

        # Test thumbnail generation from mp4
        thumb_path = tmp_path / "thumbnail.png"
        generate_thumbnail(out_mp4, fallback_frame=f1, thumbnail_path=thumb_path)
        assert thumb_path.exists()
        assert thumb_path.stat().st_size > 0
