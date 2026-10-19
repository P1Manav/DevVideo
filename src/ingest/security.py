"""
Ingest security: URL validation, secret redaction, and delimiter neutralization.
"""

from __future__ import annotations

import logging
import math
import re

logger = logging.getLogger(__name__)

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

    if owner in (".", "..") or repo in (".", "..") or ".." in owner or ".." in repo:
        raise ValueError(
            f"Invalid GitHub URL: {url!r}. "
            "Owner and repo cannot be '.' or '..' or contain path traversal."
        )

    return owner, repo


_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z0-9 ]+ PRIVATE KEY-----[^-]+-----END [A-Z0-9 ]+ PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bxox[baprs]-[0-9A-Za-z_-]{10,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b"),
    re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)bearer\s+([A-Za-z0-9_/+=-]{20,})"),
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

    lines = result.splitlines(keepends=True)
    out_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        is_cmd = any(stripped.startswith(pfx) for pfx in _COMMAND_LINE_PREFIXES)

        if is_cmd:
            out_lines.append(line)
            continue

        def _entropy_sub(m: re.Match) -> str:
            token = m.group(0)
            if "/" in token or "\\" in token:
                return token
            lower_token = token.lower()
            if any(lower_token.endswith(ext) for ext in _COMMON_FILE_EXTENSIONS):
                return token
            if re.match(r"^[a-zA-Z_]+$", token):
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
    return re.sub(
        r"===\s*(?:END[_\s]+)?UNTRUSTED[A-Z0-9_\s]*===",
        "[DELIMITER_NEUTRALIZED]",
        text,
        flags=re.IGNORECASE,
    )
