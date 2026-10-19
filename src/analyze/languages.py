"""
First-party language detection and accounting.
Implements Rule T2: Excludes vendored, minified, or doc assets unless they are the only code.
"""
from __future__ import annotations

import os
from typing import Mapping

CODE_EXTENSIONS: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++",
    ".sh": "Shell",
    ".bash": "Shell",
}

VENDORED_DIR_NAMES = {
    "node_modules", "vendor", "third_party", "dist", "build",
    "_build", "site-packages", ".tox", ".venv", "venv",
    "doc", "docs",
}


def is_vendored_or_generated_path(path: str, text: str = "") -> bool:
    """
    Check if a path points to vendored, minified, or documentation code.
    T2: Exclude node_modules, vendor, third_party, dist, build, docs/_static, doc/,
    _build, site-packages, *.min.js, doc/docs, or files with avg line length > 300 in first 2KB.
    """
    p_norm = path.lower().replace("\\", "/")
    parts = p_norm.split("/")
    filename = parts[-1]

    # Exclude vendored/doc folders in ancestor path
    if any(part in VENDORED_DIR_NAMES for part in parts[:-1]):
        return True

    # Exclude minified files
    if filename.endswith(".min.js") or filename.endswith(".min.css") or filename.endswith("-min.js"):
        return True

    # Check for minification in first 2 KB (avg line length > 300 chars)
    if text:
        sample = text[:2048]
        lines = [l for l in sample.splitlines() if l.strip()]
        if lines:
            avg_len = sum(len(l) for l in lines) / float(len(lines))
            if avg_len > 300:
                return True

    return False


def compute_languages_by_bytes(files: Mapping[str, str]) -> dict[str, int]:
    """
    Compute language distribution strictly from first-party code (T2).
    If no first-party code exists, returns empty dict (no language claimed).
    """
    first_party_bytes: dict[str, int] = {}
    vendored_code_bytes: dict[str, int] = {}

    for path, text in files.items():
        ext = os.path.splitext(path)[1].lower()
        if ext in CODE_EXTENSIONS:
            lang = CODE_EXTENSIONS[ext]
            size = len(text.encode("utf-8", errors="replace"))
            if is_vendored_or_generated_path(path, text):
                vendored_code_bytes[lang] = vendored_code_bytes.get(lang, 0) + size
            else:
                first_party_bytes[lang] = first_party_bytes.get(lang, 0) + size

    if first_party_bytes:
        return dict(sorted(first_party_bytes.items(), key=lambda kv: kv[1], reverse=True))

    # If repo contains ONLY code inside doc/docs and nowhere else, and that's the only code
    # (unless it's just minified assets)
    if vendored_code_bytes:
        # Check if non-minified code exists
        real_vendored: dict[str, int] = {}
        for path, text in files.items():
            ext = os.path.splitext(path)[1].lower()
            if ext in CODE_EXTENSIONS and not (path.endswith(".min.js") or "jquery" in path.lower() or "underscore" in path.lower()):
                lang = CODE_EXTENSIONS[ext]
                size = len(text.encode("utf-8", errors="replace"))
                real_vendored[lang] = real_vendored.get(lang, 0) + size
        if real_vendored:
            return dict(sorted(real_vendored.items(), key=lambda kv: kv[1], reverse=True))

    return {}
