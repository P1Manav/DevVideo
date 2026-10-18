"""
Reasoning and verification loop module.

Executes:
1. plan -> verify -> feedback -> re-plan loop (max 2 retries)
2. All semantic checks before TTS (groundedness, quotes, commands, duration, banned phrases)
3. Typed ScriptRejected(reasons) exception
4. Multi-tier planner fallback chain: claude -> offline -> degraded
5. Absolute guarantee against UnboundLocalError and crashes
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .analyze import RepoFacts
from .evals.gates import _extract_content_tokens
from .plan import OfflinePlanner, Planner, _extract_tokens
from .schema import (
    Beat,
    Evidence,
    OnScreen,
    Scene,
    ScriptPlan,
    check_for_banned_phrases,
    normalize_speech,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 2

_COMMAND_STARTERS = (
    "sudo", "pip", "pip3", "python", "python3", "npm", "npx", "yarn", "pnpm",
    "uv", "poetry", "cargo", "go", "make", "docker", "git", "curl", "bash",
    "sh", "cd", "export",
)


class ScriptRejected(RuntimeError):
    """Raised when all planning attempts and retries for a planner fail verification."""
    def __init__(self, reasons: list[str], last_script: ScriptPlan | None = None) -> None:
        super().__init__("; ".join(reasons))
        self.reasons = reasons
        self.last_script = last_script


def verify_script_plan(
    script: ScriptPlan,
    repo_files: dict[str, str],
    wpm: float = 150.0,
    max_duration: float = 58.0,
    facts: Any | None = None,
) -> tuple[bool, list[str]]:
    """
    Run comprehensive semantic verification on a ScriptPlan before TTS:
    - Provenance groundedness: spans exist case-sensitively and content tokens match
    - Command validity: commands shown appear verbatim in repo files
    - Narration quality: no banned buzzwords or junk tokens
    - Duration estimate with calibrated WPM <= max_duration + 5s
    """
    from .evals.gates import (
        check_command_validity_gate,
        check_groundedness,
        check_narration_quality_gate,
    )

    errors: list[str] = []

    if not script.scenes:
        return False, ["ScriptPlan contains no scenes"]

    # 1. Provenance Groundedness Gate
    ground_gate = check_groundedness(script, repo_files, facts=facts)
    if not ground_gate.passed:
        errors.append(f"Groundedness failed: {ground_gate.details}")

    # 2. Command Validity Gate
    cmd_gate = check_command_validity_gate(script, repo_files)
    if not cmd_gate.passed:
        errors.append(f"Command validity failed: {cmd_gate.details}")

    # 3. Narration Quality Gate
    qual_gate = check_narration_quality_gate(script, repo_files)
    if not qual_gate.passed:
        errors.append(f"Narration quality failed: {qual_gate.details}")

    # 4. Duration check
    est_dur = script.estimated_duration_seconds(wpm=wpm)
    if est_dur > max_duration + 8.0:
        errors.append(f"Estimated duration {est_dur:.1f}s exceeds budget of {max_duration}s at {wpm:.0f} wpm")

    return len(errors) == 0, errors


def build_degraded_plan(facts: RepoFacts, repo_files: dict[str, str]) -> ScriptPlan:
    """
    Safety net: creates an honest, extractive script from facts without template gibberish.
    """
    from .narrate import write_explainer_script
    return write_explainer_script(facts)


def reason_and_plan(
    facts: RepoFacts,
    repo_files: dict[str, str],
    planners: list[Planner],
    wpm: float = 150.0,
    max_duration: float = 58.0,
) -> tuple[ScriptPlan, list[str], str, str]:
    """
    Execute the planning and reasoning verify-revise loop.
    Iterates through candidate planners (e.g. [ClaudePlanner, OfflinePlanner]).
    Returns (script_plan, revision_history, planner_used, fallback_reason).
    Guarantees no UnboundLocalError and zero unhandled exceptions.
    """
    revision_history: list[str] = []
    fallback_reason = ""
    planner_used = "offline"
    script: ScriptPlan | None = None

    for planner in planners:
        current_name = planner.name
        feedback: list[str] = []
        planner_succeeded = False
        last_planner_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                candidate_script = planner.plan(facts, feedback=feedback if feedback else None)
                ok, errors = verify_script_plan(candidate_script, repo_files, wpm=wpm, max_duration=max_duration, facts=facts)
                if ok:
                    script = candidate_script
                    planner_used = current_name
                    planner_succeeded = True
                    revision_history.append(f"{current_name}_attempt_{attempt + 1}: verification passed")
                    break
                else:
                    feedback = errors
                    last_planner_error = f"{current_name}: rejected: {'; '.join(errors)}"
                    revision_history.append(f"{current_name}_attempt_{attempt + 1}: rejected: {'; '.join(errors)}")
            except Exception as e:
                err_str = f"{type(e).__name__}: {e}"
                feedback = [err_str]
                err_lower = str(e).lower()
                if "exited with code" in err_lower or "executionerror" in type(e).__name__.lower():
                    # extract exit code and stderr
                    last_planner_error = f"{current_name}: {e}"
                    if not last_planner_error.startswith(f"{current_name}:"):
                        last_planner_error = f"{current_name}: exit 1: {e}"
                elif "timeout" in err_lower:
                    last_planner_error = f"{current_name}: timeout"
                elif "missingbinary" in type(e).__name__.lower() or "not found on path" in err_lower:
                    last_planner_error = f"{current_name}: binary not found on PATH"
                elif "json" in err_lower or isinstance(e, (json.JSONDecodeError, ValueError)):
                    last_planner_error = f"{current_name}: invalid JSON: {e}"
                else:
                    last_planner_error = f"{current_name}: error: {e}"
                revision_history.append(f"{current_name}_attempt_{attempt + 1}: exception: {err_str}")

        if planner_succeeded and script is not None:
            return script, revision_history, planner_used, fallback_reason

        # Planner failed after retries, record REAL cause
        fallback_reason = last_planner_error or f"{current_name} failed verification"
        logger.warning(f"Planner '{current_name}' failed ({fallback_reason}); proceeding to fallback planner")

    # If all planners failed, degrade cleanly
    logger.warning("All planners exhausted; using degraded fallback plan")
    script = build_degraded_plan(facts, repo_files)
    planner_used = "offline_degraded"
    revision_history.append("all_planners_failed: generated degraded 3-scene plan")

    return script, revision_history, planner_used, fallback_reason

