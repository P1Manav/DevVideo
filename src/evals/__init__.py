"""
Evaluation package for DevVideo explainer generator.
Contains hard gates and soft metrics used both at runtime and in CI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..schema import ScriptPlan
from .gates import (
    check_audio_audible_gate,
    check_av_sync_gate,
    check_code_verbatim_gate,
    check_rendered_code_matches_gate,
    check_command_validity_gate,
    check_drift_gate,
    check_duration_gate,
    check_frames_valid_gate,
    check_groundedness,
    check_motion_gate,
    check_narration_quality_gate,
    check_no_overflow_gate,
    check_overflow_gate,
    check_secret_gate,
    check_secret_leaks_gate,
    check_specificity_gate,
    check_voice_present_gate,
)
from .metrics import (
    check_coverage,
    compute_domain_relevance,
    compute_readme_coverage,
    compute_repo_specific_terms_count,
    evaluate_clarity,
)
from .report import EvalGate, EvalReport

logger = logging.getLogger(__name__)

__all__ = [
    "EvalGate",
    "EvalReport",
    "check_duration_gate",
    "check_av_sync_gate",
    "check_drift_gate",
    "check_audio_audible_gate",
    "check_groundedness",
    "check_code_verbatim_gate",
    "check_rendered_code_matches_gate",
    "check_command_validity_gate",
    "check_secret_leaks_gate",
    "check_secret_gate",
    "check_no_overflow_gate",
    "check_overflow_gate",
    "check_frames_valid_gate",
    "check_voice_present_gate",
    "check_narration_quality_gate",
    "check_specificity_gate",
    "check_motion_gate",
    "compute_domain_relevance",
    "compute_readme_coverage",
    "compute_repo_specific_terms_count",
    "check_coverage",
    "evaluate_clarity",
    "run_eval",
]


def run_eval(
    script: ScriptPlan,
    repo_files: dict[str, str],
    video_duration: float | Path = 0.0,
    mp4_path: Path | None = None,
    scene_durations: list[float] | None = None,
    audio_durations: list[float] | None = None,
    planned_durations: list[float] | None = None,
    raw_input: str | None = None,
    ingest_secrets: set[str] | list[str] | None = None,
    transcripts: list[str] | None = None,
    frame_paths: list[Path] | None = None,
    overflow_scenes: list[str] | None = None,
    backend_requested: str = "",
    backend_used: str = "",
    fallback_reason: str = "",
    tts_used: str = "auto",
    renderer_used: str = "playwright",
    renderer_fallback_reason: str = "",
    calibrated_wpm: float = 165.0,
    facts: Any | None = None,
) -> EvalReport:
    """Run all 13 hard evaluation gates and compute soft metrics."""
    report = EvalReport(
        backend_requested=backend_requested,
        backend_used=backend_used,
        fallback_reason=fallback_reason,
        renderer_used=renderer_used,
        renderer_fallback_reason=renderer_fallback_reason,
    )

    actual_mp4 = mp4_path if (mp4_path and mp4_path.exists()) else (video_duration if isinstance(video_duration, Path) else None)
    num_duration = float(video_duration) if isinstance(video_duration, (int, float)) else 0.0

    # 1. Gate 1: Duration
    dur_target = actual_mp4 or num_duration
    report.gates.append(check_duration_gate(dur_target))

    # 2. Gate 2: A/V Sync
    s_dur = scene_durations or [s.duration_seconds for s in script.scenes]
    a_dur = audio_durations or s_dur
    report.gates.append(check_av_sync_gate(s_dur, a_dur, mp4_path=actual_mp4))

    # 3. Gate 3: Audible Voice
    report.gates.append(check_audio_audible_gate(actual_mp4, tts_used=tts_used))

    # 4. Gate 4: Groundedness (Provenance)
    report.gates.append(check_groundedness(script, repo_files, facts=facts))

    # 5. Gate 5: Code Verbatim
    report.gates.append(check_code_verbatim_gate(script, repo_files))

    # Gate: Rendered Code Matches
    report.gates.append(check_rendered_code_matches_gate(script, repo_files=repo_files))

    # 6. Gate 6: Command Validity
    report.gates.append(check_command_validity_gate(script, repo_files))

    # 7. Gate 7: Secret Leaks
    report.gates.append(check_secret_leaks_gate(script, ingest_secrets, transcripts, raw_input))

    # 8. Gate 8: No Overflow
    report.gates.append(check_no_overflow_gate(overflow_scenes))

    # 9. Gate 9: Frame Validity
    if frame_paths:
        report.gates.append(check_frames_valid_gate(frame_paths))
    else:
        report.gates.append(EvalGate(name="frames_valid", passed=True, value="untested", threshold="100%", details="No frames provided"))

    # 10. Gate 10: Voice Present (non-blocking unless DEVVIDEO_REQUIRE_VOICE=1)
    report.gates.append(check_voice_present_gate(tts_used=tts_used))

    # 11. Gate 11: Narration Quality (hard gate)
    report.gates.append(check_narration_quality_gate(script, repo_files))

    # 12. Gate 12: Specificity (hard gate)
    report.gates.append(check_specificity_gate(script, repo_files, facts=facts))

    # 13. Gate 13: Motion (hard gate)
    if actual_mp4 and actual_mp4.exists():
        report.gates.append(check_motion_gate(actual_mp4))
    else:
        report.gates.append(EvalGate(name="motion", passed=True, value="skipped", threshold=">= 24 changes", details="No MP4 video provided for motion analysis"))

    # Soft Metrics
    domain_score = getattr(facts, "relevance_score", None) or compute_domain_relevance(script)
    report.metrics["relevance"] = float(domain_score)
    report.metrics["domain_relevance"] = float(domain_score)
    if float(domain_score) < 0.35:
        report.metrics["domain_relevance_warning"] = "low_relevance (< 0.35)"

    report.metrics["readme_coverage"] = compute_readme_coverage(script, facts=facts)
    report.metrics["repo_specific_terms"] = compute_repo_specific_terms_count(script, repo_files, facts=facts)
    report.metrics["coverage"] = check_coverage(script)
    report.metrics["scene_count"] = len(script.scenes)
    report.metrics["wpm"] = calibrated_wpm
    report.metrics["speech_wpm"] = calibrated_wpm
    report.metrics["clarity"] = evaluate_clarity(script, llm_used=backend_used)
    report.metrics["video_duration_seconds"] = round(num_duration, 2)

    # Master publication gate: all blocking gates must pass
    report.all_gates_passed = all(g.passed for g in report.gates if getattr(g, "blocking", True))
    return report
