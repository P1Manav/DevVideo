"""
Unit tests for the eval package and regression tests for E1-E5 and R1.

Tests every gate with:
- At least one test that passes
- At least one test that triggers the gate (fails)
- Regression tests for WHAT WAS WRONG: E1, E2, E3, E4, E5, R1
- Bounded repair loop tests
"""

import pytest
from pathlib import Path
from src.schema import Scene, ScriptPlan, OnScreen, Evidence
from src.evals import (
    check_duration_gate,
    check_av_sync_gate,
    check_drift_gate,
    check_audio_audible_gate,
    check_secret_gate,
    check_secret_leaks_gate,
    check_groundedness,
    check_code_verbatim_gate,
    check_command_validity_gate,
    check_overflow_gate,
    check_frames_valid_gate,
    compute_domain_relevance,
    evaluate_clarity,
    run_eval,
)
from src.repair import RepairManager


def _make_scene(
    id: str,
    narration: str = "This fixture repo is designed for testing video retrieval pipelines.",
    content: str = "Content",
    content_type: str = "text",
    quote: str = "This is a fixture repo for testing.",
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


class TestDurationMarginGate:
    def test_under_55s_passes_without_warning(self):
        from src.evals.media_gates import check_duration_margin_gate
        gate = check_duration_margin_gate(52.0, target_margin=55.0, hard_limit=60.0)
        assert gate.passed
        assert "WARNING" not in gate.details

    def test_between_55s_and_60s_warns_non_blocking(self):
        from src.evals.media_gates import check_duration_margin_gate
        gate = check_duration_margin_gate(56.5, target_margin=55.0, hard_limit=60.0)
        assert gate.passed  # non-blocking
        assert "WARNING" in gate.details

    def test_over_60s_fails_duration_margin(self):
        from src.evals.media_gates import check_duration_margin_gate
        gate = check_duration_margin_gate(61.2, target_margin=55.0, hard_limit=60.0)
        assert not gate.passed
        assert "FAILED" in gate.details


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

    def test_ingest_recorded_secret_detected_independently(self):
        script = ScriptPlan(repo_name="test", scenes=[_make_scene("s1", narration="Connecting with secret_db_pass_xyz123"), _make_scene("s2")])
        gate = check_secret_leaks_gate(script, ingest_secrets={"secret_db_pass_xyz123"})
        assert not gate.passed
        assert "contains recorded secret" in gate.details


class TestGroundednessGate:
    def test_fully_grounded_100_percent_passes(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        gate = check_groundedness(script, REPO_FILES)
        assert gate.passed
        assert gate.value == "100%"

    def test_e1_short_quote_fails_gate(self):
        """Regression test for E1: quote='a' or trivial short quote must fail."""
        scene = _make_scene("short_quote", quote="a")
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])
        gate = check_groundedness(script, REPO_FILES)
        assert not gate.passed
        assert "quote too short" in gate.details

    def test_e1_case_sensitive_check(self):
        """Regression test for E1: case difference must fail groundedness."""
        scene = _make_scene("case_diff", quote="THIS IS A FIXTURE REPO FOR TESTING.")
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])
        gate = check_groundedness(script, REPO_FILES)
        assert not gate.passed
        assert "quote not found case-sensitively" in gate.details

    def test_missing_evidence_file_triggers_gate(self):
        scene = _make_scene("bad_file", file="NONEXISTENT.md", quote="This is a fixture repo for testing.")
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

    def test_e2_zero_commands_reports_not_applicable(self):
        """Regression test for E2: zero commands reports 'not applicable', not vacuous pass."""
        scene1 = _make_scene("s1", content="Plain explanatory text without shell commands", content_type="text")
        scene2 = _make_scene("s2", content="More explanatory text without shell commands", content_type="text")
        script = ScriptPlan(repo_name="test", scenes=[scene1, scene2])
        gate = check_command_validity_gate(script, REPO_FILES)
        assert gate.passed
        assert "not applicable" in gate.value

    def test_e2_sudo_command_detected_and_fails(self):
        """Regression test for E2: sudo prefix command must be detected and validated."""
        scene = _make_scene("s1", content="sudo pip install evil", content_type="code")
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])
        gate = check_command_validity_gate(script, REPO_FILES)
        assert not gate.passed
        assert "sudo pip install evil" in gate.details


