"""
Timeline layout models and duration computation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schema import ScriptPlan


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


def compute_scene_durations(
    script: ScriptPlan,
    scene_audio_durations: list[float] | None = None,
) -> list[float]:
    """Compute per-scene duration in seconds from audio durations or estimated text length."""
    scene_durations: list[float] = []
    for i, s in enumerate(script.scenes):
        if scene_audio_durations and i < len(scene_audio_durations) and scene_audio_durations[i] > 0:
            dur = max(2.0, scene_audio_durations[i])
        elif s.duration_seconds > 0:
            dur = max(2.0, s.duration_seconds)
        else:
            dur = s.estimated_duration(wpm=120.0)
        scene_durations.append(dur)
    return scene_durations
