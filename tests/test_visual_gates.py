"""
Tests for Phase 4, 5, and 9 visual gates:
- code_highlight_focus
- code_window_visible
- decoration_free
- onscreen_matches_voice
Including adversarial failing cases.
"""
from __future__ import annotations
import pytest
from src.schema import ScriptPlan, Scene, Beat, OnScreen, SourceSpan, Evidence
from src.evals.visual_gates import (
    check_code_highlight_focus_gate,
    check_code_window_visible_gate,
    check_decoration_free_gate,
    check_onscreen_matches_voice_gate,
)
from src.evals.text_gates import check_onscreen_text_integrity_gate


def _make_dummy_title_scene() -> Scene:
    return Scene(
        id="title",
        kind="title",
        title="Title",
        narration="Welcome to demo.",
        beats=[
            Beat(
                say="Welcome to demo.",
                caption="Welcome to demo.",
                focus="demo",
                sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="Welcome to demo.")],
                start_seconds=0.0,
                end_seconds=2.0,
            )
        ],
        on_screen=OnScreen(
            type="title",
            content="Demo",
            metadata={"repo": "demo"},
        ),
        evidence=Evidence(file="README.md", quote="Welcome to demo."),
        duration_seconds=2.0,
    )


def _make_code_scene(focus: str, content: str, filepath: str = "src/core.py") -> Scene:
    return Scene(
        id="code_1",
        kind="code",
        title="Code Walkthrough",
        narration="Here main initializes the retrieval engine.",
        beats=[
            Beat(
                say="Here main initializes the retrieval engine.",
                caption="Main initializes the engine.",
                focus=focus,
                sources=[SourceSpan(file=filepath, start_line=1, end_line=5, text="def main():\n    pass")],
                start_seconds=0.0,
                end_seconds=4.0,
            )
        ],
        on_screen=OnScreen(
            type="code",
            content=content,
            metadata={"file": filepath, "lang": "python"},
        ),
        evidence=Evidence(file=filepath if filepath else "README.md", quote="def main(): pass"),
        duration_seconds=4.0,
    )


def test_code_highlight_focus_adversarial():
    # 10 lines of code
    code_content = "\n".join([f"line_{i} = do_work({i})" for i in range(10)])

    # Passing case: lines 1-3 highlighted (3/10 = 30% <= 60%, count <= 5)
    valid_scene = _make_code_scene(focus="1-3", content=code_content)
    valid_script = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), valid_scene])
    gate = check_code_highlight_focus_gate(valid_script)
    assert gate.passed, f"Expected pass but got: {gate.details}"

    # Adversarial case 1: 8 of 10 lines highlighted (80% > 60%)
    adv_scene_overfocus = _make_code_scene(focus="1-8", content=code_content)
    adv_script_1 = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), adv_scene_overfocus])
    gate_adv1 = check_code_highlight_focus_gate(adv_script_1)
    assert not gate_adv1.passed
    assert "exceeding 60% limit" in gate_adv1.details or "violations" in gate_adv1.value

    # Adversarial case 2: > 5 rows highlighted
    adv_scene_toomany = _make_code_scene(focus="1-6", content="\n".join([f"l{i}=1" for i in range(15)]))
    adv_script_2 = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), adv_scene_toomany])
    gate_adv2 = check_code_highlight_focus_gate(adv_script_2)
    assert not gate_adv2.passed


def test_code_window_visible_adversarial():
    # Passing case: normal function with real logic
    valid_code = "def load(name: str):\n    model = build_model(name)\n    checkpoint = fetch(name)\n    model.load(checkpoint)\n    return model"
    valid_scene = _make_code_scene(focus="1-3", content=valid_code, filepath="src/clip.py")
    valid_script = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), valid_scene])
    gate = check_code_window_visible_gate(valid_script)
    assert gate.passed, f"Expected pass but got: {gate.details}"

    # Adversarial case 1: Docstring-only window
    docstring_code = '"""\nParameters\n----------\nname : str\n    Model name to load\nReturns\n-------\nmodel : Model\n"""'
    adv_scene_doc = _make_code_scene(focus="1-3", content=docstring_code, filepath="src/clip.py")
    adv_script_doc = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), adv_scene_doc])
    gate_doc = check_code_window_visible_gate(adv_script_doc)
    assert not gate_doc.passed
    assert "docstring" in gate_doc.details

    # Adversarial case 2: Missing or generic filepath
    adv_scene_nofile = _make_code_scene(focus="1-3", content=valid_code, filepath="src/clip.py")
    adv_scene_nofile.on_screen.metadata["file"] = "Source Code"
    adv_script_nofile = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), adv_scene_nofile])
    gate_nofile = check_code_window_visible_gate(adv_script_nofile)
    assert not gate_nofile.passed


