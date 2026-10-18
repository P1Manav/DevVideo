"""
Ingest module: clone a GitHub repo safely and extract documentation and code files.

Security & Reliability features:
- Validate GitHub URLs strictly (https://github.com/<owner>/<repo>[.git], rejects '.' and '..')
- Secure shallow clone: core.hooksPath pointing to empty dir, core.symlinks=false, protocol.file.allow=never
- Environment GIT_TERMINAL_PROMPT=0, stdin=DEVNULL to prevent hangs
- Checked-out size cap (200 MB)
- Skip symlinks and paths escaping repo directory
- Deterministic sorted os.walk
- File caps: 50 files, 100 KB per file, 500 KB total
- Comprehensive secret redaction (API keys, JWT, PEM, Slack, Google, GitHub PAT, short symbol passwords)
- Redaction entropy rule skips paths, file extensions, and command lines
- Records exact secret values removed for independent gate verification
- Neutralizes prompt-injection delimiter lookalikes in untrusted repo text
"""

from __future__ import annotations

import contextlib
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# --- URL validation ---

_GITHUB_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)


def validate_github_url(url: str) -> tuple[str, str]:
    """
    Validate that `url` is a proper GitHub HTTPS URL.
    Rejects '.' and '..' and any path traversal characters.
    Returns (owner, repo) or raises ValueError.
    """
    clean_url = url.strip()
    m = _GITHUB_RE.match(clean_url)
    if not m:
        raise ValueError(
            f"Invalid GitHub URL: {url!r}. "
            "Must be https://github.com/<owner>/<repo>"
        )

    owner = m.group("owner")
    repo = m.group("repo")

    # Security check S2: Reject '.' and '..' and path traversal
    if owner in (".", "..") or repo in (".", "..") or ".." in owner or ".." in repo:
        raise ValueError(
            f"Invalid GitHub URL: {url!r}. "
            "Owner and repo cannot be '.' or '..' or contain path traversal."
        )

    return owner, repo


# --- Secret redaction ---

# Patterns for specific credential formats
_SECRET_PATTERNS = [
    # PEM Private Keys
    re.compile(r"-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----[^-]+-----END [A-Z0-9 ]+ PRIVATE KEY-----", re.DOTALL),
    # JWT tokens
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    # Slack tokens
    re.compile(r"\bxox[baprs]-[0-9A-Za-z_-]{10,}\b"),
    # Google API keys
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    # GitHub fine-grained and classic tokens
    re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b"),
    re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b"),
    # OpenAI & Anthropic keys
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    # AWS access keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # Bearer tokens
    re.compile(r"(?i)bearer\s+([A-Za-z0-9_/+=-]{20,})"),
    # Short / symbol password assignments (e.g. password = "p@$$w0rd", db_password = '...', secret: 'xyz!#123')
    re.compile(r"""(?i)\b([A-Za-z0-9_-]*(?:password|passwd|secret|api[_-]?key|token|auth))\s*[:=]\s*(['"])([^'"]{6,})\2"""),
]

_COMMON_FILE_EXTENSIONS = (
    ".mp4", ".wav", ".mp3", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".json", ".jsonl", ".py", ".ts", ".js", ".html", ".css", ".txt",
    ".md", ".vtt", ".srt", ".xml", ".yaml", ".yml", ".toml", ".gz",
    ".tar", ".zip", ".so", ".dll", ".exe", ".bin", ".whl",
)

_COMMAND_LINE_PREFIXES = (
    "$ ", "# ", ">>> ", "ffmpeg", "ffprobe", "git", "python", "python3",
    "pip", "pip3", "docker", "npm", "npx", "yarn", "pnpm", "uv", "poetry",
    "cargo", "go", "make", "curl", "bash", "sh", "cd", "export", "pytest",
)


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


