"""
Timeline scene animations: code window and terminal typing state generation.
"""

from __future__ import annotations

from typing import Any

from ..analyze import RepoFacts
from ..schema import Beat, Scene, ScriptPlan
from .layout import FrameState


def expand_code(
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
    code_file = meta.get("file") or facts.entry_module or "module.py"
    code_text = scene.on_screen.content if (scene.on_screen and scene.on_screen.content) else ""
    sym_match = next((s for s in facts.top_symbols if s.file == code_file), None)
    code_start_line = sym_match.start_line if sym_match else 1
    b_count = max(1, len(beats))
    b_dur = max(2.0, scene_dur / b_count)

    states: list[FrameState] = []
    for b_idx, b in enumerate(beats):
        focus_range = None
        if b.focus and "-" in b.focus:
            try:
                parts = b.focus.split("-")
                focus_range = (int(parts[0]), int(parts[1]))
            except Exception:
                focus_range = None

        if focus_range:
            # Phase 4: Cap highlighted lines to at most 5 rows per beat
            l_start, l_end = focus_range
            if l_end - l_start + 1 > 5:
                l_end = l_start + 4
            focus_range = (l_start, l_end)
        else:
            total_code_l = len(code_text.splitlines()) if code_text else 1
            focus_range = (code_start_line, min(code_start_line + 2, code_start_line + total_code_l - 1))

        if focus_range and (focus_range[1] - focus_range[0] >= 2) and b_dur > 2.8:
            l_start, l_end = focus_range
            step1_end = min(l_start + 1, l_end)
            step2_end = l_start + max(1, (l_end - l_start) * 2 // 3)
            d1 = round(b_dur * 0.32, 2)
            d2 = round(b_dur * 0.32, 2)
            d3 = round(b_dur - d1 - d2, 2)

            states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind="code",
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=b.caption,
                    duration_seconds=d1,
                    state_kind="code_chunk",
                    state_data={
                        "file": code_file,
                        "code": code_text,
                        "start_line": code_start_line,
                        "focus_range": (l_start, step1_end),
                        "chunk_index": b_idx,
                        "caption_callout": f"Definition & setup: lines {l_start}-{step1_end}",
                        "callout_type": "setup",
                    },
                    active_focus=b.focus,
                )
            )
            states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind="code",
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=b.caption,
                    duration_seconds=d2,
                    state_kind="code_chunk",
                    state_data={
                        "file": code_file,
                        "code": code_text,
                        "start_line": code_start_line,
                        "focus_range": (l_start, step2_end),
                        "chunk_index": b_idx,
                        "caption_callout": f"Call flow & arguments: lines {l_start}-{step2_end}",
                        "callout_type": "flow",
                    },
                    active_focus=b.focus,
                )
            )
            states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind="code",
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=b.caption,
                    duration_seconds=d3,
                    state_kind="code_chunk",
                    state_data={
                        "file": code_file,
                        "code": code_text,
                        "start_line": code_start_line,
                        "focus_range": focus_range,
                        "chunk_index": b_idx,
                        "caption_callout": b.caption,
                        "callout_type": "focus",
                    },
                    active_focus=b.focus,
                )
            )
        elif b_dur > 2.0:
            mid_line = (
                focus_range[0] + max(1, (focus_range[1] - focus_range[0]) // 2)
                if (focus_range and focus_range[1] > focus_range[0])
                else (focus_range[0] if focus_range else code_start_line)
            )
            d_step1 = round(b_dur * 0.45, 2)
            d_step2 = round(b_dur - d_step1, 2)
            c_callout1 = f"Scope setup: line {focus_range[0]}" if focus_range else f"Setup {code_file}"
            states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind="code",
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=b.caption,
                    duration_seconds=d_step1,
                    state_kind="code_chunk",
                    state_data={
                        "file": code_file,
                        "code": code_text,
                        "start_line": code_start_line,
                        "focus_range": (focus_range[0], mid_line) if focus_range else None,
                        "chunk_index": b_idx,
                        "caption_callout": c_callout1,
                        "callout_type": "setup",
                    },
                    active_focus=b.focus,
                )
            )
            states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind="code",
                    scene_title=scene.title,
                    current_scene_idx=idx,
                    total_scenes=total_scenes,
                    all_scene_titles=titles,
                    repo_name=script.repo_name,
                    caption=b.caption,
                    duration_seconds=d_step2,
                    state_kind="code_chunk",
                    state_data={
                        "file": code_file,
                        "code": code_text,
                        "start_line": code_start_line,
                        "focus_range": focus_range,
                        "chunk_index": b_idx,
                        "caption_callout": b.caption,
                        "callout_type": "focus",
                    },
                    active_focus=b.focus,
                )
            )
        else:
            states.append(
                FrameState(
                    scene_id=scene.id,
                    scene_kind="code",
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
                        "start_line": code_start_line,
                        "focus_range": focus_range,
                        "chunk_index": b_idx,
                        "caption_callout": b.caption,
                        "callout_type": "focus",
                    },
                    active_focus=b.focus,
                )
            )
    return states


