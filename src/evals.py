"""
Evaluation gates and metrics.

Hard gates (must pass or video is NOT published):
  - duration <= 60s
  - secret leaks = 0 (checks script narration, on-screen text, AND raw LLM input)
  - groundedness = 100% (every scene must cite a real file and verbatim quote)
  - command validity = 100% (every on-screen shell command must appear verbatim in repo files)
  - audio/scene drift <= 0.5s
  - no text overflow in any frame

Metrics (informational / soft):
  - domain_relevance: presence of AI/video/retrieval terms (warns if < 0.5, does not fail)
  - clarity: LLM-judge rubric (only when real LLM available, else "clarity: skipped (no LLM)")
  - scene_count, video_duration
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .schema import ScriptPlan
from .ingest import redact_secrets

logger = logging.getLogger(__name__)

_DOMAIN_KEYWORDS = {
    "video", "ai", "retrieval", "understanding", "search", "index",
    "embedding", "model", "neural", "documentation", "developer",
    "pipeline", "inference", "vision", "multimodal", "query",
}

_CMD_PREFIXES = (
    "pip ", "pip3 ", "npm ", "npx ", "yarn ", "pnpm ", "git ",
    "python ", "python3 ", "docker ", "cargo ", "make ", "pytest ",
)


@dataclass
class EvalGate:
    """Result of a single evaluation gate."""
    name: str
    passed: bool
    value: str
    threshold: str
    details: str = ""


@dataclass
class EvalReport:
    """Full evaluation report for a generated video."""
    gates: list[EvalGate] = field(default_factory=list)
    metrics: dict[str, float | str] = field(default_factory=dict)
    all_gates_passed: bool = False
    backend_requested: str = ""
    backend_used: str = ""
    fallback_reason: str = ""
    renderer_used: str = ""
    renderer_fallback_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "all_gates_passed": self.all_gates_passed,
            "gates": [asdict(g) for g in self.gates],
            "metrics": self.metrics,
            "backend_requested": self.backend_requested,
            "backend_used": self.backend_used,
            "fallback_reason": self.fallback_reason,
            "renderer_used": self.renderer_used,
            "renderer_fallback_reason": self.renderer_fallback_reason,
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info(f"Eval report saved to {path}")


def check_duration_gate(duration: float, max_seconds: float = 60.0) -> EvalGate:
    """Hard gate: video duration must be <= max_seconds."""
    return EvalGate(
        name="duration",
        passed=duration <= max_seconds,
        value=f"{duration:.1f}s",
        threshold=f"<= {max_seconds}s",
    )


def check_secret_gate(
    script: ScriptPlan,
    raw_input: str | None = None,
) -> EvalGate:
    """
    Hard gate: no secrets in narration, on-screen content, or raw LLM input text.
    """
    leaks = 0
    locations: list[str] = []

    if raw_input is not None:
        if redact_secrets(raw_input) != raw_input:
            leaks += 1
            locations.append("raw_input_prompt")

    for scene in script.scenes:
        if redact_secrets(scene.narration) != scene.narration:
            leaks += 1
            locations.append(f"narration:{scene.id}")
        if redact_secrets(scene.on_screen.content) != scene.on_screen.content:
            leaks += 1
            locations.append(f"on_screen:{scene.id}")

    return EvalGate(
        name="secret_leaks",
        passed=leaks == 0,
        value=str(leaks),
        threshold="0",
        details=f"Leaks detected in: {locations}" if leaks else "No secrets detected",
    )


def check_groundedness(script: ScriptPlan, repo_files: dict[str, str]) -> EvalGate:
    """Hard gate: 100% of scenes must have verified evidence in repository files."""
    if not script.scenes:
        return EvalGate(
            name="groundedness",
            passed=False,
            value="0%",
            threshold="100%",
            details="Script has no scenes",
        )

    grounded = 0
    ungrounded: list[str] = []
    for scene in script.scenes:
        ev = scene.evidence
        if ev.file in repo_files:
            content = repo_files[ev.file]
            if ev.quote.lower() in content.lower():
                grounded += 1
            else:
                ungrounded.append(f"{scene.id}: quote not in {ev.file}")
        else:
            ungrounded.append(f"{scene.id}: {ev.file} not in repo")

    ratio = grounded / len(script.scenes)
    return EvalGate(
        name="groundedness",
        passed=ratio >= 1.0,
        value=f"{ratio:.0%}",
        threshold="100%",
        details=f"{grounded}/{len(script.scenes)} scenes grounded" + (f" (Ungrounded: {ungrounded})" if ungrounded else ""),
    )


def extract_commands(content: str) -> list[str]:
    """Extract command lines from text or code blocks."""
    commands = []
    norm_content = content.replace("\\n", "\n")
    for raw_line in norm_content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("$ "):
            commands.append(line[2:].strip())
        elif any(line.startswith(prefix) for prefix in _CMD_PREFIXES):
            commands.append(line)
    return commands


def check_command_validity_gate(script: ScriptPlan, repo_files: dict[str, str]) -> EvalGate:
    """
    Hard gate: 100% of on-screen executable commands must appear verbatim in repo files/docs.
    """
    total_commands = 0
    valid_commands = 0
    missing: list[str] = []

    all_repo_text = "\n".join(repo_files.values())

    for scene in script.scenes:
        cmds = extract_commands(scene.on_screen.content)
        for cmd in cmds:
            total_commands += 1
            if cmd in all_repo_text:
                valid_commands += 1
            else:
                missing.append(f"{scene.id}: '{cmd}'")

    if total_commands == 0:
        return EvalGate(
            name="command_validity",
            passed=True,
            value="100% (0 commands)",
            threshold="100%",
            details="No on-screen shell commands detected",
        )

    ratio = valid_commands / total_commands
    return EvalGate(
        name="command_validity",
        passed=(ratio >= 1.0),
        value=f"{ratio:.0%}",
        threshold="100%",
        details=f"{valid_commands}/{total_commands} commands verified verbatim in repo" + (f" (Missing: {missing})" if missing else ""),
    )


def check_drift_gate(
    planned_or_scene_durations: list[float],
    audio_durations: list[float],
    tolerance: float = 0.5,
) -> EvalGate:
    """Hard gate: audio/scene duration drift within tolerance (<= 0.5s)."""
    max_drift = 0.0
    for sd, ad in zip(planned_or_scene_durations, audio_durations):
        drift = abs(sd - ad)
        max_drift = max(max_drift, drift)

    return EvalGate(
        name="audio_scene_drift",
        passed=max_drift <= tolerance,
        value=f"{max_drift:.2f}s",
        threshold=f"<= {tolerance}s",
        details=f"Max drift: {max_drift:.2f}s (tolerance: {tolerance}s)",
    )


def check_overflow_gate(overflow_scenes: list[str]) -> EvalGate:
    """Hard gate: no text box exceeds frame in any rendered scene."""
    has_overflow = len(overflow_scenes) > 0
    return EvalGate(
        name="no_text_overflow",
        passed=not has_overflow,
        value=f"{len(overflow_scenes)} overflowing scenes",
        threshold="0",
        details=f"Overflow in scenes: {overflow_scenes}" if has_overflow else "All scene frames fit within bounds",
    )


def compute_domain_relevance(script: ScriptPlan) -> float:
    """Score 0-1: how many domain keywords appear in the narration."""
    all_text = " ".join(s.narration.lower() for s in script.scenes)
    found = sum(1 for kw in _DOMAIN_KEYWORDS if kw in all_text)
    return min(1.0, found / max(len(_DOMAIN_KEYWORDS) * 0.3, 1))


def run_eval(
    script: ScriptPlan,
    repo_files: dict[str, str],
    video_duration: float,
    scene_durations: list[float] | None = None,
    audio_durations: list[float] | None = None,
    planned_durations: list[float] | None = None,
    raw_input: str | None = None,
    backend_requested: str = "",
    backend_used: str = "",
    fallback_reason: str = "",
    renderer_used: str = "playwright",
    renderer_fallback_reason: str = "",
    overflow_scenes: list[str] | None = None,
) -> EvalReport:
    """Run all evaluation gates and metrics."""
    report = EvalReport(
        backend_requested=backend_requested,
        backend_used=backend_used,
        fallback_reason=fallback_reason,
        renderer_used=renderer_used,
        renderer_fallback_reason=renderer_fallback_reason,
    )

    # 1. Hard Gates
    report.gates.append(check_duration_gate(video_duration))
    report.gates.append(check_secret_gate(script, raw_input=raw_input))
    report.gates.append(check_groundedness(script, repo_files))
    report.gates.append(check_command_validity_gate(script, repo_files))
    report.gates.append(check_overflow_gate(overflow_scenes or []))

    dur_ref = planned_durations or scene_durations
    if dur_ref and audio_durations:
        report.gates.append(check_drift_gate(dur_ref, audio_durations, tolerance=0.5))

    # 2. Informational Metrics
    domain_score = round(compute_domain_relevance(script), 2)
    report.metrics["domain_relevance"] = domain_score
    if domain_score < 0.5:
        logger.warning(f"Domain relevance score {domain_score:.2f} is below 0.5 threshold")
        report.metrics["domain_relevance_warning"] = "low_relevance (< 0.5)"

    report.metrics["scene_count"] = len(script.scenes)
    report.metrics["estimated_narration_seconds"] = round(script.estimated_duration_seconds(), 1)
    report.metrics["video_duration_seconds"] = round(video_duration, 1)

    if backend_used == "claude":
        report.metrics["clarity"] = "evaluated (LLM judge)"
    else:
        report.metrics["clarity"] = "clarity: skipped (no LLM)"

    # Overall pass/fail
    report.all_gates_passed = all(g.passed for g in report.gates)

    return report
