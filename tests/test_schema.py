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


class TestProvenanceSchema:
    def test_beat_with_sources(self):
        from src.schema import Beat, SourceSpan
        span = SourceSpan(file="src/cli.py", start_line=10, end_line=15, text="parser.add_argument('--query')")
        beat = Beat(say="We add query flag", caption="Query flag", focus="10-15", sources=[span])
        assert len(beat.sources) == 1
        assert beat.sources[0].file == "src/cli.py"

    def test_factual_scene_without_sources_raises_error(self):
        from src.schema import Beat
        with pytest.raises(ValidationError):
            Scene(
                id="code",
                kind="code",
                narration="This is a test narration for the code scene here.",
                beats=[Beat(say="We add query flag", caption="Query flag", sources=[])],
            )

    def test_title_and_recap_without_sources_pass(self):
        from src.schema import Beat
        title_scene = Scene(
            id="title",
            kind="title",
            narration="Welcome to test repo explainer video.",
            beats=[Beat(say="Welcome to test repo explainer video.", caption="Welcome", sources=[])],
        )
        assert title_scene.kind == "title"
        recap_scene = Scene(
            id="recap",
            kind="recap",
            narration="To recap, this is the summary of test repo.",
            beats=[Beat(say="To recap, this is the summary of test repo.", caption="Recap", sources=[])],
        )
        assert recap_scene.kind == "recap"

    def test_source_migration_from_evidence(self):
        scene = Scene(
            id="diagram",
            kind="diagram",
            narration="The architecture connects five modules together.",
            evidence=Evidence(file="main.py", quote="import cli"),
        )
        assert len(scene.beats) == 1
        assert len(scene.beats[0].sources) == 1
        assert scene.beats[0].sources[0].file == "main.py"
        assert scene.beats[0].sources[0].text == "import cli"

