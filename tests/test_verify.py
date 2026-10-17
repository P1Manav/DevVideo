"""
Unit tests for the verify module.
"""

import pytest
from pathlib import Path

from src.schema import Scene, ScriptPlan, OnScreen, Evidence
from src.verify import verify_script


def _make_scene(id: str, evidence_file: str = "README.md", quote: str = "fixture repo") -> Scene:
    return Scene(
        id=id,
        narration="This is a test narration with enough words for the scene to be valid and interesting.",
        on_screen=OnScreen(type="text", content="Test content"),
        evidence=Evidence(file=evidence_file, quote=quote),
    )


# Simulate the repo_files dict
REPO_FILES = {
    "README.md": "# Fixture Repo\nThis is a fixture repo for testing.",
    "docs/usage.md": "## Usage\nInstall and run the project.",
}


class TestVerifyScript:
    def test_valid_script_passes(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", "README.md", "fixture repo"),
                _make_scene("s2", "docs/usage.md", "install"),
            ],
        )
        result = verify_script(script, REPO_FILES)
        assert result.ok

    def test_missing_evidence_file(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", "NONEXISTENT.md", "whatever"),
                _make_scene("s2", "README.md", "fixture repo"),
            ],
        )
        result = verify_script(script, REPO_FILES)
        assert not result.ok
        assert any("not found" in e for e in result.errors)

    def test_quote_not_found(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", "README.md", "this text is not in the file at all xyz"),
                _make_scene("s2", "README.md", "fixture repo"),
            ],
        )
        result = verify_script(script, REPO_FILES)
        assert not result.ok
        assert any("quote" in e.lower() for e in result.errors)

    def test_secret_in_narration(self):
        scene = Scene(
            id="leaked",
            narration="The API key is sk-abc123def456ghi789jkl012mno345pqr678 and it works great for testing.",
            on_screen=OnScreen(type="text", content="Test"),
            evidence=Evidence(file="README.md", quote="fixture repo"),
        )
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])
        result = verify_script(script, REPO_FILES)
        assert not result.ok
        assert any("secret" in e.lower() for e in result.errors)

    def test_duration_too_long(self):
        # Create multiple scenes that together exceed duration limit
        # Each narration is under 600 chars but total words push past max_duration
        def long_scene(sid: str) -> Scene:
            return Scene(
                id=sid,
                narration=" ".join(["word"] * 80),  # 80 words, ~32s at 150wpm, under 600 chars
                on_screen=OnScreen(type="text", content="Test"),
                evidence=Evidence(file="README.md", quote="fixture repo"),
            )

        script = ScriptPlan(
            repo_name="test",
            scenes=[long_scene("s1"), long_scene("s2"), long_scene("s3")],  # ~96s total
        )
        result = verify_script(script, REPO_FILES, max_duration=58.0)
        assert not result.ok
        assert any("duration" in e.lower() for e in result.errors)

