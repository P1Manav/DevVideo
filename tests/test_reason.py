"""
Unit tests for the reason module and verify-revise loop.

Tests:
- Bad first draft -> feedback provided -> success on retry
- Retries exhausted -> fallback to next planner
- All planners failing -> safe degraded plan produced (never UnboundLocalError)
- Comprehensive verification checks (evidence, quote, command validity, banned words)
"""

import pytest

from src.analyze import RepoFacts, CleanedReadme
from src.reason import reason_and_plan, verify_script_plan, build_degraded_plan
from src.schema import Beat, Evidence, OnScreen, Scene, ScriptPlan
from tests.helpers.scripted_planner import ScriptedPlanner


@pytest.fixture
def sample_facts():
    return RepoFacts(
        repo_name="toy_repo",
        owner="developer",
        readme=CleanedReadme(
            title="Toy Repo",
            description="A demonstration repository for testing reasoning loops.",
            sections={"Usage": "pip install toy-repo"},
            code_fences=["pip install toy-repo"],
        ),
        tree=["README.md", "src/main.py"],
        entry_points=["src/main.py"],
    )


@pytest.fixture
def repo_files():
    return {
        "README.md": "# Toy Repo\nA demonstration repository for testing reasoning loops.\n\nUsage:\npip install toy-repo",
        "src/main.py": "def main():\n    print('hello toy')\n",
    }


def make_valid_plan():
    return ScriptPlan(
        repo_name="toy_repo",
        scenes=[
            Scene(
                id="intro",
                kind="title",
                title="Intro",
                beats=[Beat(say="Welcome to toy repo, a demonstration repository for testing.", caption="Welcome to toy repo")],
                on_screen=OnScreen(type="title", content="Toy Repo"),
                evidence=Evidence(file="README.md", quote="demonstration repository"),
            ),
            Scene(
                id="terminal",
                kind="terminal",
                title="Terminal",
                beats=[Beat(say="Run pip install toy-repo to install the package.", caption="pip install toy-repo")],
                on_screen=OnScreen(type="terminal", content="pip install toy-repo"),
                evidence=Evidence(file="README.md", quote="pip install toy-repo"),
            ),
        ]
    )


def make_bad_plan_missing_file():
    return ScriptPlan(
        repo_name="toy_repo",
        scenes=[
            Scene(
                id="intro",
                kind="title",
                title="Intro",
                beats=[Beat(say="Welcome to toy repo demonstration.", caption="Toy repo intro")],
                on_screen=OnScreen(type="title", content="Toy Repo"),
                evidence=Evidence(file="NONEXISTENT.md", quote="demonstration repository"),
            ),
            Scene(
                id="terminal",
                kind="terminal",
                title="Terminal",
                beats=[Beat(say="Run pip install toy-repo to install.", caption="pip install toy-repo")],
                on_screen=OnScreen(type="terminal", content="pip install toy-repo"),
                evidence=Evidence(file="README.md", quote="pip install toy-repo"),
            ),
        ]
    )


def make_bad_plan_banned_words():
    return ScriptPlan(
        repo_name="toy_repo",
        scenes=[
            Scene(
                id="intro",
                kind="title",
                title="Intro",
                beats=[Beat(say="This provides a modular and robust architecture.", caption="Modular architecture")],
                on_screen=OnScreen(type="title", content="Toy Repo"),
                evidence=Evidence(file="README.md", quote="demonstration repository"),
            ),
            Scene(
                id="terminal",
                kind="terminal",
                title="Terminal",
                beats=[Beat(say="Run pip install toy-repo.", caption="pip install toy-repo")],
                on_screen=OnScreen(type="terminal", content="pip install toy-repo"),
                evidence=Evidence(file="README.md", quote="pip install toy-repo"),
            ),
        ]
    )


class TestReasoningLoop:
    def test_bad_first_draft_revises_on_retry(self, sample_facts, repo_files):
        """Bad first draft receives feedback and succeeds on retry."""
        bad_plan = make_bad_plan_missing_file()
        good_plan = make_valid_plan()

        scripted = ScriptedPlanner([bad_plan, good_plan])

        plan, history, planner_used, fallback = reason_and_plan(
            facts=sample_facts,
            repo_files=repo_files,
            planners=[scripted],
        )

        assert scripted.call_count == 2
        assert len(scripted.received_feedbacks) == 2
        assert scripted.received_feedbacks[0] is None
        assert scripted.received_feedbacks[1] is not None
        assert any("NONEXISTENT.md" in fb for fb in scripted.received_feedbacks[1])
        assert planner_used == "scripted"
        assert len(plan.scenes) == 2
        assert any("attempt_2: verification passed" in h for h in history)

    def test_retries_exhausted_falls_back_to_next_planner(self, sample_facts, repo_files):
        """Planner failing all retries cascades to fallback planner."""
        always_bad = ScriptedPlanner([make_bad_plan_missing_file()] * 4)
        always_bad.name = "always_bad"

        fallback_good = ScriptedPlanner([make_valid_plan()])
        fallback_good.name = "fallback_good"

        plan, history, planner_used, fallback_reason = reason_and_plan(
            facts=sample_facts,
            repo_files=repo_files,
            planners=[always_bad, fallback_good],
        )

        assert planner_used == "fallback_good"
        assert "always_bad failed verification" in fallback_reason
        assert plan.scenes[0].evidence.file == "README.md"

    def test_all_planners_fail_produces_degraded_plan(self, sample_facts, repo_files):
        """All planners failing degrades gracefully with zero UnboundLocalError or crash."""
        bad1 = ScriptedPlanner([make_bad_plan_missing_file()] * 3)
        bad1.name = "bad1"

        plan, history, planner_used, fallback = reason_and_plan(
            facts=sample_facts,
            repo_files=repo_files,
            planners=[bad1],
        )

        assert plan is not None
        assert planner_used == "offline_degraded"
        assert len(plan.scenes) >= 2
        assert any("degraded" in h for h in history)

    def test_banned_buzzword_triggers_rejection(self, repo_files):
        """Scenes containing banned buzzwords are flagged during verification."""
        bad_plan = make_bad_plan_banned_words()
        ok, errors = verify_script_plan(bad_plan, repo_files)
        assert ok is False
        assert any("banned buzzwords" in err for err in errors)
