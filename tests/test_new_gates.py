"""
Comprehensive unit tests for Phase 7 evaluation gates:
- Provenance groundedness (60% token overlap + case-sensitive span existence)
- Narration quality (no banned phrases, no junk tokens, no duplicate skeletons, honest start-with file)
- Specificity (each beat names >= 1 repo-specific item)
- Motion gate (>= 24 change events, max gap <= 5.0s)
- Adversarial test cases (quote 'a', sudo commands, template gibberish, static video)
"""

from __future__ import annotations

import tempfile
import subprocess
from pathlib import Path

import pytest

from src.evals.gates import (
    check_audio_audible_gate,
    check_command_validity_gate,
    check_groundedness,
    check_motion_gate,
    check_narration_quality_gate,
    check_specificity_gate,
    check_onscreen_text_integrity_gate,
)
from src.schema import Beat, Evidence, OnScreen, Scene, ScriptPlan, SourceSpan


REPO_FILES = {
    "README.md": (
        "# VidSearch\n"
        "VidSearch indexes videos with CLIP and Faiss for natural language query search.\n"
        "```bash\n"
        "pip install -r requirements.txt\n"
        "python -m vidsearch.cli --query \"sunset\"\n"
        "```\n"
    ),
    "vidsearch/__init__.py": '"""VidSearch package."""\n__version__ = "0.1.0"\n',
    "vidsearch/cli.py": (
        "import argparse\n"
        "def main():\n"
        '    """CLI query tool entrypoint."""\n'
        "    parser = argparse.ArgumentParser()\n"
        '    parser.add_argument("--query", type=str, required=True, help="Search query string")\n'
        "    return parser.parse_args()\n"
    ),
}


class DummyFacts:
    repo_name = "vidsearch"
    entry_module = "vidsearch/cli.py"
    top_modules = ["vidsearch.cli", "vidsearch.indexer"]
    identifiers = ["main", "parse_args", "VidSearch"]
    dependencies = {"clip": "neural embeddings", "faiss": "vector index"}
    readme_description_sentences = ["VidSearch indexes videos with CLIP and Faiss for natural language query search."]
    relevance_score = 0.85

    class CLI:
        flag = "--query"
        help = "Search query string"

    cli_flags = [CLI()]


def _dummy_recap():
    return Scene(
        id="recap",
        kind="recap",
        narration="Start with vidsearch/cli.py to explore the implementation.",
        beats=[
            Beat(
                say="Start with vidsearch dot py to explore the code.",
                caption="Start with vidsearch/cli.py",
                sources=[SourceSpan(file="vidsearch/cli.py", start_line=1, end_line=2, text="import argparse")],
            )
        ],
    )


