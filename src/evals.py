"""
Evaluation gates and metrics.

Hard gates (must pass or video is NOT published):
  - duration <= 60s
  - command validity 100% (not applicable for mock)
  - secret leaks = 0
  - audio/scene drift within tolerance

Metrics (informational):
  - groundedness: share of scenes with valid evidence
  - domain_relevance: presence of AI/video/retrieval terms
  - clarity: LLM-judge rubric (only when real LLM available, else "skipped")

Guardrails:
  - pre: URL validation, size caps, redaction (in ingest)
  - mid: schema validation, retry cap (in pipeline)
  - post: final gate (here)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .schema import ScriptPlan
from .ingest import redact_secrets

logger = logging.getLogger(__name__)

# Domain keywords for relevance scoring
_DOMAIN_KEYWORDS = {
    "video", "ai", "retrieval", "understanding", "search", "index",
    "embedding", "model", "neural", "documentation", "developer",
    "pipeline", "inference", "vision", "multimodal", "query",
}


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

    def to_dict(self) -> dict:
        return {
            "all_gates_passed": self.all_gates_passed,
            "gates": [asdict(g) for g in self.gates],
            "metrics": self.metrics,
            "backend_requested": self.backend_requested,
            "backend_used": self.backend_used,
            "fallback_reason": self.fallback_reason,
        }

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))
        logger.info(f"Eval report saved to {path}")


def check_duration_gate(duration: float, max_seconds: float = 60.0) -> EvalGate:
    """Hard gate: video must be <= max_seconds."""
    return EvalGate(
        name="duration",
        passed=duration <= max_seconds,
        value=f"{duration:.1f}s",
        threshold=f"<= {max_seconds}s",
    )


def check_secret_gate(script: ScriptPlan) -> EvalGate:
    """Hard gate: no secrets in narration or on-screen content."""
    leaks = 0
    for scene in script.scenes:
        if redact_secrets(scene.narration) != scene.narration:
            leaks += 1
        if redact_secrets(scene.on_screen.content) != scene.on_screen.content:
            leaks += 1

    return EvalGate(
        name="secret_leaks",
        passed=leaks == 0,
        value=str(leaks),
        threshold="0",
    )


def check_groundedness(script: ScriptPlan, repo_files: dict[str, str]) -> EvalGate:
    """Metric: share of scenes with valid evidence."""
    grounded = 0
    for scene in script.scenes:
        ev = scene.evidence
        if ev.file in repo_files:
            content = repo_files[ev.file]
            if ev.quote.lower() in content.lower():
                grounded += 1

    ratio = grounded / len(script.scenes) if script.scenes else 0
    return EvalGate(
        name="groundedness",
        passed=ratio >= 0.5,  # at least half grounded
        value=f"{ratio:.0%}",
        threshold=">= 50%",
        details=f"{grounded}/{len(script.scenes)} scenes grounded",
    )


def check_drift_gate(
    scene_durations: list[float],
    audio_durations: list[float],
    tolerance: float = 2.0,
) -> EvalGate:
    """Hard gate: audio/scene duration drift within tolerance."""
    max_drift = 0.0
    for sd, ad in zip(scene_durations, audio_durations):
        drift = abs(sd - ad)
        max_drift = max(max_drift, drift)

    return EvalGate(
        name="audio_scene_drift",
        passed=max_drift <= tolerance,
        value=f"{max_drift:.2f}s",
        threshold=f"<= {tolerance}s",
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
    backend_requested: str = "",
    backend_used: str = "",
    fallback_reason: str = "",
) -> EvalReport:
    """Run all evaluation gates and metrics."""
    report = EvalReport(
        backend_requested=backend_requested,
        backend_used=backend_used,
        fallback_reason=fallback_reason,
    )

    # Hard gates
    report.gates.append(check_duration_gate(video_duration))
    report.gates.append(check_secret_gate(script))
    report.gates.append(check_groundedness(script, repo_files))

    if scene_durations and audio_durations:
        report.gates.append(check_drift_gate(scene_durations, audio_durations))

    # Metrics
    report.metrics["domain_relevance"] = round(compute_domain_relevance(script), 2)
    report.metrics["scene_count"] = len(script.scenes)
    report.metrics["estimated_narration_seconds"] = round(script.estimated_duration_seconds(), 1)
    report.metrics["video_duration_seconds"] = round(video_duration, 1)
    report.metrics["clarity"] = "skipped"  # Only with real LLM judge

    # Overall
    report.all_gates_passed = all(g.passed for g in report.gates)

    return report
