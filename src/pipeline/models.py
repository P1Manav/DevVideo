"""
Pipeline data models and environment inspection helpers.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..evals import EvalReport
from ..schema import ScriptPlan


@dataclass
class PipelineResult:
    """Result of the full pipeline run."""
    success: bool = False
    exit_code: int = 0  # 0: published, 1: rejected, 2: error
    video_path: Path | None = None
    script: ScriptPlan | None = None
    eval_report: EvalReport | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def get_git_sha(repo_dir: Path | None = None) -> str:
    """Retrieve git HEAD sha from repo directory or current repo."""
    try:
        cmd = ["git", "rev-parse", "HEAD"]
        res = subprocess.run(
            cmd,
            cwd=str(repo_dir) if repo_dir else None,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.stdout.strip() if res.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_environment_versions() -> dict[str, str]:
    """Retrieve environment versions for Python, ffmpeg, and Playwright."""
    versions = {"python": sys.version.split()[0]}
    if shutil.which("ffmpeg"):
        try:
            res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
            m = re.search(r"ffmpeg version (\S+)", res.stdout)
            versions["ffmpeg"] = m.group(1) if m else "available"
        except Exception:
            versions["ffmpeg"] = "available"
    else:
        versions["ffmpeg"] = "not_found"

    try:
        import playwright
        versions["playwright"] = getattr(playwright, "__version__", "installed")
    except Exception:
        versions["playwright"] = "not_installed"

    return versions


def _build_prompt(repo: Any) -> str:
    """Build prompt for LLM containing repository content (backwards compatibility)."""
    files = getattr(repo, "files", {})
    file_contents = ""
    for path, content in files.items():
        file_contents += f"\n--- FILE: {path} ---\n{content}\n"

    repo_name = getattr(repo, "repo_name", "unknown")
    owner = getattr(repo, "owner", "")
    return f"""Repository: {repo_name}
Owner: {owner}
{file_contents}
"""