def redact_secrets(text: str, recorded_secrets: set[str] | None = None) -> str:
    """
    Replace anything that looks like a secret with [REDACTED].
    Populates `recorded_secrets` with stripped secret values for gate verification.
    Entropy rule strictly skips paths, file extensions, and command lines.
    """
    if not text:
        return text

    result = text

    # Apply specific regex patterns
    for pat in _SECRET_PATTERNS:
        def _replacer(m: re.Match) -> str:
            val = m.group(0)
            if m.lastindex == 3:
                key_name = m.group(1)
                secret_val = m.group(3)
                if recorded_secrets is not None and secret_val and len(secret_val) >= 6:
                    recorded_secrets.add(secret_val)
                return f'{key_name} = "[REDACTED]"'
            elif "bearer" in val.lower():
                secret_val = m.group(1) if m.lastindex else val
                if recorded_secrets is not None and secret_val:
                    recorded_secrets.add(secret_val)
                return "Bearer [REDACTED]"
            else:
                if recorded_secrets is not None and val:
                    recorded_secrets.add(val)
                return "[REDACTED]"

        result = pat.sub(_replacer, result)

    # Entropy-based detection on lines that are NOT command lines
    lines = result.splitlines(keepends=True)
    out_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        is_cmd = any(stripped.startswith(pfx) for pfx in _COMMAND_LINE_PREFIXES)

        if is_cmd:
            # Preserve command lines without entropy corruption
            out_lines.append(line)
            continue

        def _entropy_sub(m: re.Match) -> str:
            token = m.group(0)
            # Skip path-like structure
            if "/" in token or "\\" in token:
                return token
            # Skip file extensions
            lower_token = token.lower()
            if any(lower_token.endswith(ext) for ext in _COMMON_FILE_EXTENSIONS):
                return token

            if _has_high_entropy(token):
                if recorded_secrets is not None:
                    recorded_secrets.add(token)
                return "[REDACTED]"
            return token

        line_redacted = re.sub(r"[A-Za-z0-9_/+=-]{24,}", _entropy_sub, line)
        out_lines.append(line_redacted)

    return "".join(out_lines)


def neutralize_repo_text(text: str) -> str:
    """Neutralize any delimiter lookalikes in untrusted repo text (Prompt injection defense)."""
    if not text:
        return text
    # Replace delimiter lookalikes so attackers cannot escape untrusted data blocks
    return re.sub(
        r"===\s*(?:END[_\s]+)?UNTRUSTED[A-Z0-9_\s]*===",
        "[DELIMITER_NEUTRALIZED]",
        text,
        flags=re.IGNORECASE,
    )


# --- File collection ---

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
    files: dict[str, str] = field(default_factory=dict)  # relative_posix_path -> content
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
        # S1: Skip symlinks
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
        # Sort in place for deterministic traversal
        dirs.sort()
        filenames.sort()

        root = Path(root_str)
        try:
            rel_root = root.relative_to(repo_dir)
        except ValueError:
            continue

        parts = rel_root.parts
        # Skip hidden directories, virtualenvs, dependencies
        if any(p.startswith(".") or p in ("node_modules", "vendor", "__pycache__", "venv", ".venv") for p in parts):
            continue

        for fname in filenames:
            if len(files) >= MAX_FILES:
                break
            if total_size >= MAX_TOTAL_SIZE:
                break

            fpath = root / fname
            # S1: Skip symlinks
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


def clone_repo(url: str, target_dir: Path) -> Path:
    """
    Shallow clone a GitHub repo with hooks disabled, symlinks disabled, and file protocol blocked.
    Returns path to cloned directory.
    """
    owner, repo = validate_github_url(url)
    clone_path = target_dir / repo

    # Create empty directory for core.hooksPath (Windows-safe, no /dev/null)
    empty_hooks_dir = target_dir / "_empty_hooks"
    empty_hooks_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "git",
        "-c", f"core.hooksPath={empty_hooks_dir}",
        "-c", "core.symlinks=false",
        "-c", "protocol.file.allow=never",
        "clone",
        "--depth", "1",
        "--single-branch",
        "--no-tags",
        url,
        str(clone_path),
    ]

    logger.info(f"Cloning {url} into {clone_path}")
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    result = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git clone failed (exit {result.returncode}): {result.stderr[:500]}"
        )

    # Size cap check: abort if checked-out size > 200 MB
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
        shutil.rmtree(tmp_dir, ignore_errors=True)


def ingest_github(url: str) -> RepoContent:
    """
    Full ingest pipeline for a GitHub URL with guaranteed cleanup.
    """
    with safe_clone_github(url) as content:
        # Return collected content (clone_dir is None after cleanup)
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
