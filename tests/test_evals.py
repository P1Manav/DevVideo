"""
Unit tests for the eval module.

Tests every gate with:
- At least one test that passes
- At least one test that triggers the gate (fails)
Plus tests for soft metrics (domain relevance warning, clarity skipped indicator).
"""

import pytest
from src.schema import Scene, ScriptPlan, OnScreen, Evidence
from src.evals import (
    check_duration_gate,
    check_secret_gate,
    check_groundedness,
    check_command_validity_gate,
    check_drift_gate,
    check_overflow_gate,
    compute_domain_relevance,
    run_eval,
)


def _make_scene(
    id: str,
    narration: str = "A valid narration about AI video understanding and retrieval systems.",
    content: str = "Content",
    content_type: str = "text",
    quote: str = "fixture repo",
    file: str = "README.md",
) -> Scene:
    return Scene(
        id=id,
        narration=narration,
        on_screen=OnScreen(type=content_type, content=content),
        evidence=Evidence(file=file, quote=quote),
    )


REPO_FILES = {
    "README.md": "# Fixture Repo\nThis is a fixture repo for testing.\n```bash\npip install -r requirements.txt\npython main.py\n```",
    "docs/usage.md": "Usage guide:\npip install -r requirements.txt\npython main.py",
}


class TestDurationGate:
    def test_under_60s(self):
        gate = check_duration_gate(45.0)
        assert gate.passed

    def test_exactly_60s(self):
        gate = check_duration_gate(60.0)
        assert gate.passed

    def test_over_60s_triggers_gate(self):
        gate = check_duration_gate(60.1)
        assert not gate.passed
        assert "60.1s" in gate.value


class TestSecretGate:
    def test_no_secrets(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        gate = check_secret_gate(script, raw_input="Normal prompt with no keys")
        assert gate.passed
        assert gate.value == "0"

    def test_secrets_in_narration_triggers_gate(self):
        scene = _make_scene("leaked_narr", narration="Use api_key = sk-abc123def456ghi789jkl012mno345pqr678 to auth.")
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])
        gate = check_secret_gate(script)
        assert not gate.passed
        assert int(gate.value) > 0

    def test_secrets_in_on_screen_triggers_gate(self):
        scene = _make_scene("leaked_screen", content="export GITHUB_TOKEN=ghp_123456789012345678901234567890123456")
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])
        gate = check_secret_gate(script)
        assert not gate.passed

    def test_secrets_in_raw_llm_input_triggers_gate(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        raw_prompt = "Prompt containing secret: AKIA1234567890123456 in raw text"
        gate = check_secret_gate(script, raw_input=raw_prompt)
        assert not gate.passed


class TestGroundednessGate:
    def test_fully_grounded_100_percent_passes(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        gate = check_groundedness(script, REPO_FILES)
        assert gate.passed
        assert gate.value == "100%"

    def test_ungrounded_quote_triggers_gate(self):
        scene = _make_scene("bad_quote", quote="invented hallucinatory text not in repo")
        script = ScriptPlan(repo_name="test", scenes=[_make_scene("s1"), scene])
        gate = check_groundedness(script, REPO_FILES)
        assert not gate.passed
        assert gate.value == "50%"

    def test_missing_evidence_file_triggers_gate(self):
        scene = _make_scene("bad_file", file="NONEXISTENT.md", quote="anything")
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])
        gate = check_groundedness(script, REPO_FILES)
        assert not gate.passed

class TestCommandValidityGate:
    def test_verbatim_commands_pass(self):
        scene1 = _make_scene("s1", content="pip install -r requirements.txt", content_type="code")
        scene2 = _make_scene("s2", content="python main.py", content_type="code")
        script = ScriptPlan(repo_name="test", scenes=[scene1, scene2])
        gate = check_command_validity_gate(script, REPO_FILES)
        assert gate.passed
        assert "100%" in gate.value

    def test_no_commands_passes(self):
        scene1 = _make_scene("s1", content="Plain explanatory text without shell commands", content_type="text")
        scene2 = _make_scene("s2", content="More explanatory text", content_type="text")
        script = ScriptPlan(repo_name="test", scenes=[scene1, scene2])
        gate = check_command_validity_gate(script, REPO_FILES)
        assert gate.passed

    def test_unverified_command_triggers_gate(self):
        scene1 = _make_scene("s1", content="pip install malicious-unknown-package\nrm -rf /", content_type="code")
        script = ScriptPlan(repo_name="test", scenes=[scene1, _make_scene("s2")])
        gate = check_command_validity_gate(script, REPO_FILES)
        assert not gate.passed
        assert "malicious-unknown-package" in gate.details


