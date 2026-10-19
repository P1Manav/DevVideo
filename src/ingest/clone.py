"""
Safe repository cloning and local directory ingestion.
"""

from __future__ import annotations

import contextlib
import logging
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator

from .collector import RepoContent, collect_files
from .security import validate_github_url

logger = logging.getLogger(__name__)


def _force_rmtree(p_dir: Path) -> None:
    def _on_err(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    if p_dir.exists():
        shutil.rmtree(p_dir, onerror=_on_err)


def clone_repo(url: str, target_dir: Path) -> Path:
    """
    Shallow clone a GitHub repo with hooks disabled, symlinks disabled, and file protocol blocked.
    Returns path to cloned directory.
    """
    owner, repo = validate_github_url(url)
    clone_path = target_dir / repo

    empty_hooks_dir = target_dir / "_empty_hooks"
    empty_hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks_posix = empty_hooks_dir.resolve().as_posix()

    cmd = [
        "git",
        "-c", f"core.hooksPath={hooks_posix}",
        "-c", "core.symlinks=false",
        "-c", "protocol.file.allow=never",
        "clone",
        "--depth", "1",
        url,
        str(clone_path),
    ]

    logger.info(f"Cloning {url} into {clone_path}")
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    last_err = None
    for attempt in range(3):
        if clone_path.exists():
            _force_rmtree(clone_path)
        try:
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=90,
                env=env,
            )
            if result.returncode == 0:
                break
            last_err = RuntimeError(f"git clone failed (exit {result.returncode}): {result.stderr[:500]}")
        except subprocess.TimeoutExpired as e:
            last_err = e
            logger.warning(f"git clone attempt {attempt + 1} timed out, retrying...")
    else:
        raise RuntimeError(f"git clone failed after 3 attempts: {last_err}")

    total_bytes = 0
    for p in clone_path.rglob("*"):
        if p.is_file() and not p.is_symlink():
            try:
                total_bytes += p.stat().st_size
            except Exception:
                pass
    if total_bytes > 200 * 1024 * 1024:
        raise ValueError(
            f"Repository checked-out size ({total_bytes / (1024*1024):.1f} MB) exceeds 200 MB cap"
        )

    return clone_path


def get_git_commit_sha(repo_path: Path) -> str:
    """Retrieve HEAD commit SHA if available."""
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return ""


@contextlib.contextmanager
def safe_clone_github(url: str) -> Iterator[RepoContent]:
    """
    Context manager for cloning a GitHub repository that guarantees cleanup in every outcome.
    """
    owner, repo = validate_github_url(url)
    tmp_dir = tempfile.mkdtemp(prefix="devvideo_clone_")
    try:
        clone_path = clone_repo(url, Path(tmp_dir))
        recorded_secrets: set[str] = set()
        files = collect_files(clone_path, recorded_secrets=recorded_secrets)
        commit_sha = get_git_commit_sha(clone_path)
        yield RepoContent(
            repo_name=repo,
            owner=owner,
            files=files,
            clone_dir=str(clone_path),
            redacted_secrets=recorded_secrets,
            commit_sha=commit_sha,
        )
    finally:
        _force_rmtree(Path(tmp_dir))


def ingest_github(url: str) -> RepoContent:
    """
    Full ingest pipeline for a GitHub URL with guaranteed cleanup.
    """
    with safe_clone_github(url) as content:
        return RepoContent(
            repo_name=content.repo_name,
            owner=content.owner,
            files=content.files,
            clone_dir=None,
            redacted_secrets=content.redacted_secrets,
            commit_sha=content.commit_sha,
        )


def ingest_local(path: str) -> RepoContent:
    """
    Ingest from a local directory (CLI only, must exist).
    """
    p = Path(path)
    if not p.is_dir():
        raise ValueError(f"Not a directory: {path}")

    recorded_secrets: set[str] = set()
    files = collect_files(p, recorded_secrets=recorded_secrets)
    commit_sha = get_git_commit_sha(p)

    return RepoContent(
        repo_name=p.name,
        owner="local",
        files=files,
        clone_dir=str(p),
        redacted_secrets=recorded_secrets,
        commit_sha=commit_sha,
    )
