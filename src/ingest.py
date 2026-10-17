"""
Ingest module: clone a GitHub repo and extract documentation files.

Responsibilities:
- Validate GitHub URLs (only https://github.com/<owner>/<repo>)
- Shallow clone with hooks disabled
- Collect README, docs, and key source files
- Apply size and file-count caps
- Redact secrets before any text leaves this module
"""

from __future__ import annotations

import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# --- URL validation ---

_GITHUB_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)


def validate_github_url(url: str) -> tuple[str, str]:
    """
    Validate that `url` is a proper GitHub HTTPS URL.
    Returns (owner, repo) or raises ValueError.
    """
    m = _GITHUB_RE.match(url.strip())
    if not m:
        raise ValueError(
            f"Invalid GitHub URL: {url!r}. "
            "Must be https://github.com/<owner>/<repo>"
        )
    return m.group("owner"), m.group("repo")


# --- Secret redaction ---

# Patterns that look like API keys, tokens, passwords
_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|auth)\s*[:=]\s*['\"]?([A-Za-z0-9_/+=-]{16,})['\"]?"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_/+=-]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style keys
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),  # GitHub PATs
    re.compile(r"AKIA[A-Z0-9]{16}"),  # AWS access keys
]


def _shannon_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not s:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    length = len(s)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in freq.values()
    )


def _has_high_entropy(token: str, threshold: float = 4.0) -> bool:
    """Check if a token has suspiciously high entropy (likely a secret)."""
    return len(token) >= 20 and _shannon_entropy(token) > threshold


def redact_secrets(text: str) -> str:
    """
    Replace anything that looks like a secret with [REDACTED].
    Uses both pattern matching and entropy checks.
    """
    result = text
    for pat in _SECRET_PATTERNS:
        result = pat.sub("[REDACTED]", result)

    # Entropy-based: find long hex/base64-ish tokens
    for match in re.finditer(r"[A-Za-z0-9_/+=-]{24,}", result):
        token = match.group()
        if _has_high_entropy(token):
            result = result.replace(token, "[REDACTED]")

    return result


# --- File collection ---

# Extensions we care about for documentation and code
_DOC_EXTENSIONS = {
    ".md", ".txt", ".rst", ".adoc",
    ".py", ".js", ".ts", ".go", ".rs", ".java",
    ".yaml", ".yml", ".toml", ".json", ".cfg", ".ini",
    ".sh", ".bash", ".dockerfile",
}

# Files we always want if they exist
_PRIORITY_FILES = {
    "README.md", "readme.md", "README.rst", "README.txt",
    "setup.py", "setup.cfg", "pyproject.toml",
    "package.json", "Cargo.toml", "go.mod",
    "Makefile", "Dockerfile", "docker-compose.yml",
    "LICENSE", "CONTRIBUTING.md",
}

# Caps
MAX_FILES = 50
MAX_FILE_SIZE = 100_000  # 100KB per file
MAX_TOTAL_SIZE = 500_000  # 500KB total


@dataclass
class RepoContent:
    """Collected content from a repository."""
    repo_name: str
    owner: str
    files: dict[str, str] = field(default_factory=dict)  # relative_path -> content
    clone_dir: str | None = None


def collect_files(repo_dir: Path) -> dict[str, str]:
    """
    Walk the repo and collect relevant text files.
    Returns dict of relative_path -> redacted_content.
    """
    files: dict[str, str] = {}
    total_size = 0

    # Priority files first
    for pf in sorted(_PRIORITY_FILES):
        p = repo_dir / pf
        if p.is_file() and p.stat().st_size <= MAX_FILE_SIZE:
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                files[pf] = redact_secrets(content)
                total_size += len(content)
            except Exception:
                logger.warning(f"Could not read priority file {pf}")

    # Then walk for other files
    for root_str, _dirs, filenames in os.walk(repo_dir):
        root = Path(root_str)
        # Skip hidden dirs, node_modules, vendor, etc.
        rel_root = root.relative_to(repo_dir)
        parts = rel_root.parts
        if any(p.startswith(".") or p in ("node_modules", "vendor", "__pycache__", "venv", ".venv") for p in parts):
            continue

        for fname in sorted(filenames):
            if len(files) >= MAX_FILES:
                break
            if total_size >= MAX_TOTAL_SIZE:
                break

            fpath = root / fname
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
                files[rel] = redact_secrets(content)
                total_size += len(content)
            except Exception:
                pass

    return files


def clone_repo(url: str, target_dir: Path) -> Path:
    """
    Shallow clone a GitHub repo with hooks disabled.
    Returns the path to the cloned directory.
    """
    owner, repo = validate_github_url(url)
    clone_path = target_dir / repo

    cmd = [
        "git", "clone",
        "--depth", "1",
        "--single-branch",
        "--config", "core.hooksPath=/dev/null",  # disable hooks
        url,
        str(clone_path),
    ]

    logger.info(f"Cloning {url} into {clone_path}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed (exit {result.returncode}): {result.stderr[:500]}"
        )

    return clone_path


def ingest_github(url: str) -> RepoContent:
    """
    Full ingest pipeline: validate URL, clone, collect files, clean up.
    """
    owner, repo = validate_github_url(url)

    tmp = tempfile.mkdtemp(prefix="devvideo_")
    try:
        clone_path = clone_repo(url, Path(tmp))
        files = collect_files(clone_path)
        return RepoContent(
            repo_name=repo,
            owner=owner,
            files=files,
            clone_dir=str(clone_path),
        )
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def ingest_local(path: str) -> RepoContent:
    """
    Ingest from a local directory (for testing / local usage).
    """
    p = Path(path)
    if not p.is_dir():
        raise ValueError(f"Not a directory: {path}")

    files = collect_files(p)
    return RepoContent(
        repo_name=p.name,
        owner="local",
        files=files,
        clone_dir=str(p),
    )
