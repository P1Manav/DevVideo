"""
Pipeline package: orchestrates linear generation pipeline with bounded loops and hard eval gates.
"""

from ..evals import run_eval
from .models import (
    PipelineResult,
    _build_prompt,
    get_environment_versions,
    get_git_sha,
)
from .runner import run_pipeline

__all__ = [
    "PipelineResult",
    "run_pipeline",
    "get_git_sha",
    "get_environment_versions",
    "_build_prompt",
    "run_eval",
]
