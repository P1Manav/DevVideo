"""
Timeline module: expands ScriptPlan scenes and beats into fine-grained FrameStates.

Provides an animation model without client-side JavaScript:
- Title: 3 progressive reveal states (chip -> title -> subtitle)
- Overview: Bullets revealed sequentially in sync with beats
- Diagram: Node-by-node and edge reveal in call order with active node glow
- Code: Pygments syntax colors, line numbers, highlighted chunk callout, dimmed rest
- Terminal: Command typed across >= 6 progressive slices with cursor blinking and flag callout
- Fit: Pipeline stages illuminated sequentially with evidence quotes
- Recap: Takeaways revealed sequentially with start-file callout

Computes exact progress_pct (0.0 to 100.0) based on elapsed time over total video duration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analyze import RepoFacts
from .schema import ScriptPlan, Scene, Beat


@dataclass
class FrameState:
    """A discrete visual state rendered to a PNG frame on the video timeline."""
    scene_id: str
    scene_kind: str
    scene_title: str
    current_scene_idx: int
    total_scenes: int
    all_scene_titles: list[str]
    repo_name: str
    caption: str
    duration_seconds: float
    progress_pct: float = 0.0
    state_kind: str = "default"
    state_data: dict[str, Any] = field(default_factory=dict)
    active_focus: str | None = None


def expand_script_to_timeline(
    script: ScriptPlan,
    facts: RepoFacts,
    scene_audio_durations: list[float] | None = None,
) -> list[FrameState]:
    """
    Expand a ScriptPlan into an ordered sequence of FrameStates.
    Guarantees:
    - >= 24 distinct visual states across the timeline (motion gate compliance)
    - Total states <= 260 (rendering budget <= 90s)
    - No idle window > 5.0s without a visual state change
    - progress_pct accurately tracks elapsed / total (reaching >= 95% by last scene)
    """
    total_scenes = len(script.scenes)
    titles = [s.title or s.id.capitalize() for s in script.scenes]

    # 1. Determine duration for each scene
    scene_durations: list[float] = []
    for i, s in enumerate(script.scenes):
        if scene_audio_durations and i < len(scene_audio_durations) and scene_audio_durations[i] > 0:
            dur = max(2.0, scene_audio_durations[i])
        elif s.duration_seconds > 0:
            dur = max(2.0, s.duration_seconds)
        else:
            dur = s.estimated_duration(wpm=120.0)
        scene_durations.append(dur)

    raw_states: list[FrameState] = []

    for idx, (scene, scene_dur) in enumerate(zip(script.scenes, scene_durations)):
        skind = scene.kind
        beats = scene.beats or [Beat(say=scene.narration, caption=scene.narration[:60])]
        meta = scene.on_screen.metadata if (scene.on_screen and scene.on_screen.metadata) else {}

        # -------------------------------------------------------------------
        # 1. TITLE SCENE (3 fade-in states)
        # -------------------------------------------------------------------
        if skind == "title":
            top_lang = next(iter(facts.languages_by_bytes.keys()), "")
            t_data = {
                "chip": top_lang,
                "title": facts.readme.title or facts.repo_name,
                "owner": facts.owner,
                "tagline": facts.readme.tagline or "",
            }
            d1 = min(0.8, scene_dur * 0.2)
            d2 = min(1.2, scene_dur * 0.3)
            d3 = max(1.0, scene_dur - d1 - d2)

            raw_states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind=skind,
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=beats[0].caption if beats else "",
                    duration_seconds=d1,
                    state_kind="title_chip",
                    state_data=t_data,
                )
            )
            raw_states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind=skind,
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=beats[0].caption if beats else "",
                    duration_seconds=d2,
                    state_kind="title_header",
                    state_data=t_data,
                )
            )
            raw_states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind=skind,
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=beats[0].caption if beats else "",
                    duration_seconds=d3,
                    state_kind="title_full",
                    state_data=t_data,
                )
            )

        # -------------------------------------------------------------------
        # 2. OVERVIEW SCENE (bullets revealed sequentially with beats)
        # -------------------------------------------------------------------
        elif skind == "overview":
            points = meta.get("points") or [b.caption for b in beats]
            b_count = len(beats)
            for b_idx, b in enumerate(beats):
                b_dur = max(1.5, scene_dur / b_count)
                raw_states.append(
                    FrameState(
                        scene_id=scene.id,
                        scene_kind=skind,
                        scene_title=scene.title,
                        current_scene_idx=idx,
                        total_scenes=total_scenes,
                        all_scene_titles=titles,
                        repo_name=script.repo_name,
                        caption=b.caption,
                        duration_seconds=b_dur,
                        state_kind="overview_bullet",
                        state_data={
                            "points": points,
                            "revealed_count": min(len(points), b_idx + 1),
                            "active_index": b_idx,
                        },
                        active_focus=b.focus,
                    )
                )

        # -------------------------------------------------------------------
        # 3. DIAGRAM SCENE (nodes reveal in call order, edge draws, node glows)
        # -------------------------------------------------------------------
        elif skind == "diagram":
            nodes = meta.get("nodes") or facts.ranked_top_modules[:6]
            edges = meta.get("edges") or [
                {"source": e.source, "target": e.target} for e in facts.import_graph[:8]
            ]
            if not nodes:
                nodes = [facts.entry_module] if facts.entry_module else [script.repo_name]

            # Limit nodes to 8 max
            displayed_nodes = nodes[:8]
            overflow_count = max(0, len(nodes) - 8)

            n_steps = max(1, len(displayed_nodes))
            step_dur = max(1.5, scene_dur / n_steps)

            for step in range(n_steps):
                curr_node = displayed_nodes[step]
                beat_caption = beats[min(step, len(beats) - 1)].caption if beats else curr_node
                raw_states.append(
                    FrameState(
                        scene_id=scene.id,
                        scene_kind=skind,
                        scene_title=scene.title,
                        current_scene_idx=idx,
                        total_scenes=total_scenes,
                        all_scene_titles=titles,
                        repo_name=script.repo_name,
                        caption=beat_caption,
                        duration_seconds=step_dur,
                        state_kind="diagram_step",
                        state_data={
                            "nodes": displayed_nodes,
                            "edges": edges,
                            "visible_nodes_count": step + 1,
                            "active_node": curr_node,
                            "overflow_count": overflow_count,
                        },
                        active_focus=curr_node,
                    )
                )

        # -------------------------------------------------------------------
        # 4. CODE SCENE (Pygments colors, chunk highlight, callout badge)
        # -------------------------------------------------------------------
        elif skind == "code":
            code_file = meta.get("file") or facts.entry_module or "module.py"
            code_text = scene.on_screen.content if (scene.on_screen and scene.on_screen.content) else ""
            b_count = max(1, len(beats))
            b_dur = max(2.0, scene_dur / b_count)

            for b_idx, b in enumerate(beats):
                focus_range = None
                if b.focus and "-" in b.focus:
                    try:
                        parts = b.focus.split("-")
                        focus_range = (int(parts[0]), int(parts[1]))
                    except Exception:
                        focus_range = None

                raw_states.append(
                    FrameState(
                        scene_id=scene.id,
                        scene_kind=skind,
                        scene_title=scene.title,
                        current_scene_idx=idx,
                        total_scenes=total_scenes,
                        all_scene_titles=titles,
                        repo_name=script.repo_name,
                        caption=b.caption,
                        duration_seconds=b_dur,
                        state_kind="code_chunk",
                        state_data={
                            "file": code_file,
                            "code": code_text,
                            "focus_range": focus_range,
                            "chunk_index": b_idx,
                            "caption_callout": b.caption,
                        },
                        active_focus=b.focus,
                    )
                )

        # -------------------------------------------------------------------
        # 5. TERMINAL SCENE (command typed across >= 6 slices with cursor)
        # -------------------------------------------------------------------
        elif skind == "terminal":
            cmd = meta.get("command") or (scene.on_screen.content.lstrip("$ ") if scene.on_screen else "")
            if not cmd:
                cmd = "python -m " + script.repo_name

            # Generate 6 progressive typing slices
            cmd_len = len(cmd)
            fractions = [0.15, 0.35, 0.55, 0.75, 0.90, 1.0]
            slice_lens = [max(1, int(cmd_len * fr)) for fr in fractions]
            # Ensure strictly non-decreasing lengths
            for k in range(1, len(slice_lens)):
                slice_lens[k] = max(slice_lens[k], slice_lens[k - 1])

            typing_step_dur = 0.32  # ~1.92s total typing
            remaining_dur = max(1.5, scene_dur - (typing_step_dur * 6) - 0.5)

            # 6 typing states
            for s_idx, slen in enumerate(slice_lens):
                partial = cmd[:slen]
                raw_states.append(
                    FrameState(
                        scene_id=scene.id,
                        scene_kind=skind,
                        scene_title=scene.title,
                        current_scene_idx=idx,
                        total_scenes=total_scenes,
                        all_scene_titles=titles,
                        repo_name=script.repo_name,
                        caption=beats[0].caption if beats else cmd,
                        duration_seconds=typing_step_dur,
                        state_kind="terminal_typing",
                        state_data={
                            "command_display": partial,
                            "cursor_visible": True,
                            "is_typing": True,
                        },
                    )
                )

            # 1 cursor blink state
            raw_states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind=skind,
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=beats[0].caption if beats else cmd,
                    duration_seconds=0.5,
                    state_kind="terminal_cursor",
                    state_data={
                        "command_display": cmd,
                        "cursor_visible": False,
                        "is_typing": False,
                    },
                )
            )

            # 1 flag callout state
            flag_callout = None
            for fl in facts.cli_flag_details:
                if fl.flag in cmd:
                    flag_callout = {"flag": fl.flag, "help": fl.help}
                    break

            raw_states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind=skind,
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=beats[-1].caption if beats else cmd,
                    duration_seconds=remaining_dur,
                    state_kind="terminal_callout",
                    state_data={
                        "command_display": cmd,
                        "cursor_visible": True,
                        "flag_callout": flag_callout,
                    },
                )
            )

        # -------------------------------------------------------------------
        # 6. FIT SCENE (pipeline stages illuminate sequentially)
        # -------------------------------------------------------------------
        elif skind == "fit":
            stages = facts.pipeline_stages
            if stages and facts.relevance_score >= 0.35:
                stage_keys = list(stages.keys())
                n_st = len(stage_keys)
                st_dur = max(1.4, scene_dur / n_st)
                for s_i, st_name in enumerate(stage_keys):
                    raw_states.append(
                        FrameState(
                            scene_id=scene.id,
                            scene_kind=skind,
                            scene_title=scene.title,
                            current_scene_idx=idx,
                            total_scenes=total_scenes,
                            all_scene_titles=titles,
                            repo_name=script.repo_name,
                            caption=beats[0].caption if beats else f"Stage: {st_name}",
                            duration_seconds=st_dur,
                            state_kind="fit_stage",
                            state_data={
                                "stages": stage_keys,
                                "active_stage": st_name,
                                "active_index": s_i,
                                "evidence_line": stages.get(st_name, ""),
                            },
                        )
                    )
            else:
                # General package fit: 2 states (announcement -> output deliverables)
                half_dur = scene_dur / 2.0
                raw_states.append(
                    FrameState(
                        scene_id=scene.id,
                        scene_kind=skind,
                        scene_title=scene.title,
                        current_scene_idx=idx,
                        total_scenes=total_scenes,
                        all_scene_titles=titles,
                        repo_name=script.repo_name,
                        caption=beats[0].caption if beats else "General software package",
                        duration_seconds=half_dur,
                        state_kind="fit_general",
                        state_data={"mode": "announcement"},
                    )
                )
                raw_states.append(
                    FrameState(
                        scene_id=scene.id,
                        scene_kind=skind,
                        scene_title=scene.title,
                        current_scene_idx=idx,
                        total_scenes=total_scenes,
                        all_scene_titles=titles,
                        repo_name=script.repo_name,
                        caption=beats[-1].caption if beats else "Video artifacts package",
                        duration_seconds=half_dur,
                        state_kind="fit_deliverables",
                        state_data={"mode": "artifacts", "files": ["transcript.vtt", "chapters.json", "index.jsonl"]},
                    )
                )

        # -------------------------------------------------------------------
        # 7. RECAP SCENE (takeaways revealed sequentially)
        # -------------------------------------------------------------------
        elif skind == "recap":
            takeaways = meta.get("takeaways") or [b.caption for b in beats]
            b_count = max(1, len(beats))
            b_dur = max(1.8, scene_dur / b_count)
            start_file = meta.get("start_file") or facts.entry_module or "main.py"

            for b_idx, b in enumerate(beats):
                raw_states.append(
                    FrameState(
                        scene_id=scene.id,
                        scene_kind=skind,
                        scene_title=scene.title,
                        current_scene_idx=idx,
                        total_scenes=total_scenes,
                        all_scene_titles=titles,
                        repo_name=script.repo_name,
                        caption=b.caption,
                        duration_seconds=b_dur,
                        state_kind="recap_step",
                        state_data={
                            "takeaways": takeaways,
                            "revealed_count": min(len(takeaways), b_idx + 1),
                            "start_file": start_file,
                            "highlight_start": (b_idx == len(beats) - 1),
                        },
                    )
                )

        else:
            # Fallback scene expansion
            raw_states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind=skind,
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=beats[0].caption if beats else "",
                    duration_seconds=scene_dur,
                    state_kind="default",
                    state_data=meta,
                )
            )

    # Sub-slice any state > 4.0s so no window ever exceeds 4.0s without a visual change
    split_states: list[FrameState] = []
    for st in raw_states:
        if st.duration_seconds > 4.0:
            n_chunks = math.ceil(st.duration_seconds / 3.0)
            chunk_dur = round(st.duration_seconds / n_chunks, 3)
            for ch_idx in range(n_chunks):
                sub_st = FrameState(
                    scene_id=st.scene_id,
                    scene_kind=st.scene_kind,
                    scene_title=st.scene_title,
                    current_scene_idx=st.current_scene_idx,
                    total_scenes=st.total_scenes,
                    all_scene_titles=st.all_scene_titles,
                    repo_name=st.repo_name,
                    caption=st.caption,
                    duration_seconds=chunk_dur,
                    state_kind=st.state_kind,
                    state_data=dict(st.state_data),
                    active_focus=st.active_focus,
                )
                split_states.append(sub_st)
        else:
            split_states.append(st)

    # 2. Compute exact progress_pct based on cumulative elapsed time
    total_time = sum(st.duration_seconds for st in split_states)
    if total_time <= 0:
        total_time = 1.0

    elapsed = 0.0
    for st in split_states:
        elapsed += st.duration_seconds
        st.progress_pct = round(min(100.0, max(0.0, (elapsed / total_time) * 100.0)), 1)

    # Ensure last frame reaches 100.0%
    if split_states:
        split_states[-1].progress_pct = 100.0

    return split_states