class TestDriftGate:
    def test_no_drift_passes(self):
        gate = check_drift_gate([5.0, 5.0], [5.0, 5.0], tolerance=0.5)
        assert gate.passed
        assert gate.value == "0.00s"

    def test_within_tolerance_passes(self):
        gate = check_drift_gate([5.0, 5.0], [4.6, 5.3], tolerance=0.5)
        assert gate.passed

    def test_exceeds_tolerance_triggers_gate(self):
        gate = check_drift_gate([5.0, 5.0], [4.3, 5.0], tolerance=0.5)
        assert not gate.passed
        assert gate.value == "0.70s"


class TestOverflowGate:
    def test_no_overflow_passes(self):
        gate = check_overflow_gate([])
        assert gate.passed

    def test_overflow_triggers_gate(self):
        gate = check_overflow_gate(["intro", "architecture"])
        assert not gate.passed
        assert "2 overflowing scenes" in gate.value


class TestDomainRelevanceMetric:
    def test_high_relevance_no_warning(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", "This is about AI video understanding and retrieval engine with embedding search."),
                _make_scene("s2", "Neural model for video search indexing pipeline query."),
            ],
        )
        score = compute_domain_relevance(script)
        assert score >= 0.5

    def test_low_relevance_triggers_soft_warning(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", "This is about baking chocolate cookies and cupcakes at home."),
                _make_scene("s2", "How to plant roses and water them in springtime."),
            ],
        )
        report = run_eval(
            script=script,
            repo_files=REPO_FILES,
            video_duration=35.0,
            backend_used="offline",
        )
        assert report.metrics["domain_relevance"] < 0.5
        assert "low_relevance" in report.metrics.get("domain_relevance_warning", "")
        # Soft metric does not fail hard gates on its own
        assert report.all_gates_passed is True


class TestClarityMetric:
    def test_clarity_skipped_without_llm(self):
        script = ScriptPlan(repo_name="test", scenes=[_make_scene("s1"), _make_scene("s2")])
        report = run_eval(script, REPO_FILES, 40.0, backend_used="offline")
        assert report.metrics["clarity"] == "clarity: skipped (no LLM)"

    def test_clarity_evaluated_with_claude(self):
        script = ScriptPlan(repo_name="test", scenes=[_make_scene("s1"), _make_scene("s2")])
        report = run_eval(script, REPO_FILES, 40.0, backend_used="claude")
        assert report.metrics["clarity"] == "evaluated (LLM judge)"


class TestRunEvalOverall:
    def test_all_gates_pass(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", content="pip install -r requirements.txt", content_type="code"),
                _make_scene("s2", content="python main.py", content_type="code"),
            ],
        )
        report = run_eval(
            script=script,
            repo_files=REPO_FILES,
            video_duration=45.0,
            planned_durations=[5.0, 5.0],
            audio_durations=[5.0, 5.0],
            backend_requested="offline",
            backend_used="offline",
        )
        assert report.all_gates_passed is True
        assert len(report.gates) >= 5

    def test_single_gate_failure_fails_overall(self):
        # Trigger duration gate (> 60s)
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        report = run_eval(
            script=script,
            repo_files=REPO_FILES,
            video_duration=65.0,  # Exceeds 60s
            planned_durations=[5.0, 5.0],
            audio_durations=[5.0, 5.0],
        )
        assert report.all_gates_passed is False
        failed = [g.name for g in report.gates if not g.passed]
        assert "duration" in failed