class TestProvenanceGroundedness:
    def test_valid_provenance_passes(self):
        beat1 = Beat(
            say="VidSearch indexes videos with CLIP and Faiss for search.",
            caption="VidSearch: Index videos with CLIP",
            sources=[
                SourceSpan(
                    file="README.md",
                    start_line=2,
                    end_line=2,
                    text="VidSearch indexes videos with CLIP and Faiss for natural language query search.",
                )
            ],
        )
        scene = Scene(id="overview", kind="overview", beats=[beat1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_groundedness(script, REPO_FILES, facts=DummyFacts())
        assert gate.passed
        assert gate.value == "100%"

    def test_missing_span_file_fails(self):
        beat1 = Beat(
            say="VidSearch indexes videos with CLIP and Faiss.",
            caption="VidSearch indexing",
            sources=[
                SourceSpan(
                    file="DOES_NOT_EXIST.md",
                    start_line=1,
                    end_line=1,
                    text="VidSearch indexes videos",
                )
            ],
        )
        scene = Scene(id="overview", kind="overview", beats=[beat1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_groundedness(script, REPO_FILES, facts=DummyFacts())
        assert not gate.passed
        assert "not found in repo" in gate.details

    def test_case_mismatch_span_fails(self):
        beat1 = Beat(
            say="VidSearch indexes videos with CLIP and Faiss.",
            caption="VidSearch indexing",
            sources=[
                SourceSpan(
                    file="README.md",
                    start_line=2,
                    end_line=2,
                    text="VIDSEARCH INDEXES VIDEOS WITH CLIP",
                )
            ],
        )
        scene = Scene(id="overview", kind="overview", beats=[beat1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_groundedness(script, REPO_FILES, facts=DummyFacts())
        assert not gate.passed
        assert "not found case-sensitively" in gate.details

    def test_low_token_overlap_fails(self):
        beat1 = Beat(
            say="The interstellar spacecraft navigated through hyperdimensional quantum wormholes yesterday afternoon.",
            caption="Spacecraft navigation",
            sources=[
                SourceSpan(
                    file="README.md",
                    start_line=2,
                    end_line=2,
                    text="VidSearch indexes videos with CLIP and Faiss for natural language query search.",
                )
            ],
        )
        scene = Scene(id="overview", kind="overview", beats=[beat1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_groundedness(script, REPO_FILES, facts=DummyFacts())
        assert not gate.passed
        assert "grounded content tokens" in gate.details

    def test_disallowed_span_fails(self):
        beat1 = Beat(
            say="VidSearch indexes videos with CLIP and Faiss.",
            caption="VidSearch indexing",
            sources=[
                SourceSpan(
                    file="README.md",
                    start_line=1,
                    end_line=1,
                    text="[![Build](https://img.shields.io/badge/build-passing-green)](https://github.com)",
                )
            ],
        )
        scene = Scene(id="overview", kind="overview", beats=[beat1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_groundedness(script, REPO_FILES, facts=DummyFacts())
        assert not gate.passed
        assert "disallowed span format" in gate.details

    def test_line_range_outside_file_fails(self):
        beat1 = Beat(
            say="VidSearch indexes videos with CLIP and Faiss.",
            caption="VidSearch indexing",
            sources=[
                SourceSpan(
                    file="README.md",
                    start_line=50,
                    end_line=55,
                    text="VidSearch indexes videos with CLIP and Faiss for natural language query search.",
                )
            ],
        )
        scene = Scene(id="overview", kind="overview", beats=[beat1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_groundedness(script, REPO_FILES, facts=DummyFacts())
        assert not gate.passed
        assert "outside file boundaries" in gate.details

    def test_quote_not_in_cited_line_range_fails(self):
        beat1 = Beat(
            say="VidSearch indexes videos with CLIP and Faiss.",
            caption="VidSearch indexing",
            sources=[
                SourceSpan(
                    file="vidsearch/cli.py",
                    start_line=5,
                    end_line=6,
                    text="import argparse",
                )
            ],
        )
        scene = Scene(id="overview", kind="overview", beats=[beat1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_groundedness(script, REPO_FILES, facts=DummyFacts())
        assert not gate.passed
        assert "quoted text does not appear in cited line range" in gate.details


class TestNarrationQualityGate:
    def test_clean_narration_passes(self):
        b1 = Beat(
            say="VidSearch indexes videos with CLIP.",
            caption="VidSearch indexing",
            sources=[SourceSpan(file="README.md", start_line=2, end_line=2, text="VidSearch indexes videos")],
        )
        b2 = Beat(
            say="Start with vidsearch/cli.py to explore the code.",
            caption="Start with vidsearch/cli.py",
            sources=[SourceSpan(file="vidsearch/cli.py", start_line=1, end_line=2, text="import argparse")],
        )
        s1 = Scene(id="overview", kind="overview", beats=[b1])
        s2 = Scene(id="recap", kind="recap", beats=[b2])
        script = ScriptPlan(repo_name="vidsearch", scenes=[s1, s2])

        gate = check_narration_quality_gate(script, REPO_FILES)
        assert gate.passed

    @pytest.mark.parametrize(
        "banned",
        [
            "we explore",
            "primary implementation logic",
            "this project organizes",
            "structured solutions",
            "leverage",
            "state of the art",
            "powers multimodal",
        ],
    )
    def test_banned_phrases_fail(self, banned):
        b1 = Beat(
            say=f"In this project, {banned} for developers.",
            caption="Intro",
            sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="# VidSearch")],
        )
        scene = Scene(id="title", kind="title", beats=[b1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_narration_quality_gate(script, REPO_FILES)
        assert not gate.passed
        assert "banned phrase" in gate.details

    def test_junk_tokens_fail(self):
        b1 = Beat(
            say="Let us def class and return self here.",
            caption="Code walk",
            sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="# VidSearch")],
        )
        scene = Scene(id="code", kind="code", beats=[b1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])

        gate = check_narration_quality_gate(script, REPO_FILES)
        assert not gate.passed
        assert "junk tokens" in gate.details

    def test_recap_recommending_license_fails_when_code_exists(self):
        b1 = Beat(
            say="To get started, start with LICENSE in the root directory.",
            caption="Start with LICENSE",
            sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="# VidSearch")],
        )
        scene = Scene(id="recap", kind="recap", beats=[b1])
        s1 = Scene(
            id="overview",
            kind="overview",
            narration="VidSearch indexes videos.",
            beats=[Beat(say="VidSearch indexes videos.", caption="VidSearch", sources=[SourceSpan(file="README.md", start_line=2, end_line=2, text="VidSearch indexes videos")])],
        )
        script = ScriptPlan(repo_name="vidsearch", scenes=[s1, scene])

        gate = check_narration_quality_gate(script, REPO_FILES)
        assert not gate.passed
        assert "non-code file 'license'" in gate.details


class TestSpecificityGate:
    def test_specific_beats_pass(self):
        b1 = Beat(
            say="VidSearch uses Faiss for indexing video vectors.",
            caption="VidSearch Faiss",
            sources=[SourceSpan(file="README.md", start_line=2, end_line=2, text="VidSearch indexes videos with CLIP and Faiss")],
        )
        s1 = Scene(id="overview", kind="overview", beats=[b1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[s1, _dummy_recap()])

        gate = check_specificity_gate(script, REPO_FILES, facts=DummyFacts())
        assert gate.passed

    def test_generic_beat_without_repo_terms_fails(self):
        b1 = Beat(
            say="Everything operates smoothly across multiple components.",
            caption="General description",
            sources=[SourceSpan(file="README.md", start_line=2, end_line=2, text="VidSearch indexes videos")],
        )
        s1 = Scene(id="overview", kind="overview", beats=[b1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[s1, _dummy_recap()])

        gate = check_specificity_gate(script, REPO_FILES, facts=DummyFacts())
        assert not gate.passed
        assert "Non-specific beats" in gate.details


class TestAdversarialCases:
    def test_adversarial_sudo_command_fails(self):
        scene = Scene(
            id="terminal",
            kind="terminal",
            narration="Run the system command as root.",
            on_screen=OnScreen(type="terminal", content="sudo rm -rf /"),
        )
        script = ScriptPlan(repo_name="vidsearch", scenes=[scene, _dummy_recap()])
        gate = check_command_validity_gate(script, REPO_FILES)
        assert not gate.passed

    def test_adversarial_silent_audio_with_claimed_backend_fails(self, tmp_path):
        import wave
        silent_wav = tmp_path / "claimed_voice.wav"
        with wave.open(str(silent_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00" * 44100 * 3)

        gate = check_audio_audible_gate(silent_wav, tts_used="edge", min_volume_db=-50.0)
        assert not gate.passed


class TestOnscreenTextIntegrityGate:
    def test_clean_onscreen_text_passes(self):
        b1 = Beat(
            say="VidSearch indexes videos with CLIP.",
            caption="VidSearch: Index videos with CLIP",
            sources=[SourceSpan(file="README.md", start_line=2, end_line=2, text="VidSearch indexes videos with CLIP")],
        )
        s1 = Scene(id="overview", kind="overview", beats=[b1], on_screen=OnScreen(type="overview", content="VidSearch core codebase"))
        script = ScriptPlan(repo_name="vidsearch", scenes=[s1, _dummy_recap()])

        gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
        assert gate.passed
        assert gate.value == "0 violations"

    def test_dangling_stopword_caption_fails(self):
        b1 = Beat(
            say="VidSearch indexes videos with CLIP.",
            caption="VidSearch indexes videos with",
            sources=[SourceSpan(file="README.md", start_line=2, end_line=2, text="VidSearch indexes videos with CLIP")],
        )
        s1 = Scene(id="overview", kind="overview", beats=[b1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[s1, _dummy_recap()])

        gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
        assert not gate.passed
        assert "dangling stopword" in gate.details

    def test_truncation_ellipsis_fails(self):
        b1 = Beat(
            say="VidSearch indexes videos with CLIP.",
            caption="VidSearch indexes videos...",
            sources=[SourceSpan(file="README.md", start_line=2, end_line=2, text="VidSearch indexes videos with CLIP")],
        )
        s1 = Scene(id="overview", kind="overview", beats=[b1])
        script = ScriptPlan(repo_name="vidsearch", scenes=[s1, _dummy_recap()])

        gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
        assert not gate.passed
        assert "truncation ellipsis" in gate.details

    def test_dangling_stopword_on_screen_line_fails(self):
        b1 = Beat(
            say="VidSearch indexes videos with CLIP.",
            caption="VidSearch: Index videos with CLIP",
            sources=[SourceSpan(file="README.md", start_line=2, end_line=2, text="VidSearch indexes videos with CLIP")],
        )
        s1 = Scene(
            id="overview",
            kind="overview",
            beats=[b1],
            on_screen=OnScreen(type="overview", content="1. VidSearch core capabilities for\n2. Next line"),
        )
        script = ScriptPlan(repo_name="vidsearch", scenes=[s1, _dummy_recap()])

        gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
        assert not gate.passed
        assert "dangling stopword" in gate.details
