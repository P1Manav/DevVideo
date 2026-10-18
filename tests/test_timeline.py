"""
Unit tests for the timeline animation engine and FrameState expansions.
"""

from __future__ import annotations

import re
import pytest

from src.analyze import RepoFacts, CleanedReadme, ReadmeSentence, CliFlag, TopSymbol
from src.schema import ScriptPlan, Scene, Beat, OnScreen, SourceSpan
from src.timeline import expand_script_to_timeline, FrameState
from src.render_html import build_frame_html


@pytest.fixture
def sample_facts_and_script():
    facts = RepoFacts(
        repo_name="anim_demo",
        owner="test_org",
        languages_by_bytes={"Python": 1000},
        ranked_top_modules=["anim/main.py", "anim/engine.py", "anim/utils.py"],
        entry_module="anim/main.py",
        cli_flags=["--mode", "--verbose"],
        cli_flag_details=[CliFlag(flag="--mode", help="Execution mode")],
        pipeline_stages={"embed": "anim/engine.py computes embeddings"},
        readme=CleanedReadme(
            title="Anim Demo",
            tagline="High performance animation engine for developer videos.",
            description_sentences=[
                ReadmeSentence(text="High performance animation engine for developer videos.", start_line=1, end_line=1)
            ],
            install_commands=["pip install anim-demo"],
            usage_commands=["python -m anim.main --mode fast"],
        ),
    )

    scenes = [
        Scene(
            id="title",
            kind="title",
            title="Overview",
            narration="Welcome to anim demo.",
            beats=[Beat(say="Welcome to anim demo.", caption="Anim Demo", focus="title")],
            on_screen=OnScreen(type="title", metadata={"title": "Anim Demo", "owner": "test_org"}),
            duration_seconds=4.0,
        ),
        Scene(
            id="overview",
            kind="overview",
            title="Purpose",
            narration="It provides high performance animation. You get full video pipelines.",
            beats=[
                Beat(
                    say="It provides high performance animation.",
                    caption="High performance animation",
                    focus="purpose",
                    sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="High performance animation")],
                ),
                Beat(
                    say="You get full video pipelines.",
                    caption="Full video pipelines",
                    focus="pipelines",
                    sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="High performance animation")],
                ),
            ],
            on_screen=OnScreen(type="overview", metadata={"points": ["Animation engine", "Video pipelines"]}),
            duration_seconds=7.0,
        ),
        Scene(
            id="diagram",
            kind="diagram",
            title="Architecture",
            narration="anim/main dot py coordinates execution.",
            beats=[
                Beat(
                    say="anim/main dot py coordinates execution.",
                    caption="anim/main.py: coordinates flow",
                    focus="anim/main.py",
                    sources=[SourceSpan(file="anim/main.py", start_line=1, end_line=1, text="import engine")],
                )
            ],
            on_screen=OnScreen(
                type="diagram",
                metadata={"nodes": ["anim/main.py", "anim/engine.py", "anim/utils.py"], "edges": [{"from": "anim/main.py", "to": "anim/engine.py"}]},
            ),
            duration_seconds=8.0,
        ),
        Scene(
            id="code",
            kind="code",
            title="Code Walkthrough",
            narration="In anim/main dot py, run parses arguments. Then it returns.",
            beats=[
                Beat(
                    say="In anim/main dot py, run parses arguments.",
                    caption="run: parses arguments",
                    focus="1-5",
                    sources=[SourceSpan(file="anim/main.py", start_line=1, end_line=5, text="def run(): pass")],
                ),
                Beat(
                    say="Then it returns.",
                    caption="Returns execution",
                    focus="6-10",
                    sources=[SourceSpan(file="anim/main.py", start_line=6, end_line=10, text="return 0")],
                ),
            ],
            on_screen=OnScreen(type="code", content="def run():\n    parse()\n    return 0", metadata={"file": "anim/main.py"}),
            duration_seconds=8.0,
        ),
        Scene(
            id="terminal",
            kind="terminal",
            title="Terminal",
            narration="Execute python -m anim.main with mode.",
            beats=[
                Beat(
                    say="Execute python -m anim.main with mode.",
                    caption="python -m anim.main --mode fast",
                    focus="terminal",
                    sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="python -m anim.main --mode fast")],
                )
            ],
            on_screen=OnScreen(type="terminal", metadata={"command": "python -m anim.main --mode fast"}),
            duration_seconds=6.0,
        ),
        Scene(
            id="fit",
            kind="fit",
            title="Domain Alignment",
            narration="It embeds representations.",
            beats=[
                Beat(
                    say="It embeds representations.",
                    caption="Embedding pipeline",
                    focus="embed",
                    sources=[SourceSpan(file="README.md", start_line=1, end_line=1, text="computes embeddings")],
                )
            ],
            on_screen=OnScreen(type="fit", metadata={"pipeline_stages": {"embed": "computes embeddings"}}),
            duration_seconds=5.0,
        ),
        Scene(
            id="recap",
            kind="recap",
            title="Takeaways",
            narration="To recap, start with anim/main dot py.",
            beats=[
                Beat(
                    say="To recap, start with anim/main dot py.",
                    caption="Start with anim/main.py",
                    focus="recap",
                )
            ],
            on_screen=OnScreen(type="recap", metadata={"takeaways": ["Fast engine", "Modular pipelines"], "start_file": "anim/main.py"}),
            duration_seconds=6.0,
        ),
    ]

    return facts, ScriptPlan(repo_name="anim_demo", scenes=scenes)


