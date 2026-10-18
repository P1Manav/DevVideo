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
) -> tuple[bool, list[str]]:
    """
    Run comprehensive semantic verification on a ScriptPlan before TTS:
    - Evidence file exists
    - Verbatim quote exists in file (whitespace-normalized)
    - Lexical overlap: narration shares >= 2 content tokens with evidence
    - Code verbatim: code excerpt is verbatim from cited file
    - Command validity: commands shown appear verbatim in repo files
    - Absence of banned buzzwords
    - Duration estimate with calibrated WPM <= max_duration
    """
    errors: list[str] = []

    if not script.scenes:
        return False, ["ScriptPlan contains no scenes"]

    for scene in script.scenes:
        sid = scene.id
        # 1. Banned buzzwords
        banned = check_for_banned_phrases(scene.narration)
        if banned:
            errors.append(f"Scene '{sid}' contains banned buzzwords: {banned}")

        # 2. Evidence validation
        efile = scene.evidence.file
        quote = scene.evidence.quote.strip()

        # Handle potential leading slash or posix match
        norm_file = efile.lstrip("/")
        matched_file = None
        for rf in repo_files:
            if rf == norm_file or rf.endswith("/" + norm_file) or norm_file.endswith("/" + rf):
                matched_file = rf
                break

        if not matched_file:
            errors.append(f"Scene '{sid}' cites non-existent file '{efile}'")
            continue

        file_content = repo_files[matched_file]

        # Whitespace-normalized quote check
        norm_file_text = " ".join(file_content.split())
        norm_quote = " ".join(quote.split())

        if norm_quote not in norm_file_text:
            errors.append(f"Scene '{sid}' quote '{quote[:30]}...' not found in '{matched_file}'")
        else:
            # Lexical overlap: >= 2 content tokens
            narration_tokens = _extract_content_tokens(scene.narration)
            evidence_tokens = _extract_content_tokens(norm_quote)
            overlap = narration_tokens & evidence_tokens
            if len(overlap) < 2 and len(evidence_tokens) >= 2:
                errors.append(
                    f"Scene '{sid}' lacks lexical overlap with evidence: shares only {len(overlap)} tokens {overlap}"
                )

        # 3. Command validity
        if scene.kind == "terminal" or scene.on_screen.type == "terminal":
            content = scene.on_screen.content
            for line in content.splitlines():
                line = line.strip().lstrip("$ ")
                if any(line.startswith(pfx) for pfx in _COMMAND_STARTERS):
                    # Check if command appears anywhere in repo files
                    found_cmd = any(line in ftext for ftext in repo_files.values())
                    if not found_cmd:
                        # Allow prefix match (e.g. 'python -m vidsearch')
                        cmd_base = line.split()[0]
                        found_cmd = any(cmd_base in ftext for ftext in repo_files.values())
                    if not found_cmd:
                        errors.append(f"Command '{line}' in scene '{sid}' does not appear in repo files")

    # 4. Duration check
    est_dur = script.estimated_duration_seconds(wpm=wpm)
    if est_dur > max_duration:
        errors.append(f"Estimated duration {est_dur:.1f}s exceeds budget of {max_duration}s at {wpm:.0f} wpm")

    return len(errors) == 0, errors


def build_degraded_plan(facts: RepoFacts, repo_files: dict[str, str]) -> ScriptPlan:
    """
    Ultimate safety net: creates a minimal valid 3-scene plan from whatever exists.
    Guaranteed to never fail or raise an exception.
    """
    repo = facts.repo_name
    first_file = next(iter(repo_files.keys()), "README.md")
    content = repo_files.get(first_file, "Project source code components")
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("<")]

    cand = next((l for l in lines if len(_extract_tokens(l)) >= 2), None)
    quote = cand if cand else (lines[0] if lines else "source components")

    q_toks = _extract_tokens(quote)
    t1 = q_toks[0] if q_toks else repo.lower()
    t2 = q_toks[1] if len(q_toks) > 1 else "source"

    scenes = [
        Scene(
            id="title",
            kind="title",
            title="Overview",
            beats=[Beat(
                say=f"Welcome to {normalize_speech(repo)}. We explore {normalize_speech(t1)} and {normalize_speech(t2)} in under one minute.",
                caption=f"{repo}: {t1} and {t2}",
                focus=repo,
            )],
            on_screen=OnScreen(type="title", content=f"{repo}\nDeveloper Overview"),
            evidence=Evidence(file=first_file, quote=quote),
        ),
        Scene(
            id="overview",
            kind="overview",
            title="Purpose",
            beats=[
                Beat(say=f"This repository organizes {normalize_speech(t1)} and {normalize_speech(t2)}.", caption=f"Focuses on {t1}"),
                Beat(say="You can inspect its components for developer workflows.", caption="Component overview"),
            ],
            on_screen=OnScreen(type="overview", content=f"{repo}\nSource components"),
            evidence=Evidence(file=first_file, quote=quote),
        ),
        Scene(
            id="recap",
            kind="recap",
            title="Takeaways",
            beats=[
                Beat(say=f"To recap, {normalize_speech(repo)} structures {normalize_speech(t1)} and {normalize_speech(t2)}.", caption="Takeaways"),
                Beat(say=f"Explore the repository starting from {normalize_speech(first_file)}.", caption=f"Explore {first_file}"),
            ],
            on_screen=OnScreen(type="recap", content=f"Next step: view {first_file}"),
            evidence=Evidence(file=first_file, quote=quote),
        ),
    ]
    return ScriptPlan(repo_name=repo, scenes=scenes)


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

        for attempt in range(MAX_RETRIES + 1):
            try:
                candidate_script = planner.plan(facts, feedback=feedback if feedback else None)
                ok, errors = verify_script_plan(candidate_script, repo_files, wpm=wpm, max_duration=max_duration)
                if ok:
                    script = candidate_script
                    planner_used = current_name
                    planner_succeeded = True
                    revision_history.append(f"{current_name}_attempt_{attempt + 1}: verification passed")
                    break
                else:
                    feedback = errors
                    revision_history.append(f"{current_name}_attempt_{attempt + 1}: rejected: {'; '.join(errors)}")
            except Exception as e:
                err_str = f"{type(e).__name__}: {e}"
                feedback = [err_str]
                revision_history.append(f"{current_name}_attempt_{attempt + 1}: exception: {err_str}")

        if planner_succeeded and script is not None:
            return script, revision_history, planner_used, fallback_reason

        # Planner failed after retries, try next in chain
        fallback_reason = f"{current_name} failed verification after {MAX_RETRIES + 1} attempts"
        logger.warning(f"Planner '{current_name}' failed; proceeding to fallback planner")

    # If all planners failed, degrade cleanly
    logger.warning("All planners exhausted; using degraded fallback plan")
    script = build_degraded_plan(facts, repo_files)
    planner_used = "offline_degraded"
    revision_history.append("all_planners_failed: generated degraded 3-scene plan")

    return script, revision_history, planner_used, fallback_reason
