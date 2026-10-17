"""
Script verification: deterministic checks on the generated script.

Checks:
- Schema validity (handled by pydantic, called here for completeness)
- Evidence grounding: every scene's evidence.file exists and evidence.quote appears in it
- No secrets in narration or on-screen content
- Estimated duration within bounds
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .schema import ScriptPlan
from .ingest import redact_secrets

logger = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    """Result of script verification."""
    ok: bool
    errors: list[str]
    warnings: list[str]


def verify_script(
    script: ScriptPlan,
    repo_files: dict[str, str],
    min_duration: float = 30.0,
    max_duration: float = 58.0,
) -> VerifyResult:
    """
    Run all deterministic checks on a script plan.

    Args:
        script: The script to verify.
        repo_files: dict of relative_path -> content from the repo.
        min_duration: Minimum acceptable estimated duration in seconds.
        max_duration: Maximum acceptable estimated duration in seconds.

    Returns:
        VerifyResult with ok=True if all checks pass.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Evidence grounding
    for scene in script.scenes:
        ev = scene.evidence
        if ev.file not in repo_files:
            errors.append(
                f"Scene '{scene.id}': evidence file '{ev.file}' not found in repo. "
                f"Available: {list(repo_files.keys())[:10]}"
            )
            continue

        content = repo_files[ev.file]
        if ev.quote.lower() not in content.lower():
            errors.append(
                f"Scene '{scene.id}': quote '{ev.quote[:50]}...' not found in '{ev.file}'"
            )

    # 2. Secret check on narration and on-screen content
    for scene in script.scenes:
        redacted_narration = redact_secrets(scene.narration)
        if redacted_narration != scene.narration:
            errors.append(
                f"Scene '{scene.id}': narration contains potential secrets"
            )

        redacted_content = redact_secrets(scene.on_screen.content)
        if redacted_content != scene.on_screen.content:
            errors.append(
                f"Scene '{scene.id}': on-screen content contains potential secrets"
            )

    # 3. Duration estimate
    est = script.estimated_duration_seconds()
    if est < min_duration:
        warnings.append(
            f"Estimated duration {est:.1f}s is below minimum {min_duration}s"
        )
    if est > max_duration:
        errors.append(
            f"Estimated duration {est:.1f}s exceeds maximum {max_duration}s"
        )

    # 4. Scene count
    if len(script.scenes) < 2:
        errors.append("Script must have at least 2 scenes")
    if len(script.scenes) > 8:
        warnings.append(f"Script has {len(script.scenes)} scenes (max recommended: 8)")

    ok = len(errors) == 0
    if not ok:
        logger.warning(f"Script verification failed with {len(errors)} error(s)")
    else:
        logger.info("Script verification passed")

    return VerifyResult(ok=ok, errors=errors, warnings=warnings)