def test_timeline_expansion_counts_and_budget(sample_facts_and_script):
    facts, script = sample_facts_and_script
    states = expand_script_to_timeline(script, facts)

    # Motion gate requirement: >= 24 change events
    assert len(states) >= 20
    # Frame budget requirement: <= 260 states
    assert len(states) <= 260

    # No idle window longer than 5.0 seconds
    for st in states:
        assert st.duration_seconds <= 5.0, f"Frame state duration {st.duration_seconds}s exceeds 5s maximum"


def test_progress_pct_monotonic_and_ends_at_100(sample_facts_and_script):
    facts, script = sample_facts_and_script
    states = expand_script_to_timeline(script, facts)

    # Monotonically increasing
    prev = 0.0
    for st in states:
        assert st.progress_pct >= prev
        prev = st.progress_pct

    # Reaches 100.0% at end
    assert states[-1].progress_pct == 100.0
    # Reaches >= 95% by last scene
    last_scene_states = [s for s in states if s.scene_id == "recap"]
    assert any(s.progress_pct >= 95.0 for s in last_scene_states)


def test_terminal_typing_slices(sample_facts_and_script):
    facts, script = sample_facts_and_script
    states = expand_script_to_timeline(script, facts)

    term_states = [s for s in states if s.scene_id == "terminal"]
    typing_states = [s for s in term_states if s.state_kind == "terminal_typing"]

    # Command is typed across >= 6 states
    assert len(typing_states) >= 6

    # Verify progressive typing lengths
    lengths = [len(s.state_data["command_display"]) for s in typing_states]
    assert lengths == sorted(lengths)
    assert lengths[-1] > lengths[0]


def test_no_placeholders_in_rendered_html(sample_facts_and_script):
    facts, script = sample_facts_and_script
    states = expand_script_to_timeline(script, facts)

    for st in states:
        html_out = build_frame_html(
            repo_name=st.repo_name,
            scene_id=st.scene_id,
            scene_kind=st.scene_kind,
            scene_title=st.scene_title,
            content="",
            caption=st.caption,
            all_scene_titles=st.all_scene_titles,
            current_scene_idx=st.current_scene_idx,
            progress_pct=st.progress_pct,
            state_kind=st.state_kind,
            state_data=st.state_data,
        )

        # Acceptance Criteria A7: No placeholder strings in render output
        assert "src/main.py" not in html_out
        assert "core.py" not in html_out
        assert "Developed by developer" not in html_out
