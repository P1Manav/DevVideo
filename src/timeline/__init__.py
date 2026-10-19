"""
Timeline package: expands ScriptPlan scenes and beats into fine-grained FrameStates.
"""

from .compiler import (
    compute_progress_percentages,
    expand_script_to_timeline,
    sub_slice_states,
)
from .layout import FrameState, compute_scene_durations

__all__ = [
    "FrameState",
    "compute_scene_durations",
    "compute_progress_percentages",
    "expand_script_to_timeline",
    "sub_slice_states",
]
