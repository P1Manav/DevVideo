"""
Regression tests for Phase 3: Captions, VTT, and On-Screen Text Integrity (N2).
Asserts that all captions, subtitles, bullets, and terminal commands are complete clauses
with balanced syntax and zero dangling truncations.
"""
from __future__ import annotations

import pytest
from src.evals.text_gates import check_onscreen_text_integrity_gate
from src.schema import Beat, OnScreen, Scene, ScriptPlan, SourceSpan


class DummyFacts:
    repo_name = "vidsearch"
    top_symbols = []
    module_docstrings = []
    ranked_top_modules = []
    cli_flags = []
    dependencies = []
    pipeline_stages = {}
    tree = ["README.md"]
    readme_file = "README.md"


def _make_script(caption: str, on_screen_content: str = "Grounded text line") -> ScriptPlan:
    b = Beat(
        say="VidSearch indexes video segments for search.",
        caption=caption,
        sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="VidSearch indexes video segments for search")],
    )
    s = Scene(
        id="overview",
        kind="overview",
        beats=[b],
        on_screen=OnScreen(type="overview", content=on_screen_content),
    )
    s2 = Scene(
        id="recap",
        kind="recap",
        beats=[Beat(say="VidSearch recap summary.", caption="Recap: VidSearch summary", sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="VidSearch summary")])],
        on_screen=OnScreen(type="recap", content="1. Summary"),
    )
    return ScriptPlan(repo_name="vidsearch", scenes=[s, s2])


def test_reject_unbalanced_quotes():
    """N2 regression: Unbalanced quote in command/caption (e.g. --query \"sunset)."""
    script = _make_script(caption='Run: python -m vidsearch.cli --query "sunset')
    gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
    assert not gate.passed
    assert "unbalanced" in gate.details


def test_reject_dangling_adjective_natural():
    """N2 regression: Trailing adjective without noun (e.g. 'in natural')."""
    script = _make_script(caption="It can be instructed in natural")
    gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
    assert not gate.passed
    assert "dangling stopword" in gate.details


def test_reject_dangling_participle_matching():
    """N2 regression: Trailing participle without noun (e.g. 'rank matching')."""
    script = _make_script(caption="query vector index and rank matching")
    gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
    assert not gate.passed
    assert "dangling stopword" in gate.details


def test_reject_partial_clause_without_verb():
    """N2 regression: Multi-word phrase without a verb (partial clause)."""
    script = _make_script(caption="multimodal video retrieval engine architecture overview")
    gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
    assert not gate.passed
    assert "partial clause" in gate.details


def test_reject_trailing_ellipsis():
    """N2 regression: Trailing truncation ellipsis."""
    script = _make_script(caption="VidSearch indexes videos...")
    gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
    assert not gate.passed
    assert "ellipsis" in gate.details


def test_clean_complete_clauses_pass():
    """Clean complete clause captions pass onscreen text integrity."""
    script = _make_script(caption="VidSearch indexes videos with CLIP")
    gate = check_onscreen_text_integrity_gate(script, facts=DummyFacts())
    assert gate.passed