def expand_terminal(
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
    cmd = meta.get("command") or (scene.on_screen.content.lstrip("$ ") if scene.on_screen else "")
    if not cmd:
        cmd = "python -m " + script.repo_name

    cmd_len = len(cmd)
    fractions = [0.15, 0.35, 0.55, 0.75, 0.90, 1.0]
    slice_lens = [max(1, int(cmd_len * fr)) for fr in fractions]
    for k in range(1, len(slice_lens)):
        slice_lens[k] = max(slice_lens[k], slice_lens[k - 1])

    typing_step_dur = 0.35
    remaining_dur = max(1.2, scene_dur - (typing_step_dur * len(slice_lens)) - 0.7)

    states: list[FrameState] = []
    for s_idx, slen in enumerate(slice_lens):
        partial = cmd[:slen]
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="terminal",
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
                    "step": s_idx + 1,
                    "total_steps": len(slice_lens),
                },
            )
        )

    states.append(
        FrameState(
            scene_id=scene.id,
            scene_kind="terminal",
            scene_title=scene.title,
            current_scene_idx=idx,
            total_scenes=total_scenes,
            all_scene_titles=titles,
            repo_name=script.repo_name,
            caption=beats[0].caption if beats else cmd,
            duration_seconds=0.35,
            state_kind="terminal_cursor",
            state_data={"command_display": cmd, "cursor_visible": False, "is_typing": False},
        )
    )
    states.append(
        FrameState(
            scene_id=scene.id,
            scene_kind="terminal",
            scene_title=scene.title,
            current_scene_idx=idx,
            total_scenes=total_scenes,
            all_scene_titles=titles,
            repo_name=script.repo_name,
            caption=beats[0].caption if beats else cmd,
            duration_seconds=0.35,
            state_kind="terminal_cursor",
            state_data={"command_display": cmd, "cursor_visible": True, "is_typing": False},
        )
    )

    flag_callout = None
    for fl in facts.cli_flag_details:
        if fl.flag in cmd:
            flag_callout = {"flag": fl.flag, "help": fl.help}
            break

    if remaining_dur > 2.2:
        half_rem = round(remaining_dur / 2.0, 2)
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="terminal",
                scene_title=scene.title,
                current_scene_idx=idx,
                total_scenes=total_scenes,
                all_scene_titles=titles,
                repo_name=script.repo_name,
                caption=beats[-1].caption if beats else cmd,
                duration_seconds=half_rem,
                state_kind="terminal_callout",
                state_data={
                    "command_display": cmd,
                    "cursor_visible": False,
                    "flag_callout": flag_callout,
                    "sub_phase": 1,
                },
            )
        )
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="terminal",
                scene_title=scene.title,
                current_scene_idx=idx,
                total_scenes=total_scenes,
                all_scene_titles=titles,
                repo_name=script.repo_name,
                caption=beats[-1].caption if beats else cmd,
                duration_seconds=remaining_dur - half_rem,
                state_kind="terminal_callout",
                state_data={
                    "command_display": cmd,
                    "cursor_visible": True,
                    "flag_callout": flag_callout,
                    "sub_phase": 2,
                },
            )
        )
    else:
        states.append(
            FrameState(
                scene_id=scene.id,
                scene_kind="terminal",
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
    return states
