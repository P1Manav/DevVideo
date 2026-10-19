"""
Timeline scene animations: title, overview, diagram, fit, and recap state generation.
"""

from __future__ import annotations

from typing import Any

from ..analyze import RepoFacts
from ..schema import Beat, Scene, ScriptPlan
from .layout import FrameState


def expand_title(
    scene: Scene,
    idx: int,
    total_scenes: int,
    titles: list[str],
    script: ScriptPlan,
    facts: RepoFacts,
    scene_dur: float,
    beats: list[Beat],
) -> list[FrameState]:
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

    return [
        FrameState(
            scene_id=scene.id,
            scene_kind="title",
            scene_title=scene.title,
            current_scene_idx=idx,
            total_scenes=total_scenes,
            all_scene_titles=titles,
            repo_name=script.repo_name,
            caption=beats[0].caption if beats else "",
            duration_seconds=d1,
            state_kind="title_chip",
            state_data=t_data,
        ),
        FrameState(
            scene_id=scene.id,
            scene_kind="title",
            scene_title=scene.title,
            current_scene_idx=idx,
            total_scenes=total_scenes,
            all_scene_titles=titles,
            repo_name=script.repo_name,
            caption=beats[0].caption if beats else "",
            duration_seconds=d2,
            state_kind="title_header",
            state_data=t_data,
        ),
        FrameState(
            scene_id=scene.id,
            scene_kind="title",
            scene_title=scene.title,
            current_scene_idx=idx,
            total_scenes=total_scenes,
            all_scene_titles=titles,
            repo_name=script.repo_name,
            caption=beats[0].caption if beats else "",
            duration_seconds=d3,
            state_kind="title_full",
            state_data=t_data,
        ),
    ]


def expand_overview(
    scene: Scene,
    idx: int,
    total_scenes: int,
    titles: list[str],
    script: ScriptPlan,
    scene_dur: float,
    beats: list[Beat],
    meta: dict[str, Any],
) -> list[FrameState]:
    points = meta.get("points") or [b.caption for b in beats]
    if not points:
        points = [b.caption for b in beats]
    n_points = max(1, len(points))
    step_dur = max(1.2, scene_dur / n_points)

    states: list[FrameState] = []
    for p_idx in range(n_points):
        beat_caption = beats[min(p_idx, len(beats) - 1)].caption if beats else points[p_idx]
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="overview",
                scene_title=scene.title,
                current_scene_idx=idx,
                total_scenes=total_scenes,
                all_scene_titles=titles,
                repo_name=script.repo_name,
                caption=beat_caption,
                duration_seconds=step_dur,
                state_kind="overview_bullet",
                state_data={
                    "points": points,
                    "revealed_count": p_idx + 1,
                    "active_index": p_idx,
                },
                active_focus=beats[min(p_idx, len(beats) - 1)].focus if beats else None,
            )
        )
    return states


def expand_diagram(
    scene: Scene,
    idx: int,
    total_scenes: int,
    titles: list[str],
    script: ScriptPlan,
    facts: RepoFacts,
    scene_dur: float,
    beats: list[Beat],
    meta: dict[str, Any],
) -> list[FrameState]:
    nodes = meta.get("nodes") or facts.ranked_top_modules[:6]
    edges = meta.get("edges") or [
        {"source": e.source, "target": e.target} for e in facts.import_graph[:8]
    ]
    if not nodes:
        nodes = [facts.entry_module] if facts.entry_module else [script.repo_name]

    displayed_nodes = nodes[:8]
    overflow_count = max(0, len(nodes) - 8)
    n_steps = max(1, len(displayed_nodes))
    step_dur = max(1.3, scene_dur / n_steps)

    states: list[FrameState] = []
    for step in range(n_steps):
        curr_node = displayed_nodes[step]
        beat_caption = beats[min(step, len(beats) - 1)].caption if beats else curr_node
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="diagram",
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
    return states


def expand_fit(
    scene: Scene,
    idx: int,
    total_scenes: int,
    titles: list[str],
    script: ScriptPlan,
    facts: RepoFacts,
    scene_dur: float,
    beats: list[Beat],
) -> list[FrameState]:
    stages = facts.pipeline_stages
    states: list[FrameState] = []
    if stages and facts.relevance_score >= 0.35:
        stage_keys = list(stages.keys())
        n_st = len(stage_keys)
        st_dur = max(1.2, scene_dur / n_st)
        for s_i, st_name in enumerate(stage_keys):
            states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind="fit",
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
        half_dur = scene_dur / 2.0
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="fit",
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
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="fit",
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
    return states


def expand_recap(
    scene: Scene,
    idx: int,
    total_scenes: int,
    titles: list[str],
    script: ScriptPlan,
    facts: RepoFacts,
    scene_dur: float,
    beats: list[Beat],
    meta: dict[str, Any],
) -> list[FrameState]:
    takeaways = meta.get("takeaways") or [b.caption for b in beats]
    t_list = takeaways[:3]
    start_file = meta.get("start_file") or facts.entry_module or "main.py"
    n_recap_steps = len(t_list) + 1
    r_dur = max(1.2, scene_dur / n_recap_steps)

    states: list[FrameState] = []
    for step in range(len(t_list)):
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="recap",
                scene_title=scene.title,
                current_scene_idx=idx,
                total_scenes=total_scenes,
                all_scene_titles=titles,
                repo_name=script.repo_name,
                caption=t_list[step],
                duration_seconds=r_dur,
                state_kind="recap_step",
                state_data={
                    "takeaways": t_list,
                    "revealed_count": step + 1,
                    "start_file": start_file,
                    "highlight_start": False,
                },
            )
        )

    final_caption = beats[-1].caption if beats else f"Start with {start_file}"
    states.append(
        FrameState(
            scene_id=scene.id,
            scene_kind="recap",
            scene_title=scene.title,
            current_scene_idx=idx,
            total_scenes=total_scenes,
            all_scene_titles=titles,
            repo_name=script.repo_name,
            caption=final_caption,
            duration_seconds=r_dur,
            state_kind="recap_step",
            state_data={
                "takeaways": t_list,
                "revealed_count": len(t_list),
                "start_file": start_file,
                "highlight_start": True,
            },
        )
    )
    return states
