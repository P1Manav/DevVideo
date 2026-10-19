"""
Hard evaluation gates re-export module.
Combines media_gates, safety_gates, visual_gates, groundedness, and text_gates.
"""
from __future__ import annotations

from .groundedness import (
    STOPWORDS,
    _extract_content_tokens,
    check_groundedness,
)
from .media_gates import (
    _get_ffprobe_duration,
    check_audio_audible_gate,
    check_av_sync_gate,
    check_drift_gate,
    check_duration_gate,
    check_duration_margin_gate,
    check_frames_valid_gate,
    check_motion_gate,
    check_no_overflow_gate,
    check_overflow_gate,
    check_voice_present_gate,
)
from .safety_gates import (
    CMD_PREFIXES,
    INDEPENDENT_SECRET_PATTERNS,
    check_code_verbatim_gate,
    check_command_validity_gate,
    check_rendered_code_matches_gate,
    check_secret_gate,
    check_secret_leaks_gate,
    extract_commands,
    extract_rendered_code_from_html,
)
from .text_gates import (
    DANGLING_STOPWORDS,
    check_narration_quality_gate,
    check_onscreen_text_integrity_gate,
    check_specificity_gate,
)
from .visual_gates import (
    check_code_highlight_focus_gate,
    check_code_window_visible_gate,
    check_decoration_free_gate,
    check_onscreen_matches_voice_gate,
)

__all__ = [
    "STOPWORDS",
    "DANGLING_STOPWORDS",
    "CMD_PREFIXES",
    "INDEPENDENT_SECRET_PATTERNS",
    "_get_ffprobe_duration",
    "_extract_content_tokens",
    "check_duration_gate",
    "check_duration_margin_gate",
    "check_av_sync_gate",
    "check_drift_gate",
    "check_audio_audible_gate",
    "check_voice_present_gate",
    "check_groundedness",
    "check_code_verbatim_gate",
    "extract_rendered_code_from_html",
    "check_rendered_code_matches_gate",
    "extract_commands",
    "check_command_validity_gate",
    "check_secret_leaks_gate",
    "check_secret_gate",
    "check_no_overflow_gate",
    "check_overflow_gate",
    "check_frames_valid_gate",
    "check_narration_quality_gate",
    "check_specificity_gate",
    "check_motion_gate",
    "check_onscreen_text_integrity_gate",
    "check_code_highlight_focus_gate",
    "check_code_window_visible_gate",
    "check_decoration_free_gate",
    "check_onscreen_matches_voice_gate",
]
