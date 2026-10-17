"""
Unit tests for the schema module.
"""

import pytest
from pydantic import ValidationError

from src.schema import Scene, ScriptPlan, OnScreen, Evidence


class TestScene:
    def test_valid_scene(self):
        scene = Scene(
            id="intro",
            narration="This is a valid narration for the intro scene of the video.",
            on_screen=OnScreen(type="text", content="Hello World"),
            evidence=Evidence(file="README.md", quote="some quote"),
        )
        assert scene.id == "intro"

    def test_invalid_id_spaces(self):
        with pytest.raises(ValidationError):
            Scene(
                id="has spaces",
                narration="This is a valid narration for testing purposes.",
                on_screen=OnScreen(type="text", content="test"),
                evidence=Evidence(file="f.md", quote="q"),
            )

    def test_narration_too_short(self):
        with pytest.raises(ValidationError):
            Scene(
                id="short",
                narration="Too short",
                on_screen=OnScreen(type="text", content="test"),
                evidence=Evidence(file="f.md", quote="q"),
            )

    def test_empty_narration(self):
        with pytest.raises(ValidationError):
            Scene(
                id="empty",
                narration="          ",  # whitespace only but >= 10 chars
                on_screen=OnScreen(type="text", content="test"),
                evidence=Evidence(file="f.md", quote="q"),
            )

    def test_invalid_on_screen_type(self):
        with pytest.raises(ValidationError):
            Scene(
                id="bad_type",
                narration="This is a valid narration for testing purposes.",
                on_screen=OnScreen(type="video", content="test"),
                evidence=Evidence(file="f.md", quote="q"),
            )


class TestScriptPlan:
    def _make_scene(self, id: str, word_count: int = 25) -> Scene:
        narration = " ".join(["word"] * word_count)
        return Scene(
            id=id,
            narration=narration,
            on_screen=OnScreen(type="text", content="content"),
            evidence=Evidence(file="README.md", quote="quote"),
        )

    def test_valid_script(self):
        script = ScriptPlan(
            repo_name="test-repo",
            scenes=[self._make_scene("s1"), self._make_scene("s2")],
        )
        assert len(script.scenes) == 2

    def test_too_few_scenes(self):
        with pytest.raises(ValidationError):
            ScriptPlan(
                repo_name="test-repo",
                scenes=[self._make_scene("s1")],
            )

    def test_duration_estimate(self):
        # 4 scenes x 25 words = 100 words. At 150 wpm = 40 seconds
        script = ScriptPlan(
            repo_name="test-repo",
            scenes=[self._make_scene(f"s{i}") for i in range(4)],
        )
        duration = script.estimated_duration_seconds()
        assert 35 <= duration <= 45