class TestAvSyncGate:
    def test_r1_real_voice_sync_passes(self):
        """Regression test for R1: realistic scene audio and video segments in sync pass gate."""
        # Simulated 175 wpm audio lengths matching scene video segments
        scene_video = [6.2, 7.8, 8.1, 7.0]
        scene_audio = [6.25, 7.75, 8.12, 7.04]  # drift <= 0.05s
        gate = check_av_sync_gate(scene_video, scene_audio, tolerance_scene=0.15)
        assert gate.passed

    def test_exceeds_scene_tolerance_fails(self):
        scene_video = [5.0, 5.0]
        scene_audio = [5.0, 5.25]  # drift 0.25s > 0.15s
        gate = check_av_sync_gate(scene_video, scene_audio, tolerance_scene=0.15)
        assert not gate.passed


class TestOverflowGate:
    def test_no_overflow_passes(self):
        gate = check_overflow_gate([])
        assert gate.passed

    def test_overflow_triggers_gate(self):
        gate = check_overflow_gate(["intro", "architecture"])
        assert not gate.passed
        assert "2 overflowing scenes" in gate.value


class TestDomainRelevanceMetric:
    def test_high_relevance(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[
                _make_scene("s1", "This is about AI video understanding and retrieval engine with embedding search."),
                _make_scene("s2", "Neural model for video search indexing pipeline query."),
            ],
        )
        score = compute_domain_relevance(script)
        assert score >= 0.5

    def test_e3_maintain_does_not_match_ai_substring(self):
        """Regression test for E3: 'maintain' must not match 'ai' via word boundary check."""
        css_text = "This CSS stylesheet is easy to maintain and style buttons."
        score = compute_domain_relevance(css_text)
        assert score == 0.0


class TestClarityMetric:
    def test_e4_clarity_skipped_without_llm(self):
        """Regression test for E4: clarity is exactly 'skipped' unless real judge evaluated."""
        script = ScriptPlan(repo_name="test", scenes=[_make_scene("s1"), _make_scene("s2")])
        res = evaluate_clarity(script, llm_used="offline")
        assert res == "skipped"


class TestRepairManager:
    def test_e5_repair_invalid_command(self):
        """Regression test for E5: invalid command is automatically repaired or dropped."""
        manager = RepairManager(max_attempts=2)
        scene = _make_scene("term", content="$ pip install evil\n$ python main.py", content_type="code")
        script = ScriptPlan(repo_name="test", scenes=[scene, _make_scene("s2")])

        repaired = manager.repair_invalid_commands(script, REPO_FILES)
        assert repaired is True
        assert "evil" not in scene.on_screen.content
        assert manager.attempts == 1

    def test_repair_duration_faster_speech_then_drop_recap(self):
        """Test bounded 2-attempt duration repair."""
        manager = RepairManager(max_attempts=2)
        class DummyTTS:
            speed = 165

        tts = DummyTTS()
        recap_scene = _make_scene("recap", narration="Here is a full summary recap of the project workflow.")
        recap_scene.kind = "recap"
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), recap_scene],
        )

        # Attempt 1: Speed increase
        action1 = manager.repair_duration(script, tts_backend=tts)
        assert action1 == "speed_increased"
        assert tts.speed == int(165 * 1.08)

        # Attempt 2: Drop recap
        action2 = manager.repair_duration(script, tts_backend=tts)
        assert action2 == "dropped_recap"
        assert len(script.scenes) == 1

        # Attempt 3: Exceeded
        action3 = manager.repair_duration(script, tts_backend=tts)
        assert action3 == "max_attempts_exceeded"


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
            scene_durations=[5.0, 5.0],
            audio_durations=[5.0, 5.0],
            backend_requested="offline",
            backend_used="offline",
            tts_used="silent",
        )
        assert report.all_gates_passed is True
        assert len(report.gates) >= 5

    def test_single_gate_failure_fails_overall(self):
        script = ScriptPlan(
            repo_name="test",
            scenes=[_make_scene("s1"), _make_scene("s2")],
        )
        report = run_eval(
            script=script,
            repo_files=REPO_FILES,
            video_duration=65.0,  # Exceeds 60s
            scene_durations=[5.0, 5.0],
            audio_durations=[5.0, 5.0],
            tts_used="silent",
        )
        assert report.all_gates_passed is False
        failed = [g.name for g in report.gates if not g.passed]
        assert "duration" in failed
