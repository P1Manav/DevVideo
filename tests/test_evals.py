"""
Unit tests for the eval module.
"""

import pytest
from src.schema import Scene, ScriptPlan, OnScreen, Evidence
from src.evals import (
    check_duration_gate,
    check_secret_gate,
    check_groundedness,
    check_drift_gate,
    compute_domain_relevance,
    run_eval,
)


def _make_scene(id: str, narration: str = "A valid narration about AI video understanding and retrieval systems.") -> Scene:
    return Scene(
        id=id,
        narration=narration,
        on_screen=OnScreen(type="text", content="Content"),
        evidence=Evidence(file="README.md", quote="fixture repo"),
    )


REPO_FILES = {
    "README.md": "# Fixture Repo\nThis is a fixture repo for testing.",
}


class TestDurationGate:
    def test_under_60s(self):
        gate = check_duration_gate(45.0)
        assert gate.passed

    def test_exactly_60s(self):
        gate = check_duration_gate(60.0)
        assert gate.passed

    def test_over_60s(self):
        gate = check_duration_gate(61.0)
        assert not gate.passed


class TestSecretGate:
    def test_no_secrets(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        gate = check_secret_gate(script)
        assert gate.passed

    def test_has_secrets(self):
        scene = Scene(
            id="leaked",
            narration="Use api_key = sk-abc123def456ghi789jkl012mno345pqr678 to authenticate with the service.",
            on_screen=OnScreen(type="text", content="Test"),
            evidence=Evidence(file="README.md", quote="fixture repo"),
        )
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])
        gate = check_secret_gate(script)
        assert not gate.passed


class TestGroundedness:
    def test_fully_grounded(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        gate = check_groundedness(script, REPO_FILES)
        assert gate.passed

    def test_ungrounded(self):
        scene = Scene(
            id="bad",
            narration="A narration about something not in the repo at all.",
            on_screen=OnScreen(type="text", content="Test"),
            evidence=Evidence(file="NONEXISTENT.md", quote="not there"),
        )
        script = ScriptPlan(repo_name="test", scenes=[scene, scene])
        gate = check_groundedness(script, REPO_FILES)
        assert not gate.passed


class TestDriftGate:
    def test_no_drift(self):
        gate = check_drift_gate([5.0, 5.0], [5.0, 5.0])
        assert gate.passed

    def test_within_tolerance(self):
        gate = check_drift_gate([5.0, 5.0], [4.5, 5.5], tolerance=2.0)
        assert gate.passed

    def test_exceeds_tolerance(self):
        gate = check_drift_gate([5.0, 5.0], [2.0, 5.0], tolerance=2.0)
        assert not gate.passed


class TestDomainRelevance:
    def test_high_relevance(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", "This is about AI video understanding and retrieval engine with embedding search."),
                _make_scene("s2", "Neural model for video search indexing pipeline query."),
            ],
        )
        score = compute_domain_relevance(script)
        assert score > 0.5

    def test_low_relevance(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", "This is about cooking recipes and gardening tips for beginners."),
                _make_scene("s2", "How to bake a cake and plant flowers in your garden in spring."),
            ],
        )
        score = compute_domain_relevance(script)
        assert score < 0.5


class TestRunEval:
    def test_all_gates_pass(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        report = run_eval(
            script=script,
            repo_files=REPO_FILES,
            video_duration=45.0,
            scene_durations=[5.0, 5.0],
            audio_durations=[5.0, 5.0],
            backend_requested="mock",
            backend_used="mock",
        )
        assert report.all_gates_passed
