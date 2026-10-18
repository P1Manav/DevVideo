"""
Central evaluation gate registry.
Defines metadata, thresholds, descriptions, and code references for all 13 hard gates
plus voice_present. Provides markdown table generation synchronized with README.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class GateDefinition:
    name: str
    threshold: str
    description: str
    code_file: str
    blocking: bool = True


GATES_REGISTRY: list[GateDefinition] = [
    GateDefinition(
        name="duration",
        threshold="<= 60.0s",
        description="Container duration measured via ffprobe on final MP4.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="av_sync",
        threshold="Scene <= 0.15s, Stream <= 0.30s",
        description="Maximum drift between audio and video across scenes and streams.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="audio_audible",
        threshold="> -35.0 dB",
        description="Audio stream presence and loudness measured via ffmpeg volumedetect.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="groundedness",
        threshold="100%",
        description="Every scene and beat cites valid source spans with >= 60% token grounding.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="code_verbatim",
        threshold="100%",
        description="Code scene content is an exact verbatim line range from cited source.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="rendered_code_matches",
        threshold="100%",
        description="All characters and indentation in code excerpt are preserved on-screen.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="command_validity",
        threshold="100%",
        description="Shell commands shown exist verbatim in repo code fences (N/A if 0 commands).",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="secret_leaks",
        threshold="0",
        description="Zero credentials detected via independent multi-pattern scanner.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="no_overflow",
        threshold="0",
        description="No dropped lines or bounding box clipping measured in DOM or Pillow.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="frames_valid",
        threshold="100%",
        description="Sampled video frames contain non-flat visual content.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="narration_quality",
        threshold="0 violations",
        description="No banned buzzwords, no dangling endings, verbs present in every beat.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="specificity",
        threshold="100%",
        description="Every beat names >= 1 concrete repo-specific identifier or symbol.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="onscreen_text_integrity",
        threshold="0 violations",
        description="No on-screen text ends mid-word or with dangling stopword; bullets grounded.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="motion",
        threshold=">= 24 changes, max gap <= 5.0s",
        description="Content region motion events sampled at 5 fps with max idle window <= 5s.",
        code_file="src/evals/gates.py",
        blocking=True,
    ),
    GateDefinition(
        name="voice_present",
        threshold="Pass",
        description="Verified voice engine present (non-blocking unless DEVVIDEO_REQUIRE_VOICE=1).",
        code_file="src/evals/gates.py",
        blocking=False,
    ),
]


def generate_gates_markdown_table() -> str:
    """Generate Markdown table for all gates in the registry."""
    lines = [
        "| Gate | Target / Threshold | Description | Code Location |",
        "|------|-------------------|-------------|---------------|",
    ]
    for g in GATES_REGISTRY:
        lines.append(f"| `{g.name}` | `{g.threshold}` | {g.description} | [{g.code_file.split('/')[-1]}]({g.code_file}) |")
    return "\n".join(lines)