def test_decoration_free_adversarial():
    valid_scene = Scene(
        id="term_1",
        kind="terminal",
        title="Installation",
        narration="Install it with pip.",
        beats=[Beat(say="Install it with pip.", caption="Install with pip.", focus=None, sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="pip install demo")], start_seconds=0, end_seconds=3)],
        on_screen=OnScreen(type="terminal", content="pip install demo", metadata={"command": "pip install demo"}),
        evidence=Evidence(file="README.md", quote="pip install demo"),
        duration_seconds=3.0,
    )
    valid_script = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), valid_scene])
    gate = check_decoration_free_gate(valid_script)
    assert gate.passed

    # Adversarial case: Frame HTML contains fake synthesizing text
    fake_html_map = {"term_1": '<div class="terminal-container"><span class="synthesizing">SYNTHESIZING COMMAND (94%)</span></div>'}
    gate_adv = check_decoration_free_gate(valid_script, frame_html_map=fake_html_map)
    assert not gate_adv.passed
    assert "SYNTHESIZING" in gate_adv.details


def test_onscreen_matches_voice_adversarial():
    # Passing case: overview points are honest architectural takeaways
    valid_overview = Scene(
        id="overview",
        kind="overview",
        title="Overview",
        narration="VidSearch indexes video clips for dense semantic search.",
        beats=[Beat(say="VidSearch indexes video clips.", caption="Indexes video clips.", focus=None, sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="VidSearch indexes video clips.")], start_seconds=0, end_seconds=3)],
        on_screen=OnScreen(type="overview", content="Points", metadata={"points": ["Extracts frames from video clips", "Builds fast nearest neighbor index"]}),
        evidence=Evidence(file="README.md", quote="VidSearch indexes video clips."),
        duration_seconds=3.0,
    )
    valid_script = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), valid_overview])
    gate = check_onscreen_matches_voice_gate(valid_script)
    assert gate.passed

    # Adversarial case: overview points include news items with date prefixes
    adv_overview = Scene(
        id="overview",
        kind="overview",
        title="Overview",
        narration="VidSearch indexes video clips.",
        beats=[Beat(say="VidSearch indexes video clips.", caption="Indexes video clips.", focus=None, sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="VidSearch indexes video clips.")], start_seconds=0, end_seconds=3)],
        on_screen=OnScreen(type="overview", content="Points", metadata={"points": ["[July 2022] OpenCLIP released larger models", "Feature 2"]}),
        evidence=Evidence(file="README.md", quote="VidSearch indexes video clips."),
        duration_seconds=3.0,
    )
    adv_script = ScriptPlan(repo_name="demo", scenes=[_make_dummy_title_scene(), adv_overview])
    gate_adv = check_onscreen_matches_voice_gate(adv_script)
    assert not gate_adv.passed
    assert "news item" in gate_adv.details


def test_onscreen_text_integrity_dangling_cut_adversarial():
    # Adversarial case: caption cut at dangling preposition/conjunction/particle
    bad_caption_scene = Scene(
        id="title",
        kind="title",
        title="Overview",
        narration="VidSearch is a lightweight multimodal video understanding and retrieval engine.",
        beats=[
            Beat(
                say="VidSearch is a lightweight multimodal video understanding and retrieval engine.",
                caption="VidSearch: VidSearch is a lightweight multimodal video understanding",  # Cut mid-clause
                focus="vidsearch",
                sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="VidSearch is a lightweight multimodal video understanding and retrieval engine.")],
                start_seconds=0.0,
                end_seconds=4.0,
            )
        ],
        on_screen=OnScreen(type="title", content="VidSearch", metadata={"points": []}),
        evidence=Evidence(file="README.md", quote="VidSearch is a lightweight multimodal video understanding and retrieval engine."),
        duration_seconds=4.0,
    )
    bad_script = ScriptPlan(repo_name="demo", scenes=[bad_caption_scene, _make_dummy_title_scene()])
    gate = check_onscreen_text_integrity_gate(bad_script)
    # Must fail because caption duplicates the name 'VidSearch: VidSearch' or has dangling ending
    assert not gate.passed

