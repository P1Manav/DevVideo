"""
TTS speech normalization and pronunciation helpers (R11).
Normalizes text for speech synthesizers without modifying code snippets or visual text.
"""
from __future__ import annotations

import re


def tts_normalize_speech(text: str) -> str:
    """
    R11: Format speech text for clear text-to-speech pronunciation:
    - file.py -> file dot py
    - --flag -> flag flag (e.g. --top-k -> top k flag)
    - underscores -> spaces
    - e.g. -> for example, i.e. -> that is
    - omit URLs and version pins (pytorch=1.7.1 -> pytorch)
    """
    t = text
    # Expand Latin abbreviations
    t = re.sub(r"\be\.g\.,?\s*", "for example, ", t, flags=re.I)
    t = re.sub(r"\bi\.e\.,?\s*", "that is, ", t, flags=re.I)
    t = re.sub(r"\betc\.?", "and so on", t, flags=re.I)

    # Replace URLs with spoken cue
    t = re.sub(r"https?://\S+", "the link on screen", t)

    # File extensions
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.py\b", r"\1 dot py", t)
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.js\b", r"\1 dot js", t)
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.ts\b", r"\1 dot ts", t)
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.json\b", r"\1 dot json", t)
    t = re.sub(r"(\b[a-zA-Z0-9_-]+)\.txt\b", r"\1 dot txt", t)

    # CLI flags for speech
    def _flag_repl(m):
        flag_name = m.group(1).replace("-", " ").strip()
        if flag_name in ("yes", "y"):
            return ""
        return f"{flag_name} flag"

    t = re.sub(r"--([a-zA-Z0-9_-]+)", _flag_repl, t)

    # Omit version pins in speech: e.g. pytorch=1.7.1 or numpy>=1.20 -> pytorch, numpy
    t = re.sub(r"([a-zA-Z0-9_-]+)(?:==|>=|<=|=|~=)[0-9a-zA-Z_.-]+", r"\1", t)

    # Humanize underscores in spoken words
    t = t.replace("_", " ")

    # Strip extraneous punctuation for voice
    t = re.sub(r"[`~*#]", "", t)
    t = " ".join(t.split())
    return t


def humanize_identifier(ident: str) -> str:
    """Convert snake_case or camelCase identifier to readable spoken words."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1 \2", ident)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s1)
    return s2.replace("_", " ").strip().lower()
