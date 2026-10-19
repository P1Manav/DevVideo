"""
Deterministic file collection from repository filesystem.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .security import neutralize_repo_text, redact_secrets

logger = logging.getLogger(__name__)

_DOC_EXTENSIONS = {
    ".md", ".txt", ".rst", ".adoc",
    ".py", ".js", ".ts", ".go", ".rs", ".java",
    ".yaml", ".yml", ".toml", ".json", ".cfg", ".ini",
    ".sh", ".bash", ".dockerfile",
}

_PRIORITY_FILES = {
    "README.md", "readme.md", "README.rst", "README.txt",
    "setup.py", "setup.cfg", "pyproject.toml",
    "package.json", "Cargo.toml", "go.mod",
    "Makefile", "Dockerfile", "docker-compose.yml",
    "LICENSE", "CONTRIBUTING.md",
}

MAX_FILES = 50
MAX_FILE_SIZE = 100_000  # 100KB per file
MAX_TOTAL_SIZE = 500_000  # 500KB total


@dataclass
class RepoContent:
    """Collected content and metadata from a repository."""
    repo_name: str
    owner: str
    files: dict[str, str] = field(default_factory=dict)
    clone_dir: str | None = None
    redacted_secrets: set[str] = field(default_factory=set)
    commit_sha: str = ""


def collect_files(repo_dir: Path, recorded_secrets: set[str] | None = None) -> dict[str, str]:
    """
    Walk the repo deterministically and collect relevant text files.
    Skips symlinks, skips paths escaping repo directory.
    Returns dict of relative_posix_path -> redacted_and_neutralized_content.
    """
    files: dict[str, str] = {}
    total_size = 0
    resolved_repo = repo_dir.resolve()

    # Priority files first
    for pf in sorted(_PRIORITY_FILES):
        p = repo_dir / pf
        if not p.is_file():
            continue
        if p.is_symlink():
            continue
        try:
            resolved_p = p.resolve()
            if not str(resolved_p).startswith(str(resolved_repo)):
                continue
            if p.stat().st_size <= MAX_FILE_SIZE:
                content = p.read_text(encoding="utf-8", errors="replace")
                content = redact_secrets(content, recorded_secrets=recorded_secrets)
                content = neutralize_repo_text(content)
                files[pf] = content
                total_size += len(content)
        except Exception:
            logger.warning(f"Could not read priority file {pf}")

    # Deterministic walk for other files
    for root_str, dirs, filenames in os.walk(repo_dir):
        dirs.sort()
        filenames.sort()

        root = Path(root_str)
        try:
            rel_root = root.relative_to(repo_dir)
        except ValueError:
            continue

        parts = rel_root.parts
        if any(p.startswith(".") or p in ("node_modules", "vendor", "__pycache__", "venv", ".venv") for p in parts):
            continue

        for fname in filenames:
            if len(files) >= MAX_FILES:
                break
            if total_size >= MAX_TOTAL_SIZE:
                break

            fpath = root / fname
            if fpath.is_symlink():
                continue

            try:
                resolved_f = fpath.resolve()
                if not str(resolved_f).startswith(str(resolved_repo)):
                    continue
            except Exception:
                continue

            rel = str(fpath.relative_to(repo_dir)).replace("\\", "/")
            if rel in files:
                continue

            suffix = fpath.suffix.lower()
            if suffix not in _DOC_EXTENSIONS and fname not in _PRIORITY_FILES:
                continue

            try:
                size = fpath.stat().st_size
                if size > MAX_FILE_SIZE:
                    continue
                content = fpath.read_text(encoding="utf-8", errors="replace")
                content = redact_secrets(content, recorded_secrets=recorded_secrets)
                content = neutralize_repo_text(content)
                files[rel] = content
                total_size += len(content)
            except Exception:
                pass

    return files
