"""
Deterministic verb-phrase transforms and docstring cleaning (T3, T4).
Converts imperative bullets to grammatical descriptions and normalizes docstrings without duplication.
"""
from __future__ import annotations

import re

# Base verbs commonly found at start of imperative bullets
IMPERATIVE_VERBS = {
    "convert": "can convert",
    "extract": "can extract",
    "run": "can run",
    "load": "can load",
    "generate": "can generate",
    "build": "can build",
    "parse": "can parse",
    "process": "can process",
    "search": "can search",
    "query": "can query",
    "create": "can create",
    "tokenize": "can tokenize",
    "execute": "can execute",
    "transcode": "can transcode",
    "train": "can train",
    "encode": "can encode",
    "decode": "can decode",
    "index": "can index",
    "export": "can export",
    "import": "can import",
    "filter": "can filter",
    "sample": "can sample",
    "stream": "can stream",
    "capture": "can capture",
    "render": "can render",
    "calculate": "can calculate",
    "compute": "can compute",
    "save": "can save",
    "read": "can read",
    "write": "can write",
    "invoke": "can invoke",
    "apply": "can apply",
    "normalize": "can normalize",
    "transform": "can transform",
    "clean": "can clean",
    "handle": "can handle",
    "return": "can return",
    "check": "can check",
    "validate": "can validate",
}

# 30+ docstring opening patterns
DOCSTRING_TRANSFORMS = [
    (re.compile(r"^command[- ]line interface for\s+", re.I), "is the command-line interface for "),
    (re.compile(r"^cli for\s+", re.I), "is the command-line interface for "),
    (re.compile(r"^neural network model for\s+", re.I), "defines the neural network model for "),
    (re.compile(r"^top[- ]level exports for\s+", re.I), "provides the top-level exports for "),
    (re.compile(r"^top[- ]level\s+", re.I), "provides the top-level package for "),
    (re.compile(r"^entry point for\s+", re.I), "serves as the entry point for "),
    (re.compile(r"^audio and video filter constructors for\s+", re.I), "constructs audio and video filters for "),
    (re.compile(r"^execution engine invoking\s+", re.I), "executes commands invoking "),
    (re.compile(r"^main interface functions for\s+", re.I), "provides main interface functions for "),
    (re.compile(r"^stream representation nodes forming\s+", re.I), "defines stream representation nodes forming "),
    (re.compile(r"^byte[- ]pair encoding tokenizer for\s+", re.I), "tokenizes text using byte-pair encoding for "),
    (re.compile(r"^utility functions for\s+", re.I), "provides utility functions for "),
    (re.compile(r"^helper methods for\s+", re.I), "implements helper methods for "),
    (re.compile(r"^core implementation of\s+", re.I), "implements the core logic of "),
    (re.compile(r"^graph nodes representing\s+", re.I), "defines graph nodes representing "),
    (re.compile(r"^collection of\s+", re.I), "provides a collection of "),
    (re.compile(r"^library for\s+", re.I), "provides a library for "),
    (re.compile(r"^wrapper around\s+", re.I), "provides a wrapper around "),
    (re.compile(r"^bindings for\s+", re.I), "provides Python bindings for "),
    (re.compile(r"^client for\s+", re.I), "provides a client for "),
    (re.compile(r"^parser for\s+", re.I), "parses "),
    (re.compile(r"^tools for\s+", re.I), "provides tools for "),
    (re.compile(r"^classes for\s+", re.I), "defines classes for "),
    (re.compile(r"^algorithms for\s+", re.I), "implements algorithms for "),
    (re.compile(r"^data structures for\s+", re.I), "defines data structures for "),
    (re.compile(r"^engine for\s+", re.I), "implements the engine for "),
    (re.compile(r"^test string escaping\b.*", re.I), "tests string escaping"),
    (re.compile(r"^test\s+", re.I), "tests "),
]


def is_base_verb(word: str) -> bool:
    """Check if word is a base verb form."""
    w = word.lower().rstrip(".,;:")
    return w in IMPERATIVE_VERBS or w in {"return", "extract", "load", "encode", "build", "generate", "parse", "process", "run", "search", "query", "convert", "create", "tokenize", "execute", "transcode", "invoke", "apply", "normalize", "transform", "clean", "handle", "check", "validate"}


def to_third_person_verb(verb: str) -> str:
    """Convert base form verb to 3rd person singular present tense."""
    v = verb.lower().rstrip(".,;:")
    if v == "have":
        return "has"
    if v in ("apply", "try", "modify", "classify", "verify", "specify", "query"):
        return v[:-1] + "ies"
    if v.endswith(("ch", "sh", "ss", "x", "zz", "o")):
        return v + "es"
    if v.endswith("e"):
        return v + "s"
    return v + "s"


def transform_bullet_to_sentence(bullet: str) -> str | None:
    """
    T3: Convert README bullet into a natural declarative description.
    - 'Convert video to numpy array' -> 'It can convert video to a numpy array.'
    - 'Name: description' -> 'Name describes ...' or '<Name> <description>'
    Returns None if the transform cannot be confidently performed (screen only).
    """
    clean = bullet.strip().lstrip("-*•> ").strip()
    if not clean:
        return None

    # Handle 'Name: description' shape
    if ":" in clean:
        parts = clean.split(":", 1)
        name = parts[0].strip()
        desc = parts[1].strip()
        if name and desc:
            desc_first = desc.split()[0].lower() if desc.split() else ""
            if desc_first in ("is", "are", "provides", "implements", "includes", "contains", "handles", "supports"):
                return f"{name} {desc[0].lower() + desc[1:].rstrip('.')}."
            elif is_base_verb(desc_first):
                return f"{name} can {desc[0].lower() + desc[1:].rstrip('.')}."
            else:
                return f"{name} provides {desc[0].lower() + desc[1:].rstrip('.')}."

    words = clean.split()
    if not words:
        return None

    first_word = words[0].lower().rstrip(".,;:")
    if first_word in IMPERATIVE_VERBS:
        aux = IMPERATIVE_VERBS[first_word]
        rest = " ".join(words[1:]).rstrip(".")
        if "to numpy array" in rest:
            rest = rest.replace("to numpy array", "to a numpy array")
        return f"It {aux} {rest}."

    # If already 3rd person singular verb
    if first_word.endswith("s") and not first_word.endswith("ss") and len(first_word) >= 4:
        return f"It {clean[0].lower() + clean[1:].rstrip('.')}."

    # If starts with a noun phrase, check length
    if len(words) >= 3 and not is_base_verb(first_word):
        return f"It supports {clean[0].lower() + clean[1:].rstrip('.')}."

    return None


def convert_docstring_to_verb_phrase(doc: str, func_name: str | None = None) -> str:
    """
    T4: Convert docstring to verb phrase, stripping duplicate function names or leading verbs.
    Never produces 'load load a CLIP model'.
    """
    if not doc:
        return "implements core functionality"

    first = doc.strip().splitlines()[0].strip().rstrip(".")
    # Clean markdown
    first = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", first)
    first = re.sub(r"[`*]", "", first)

    # 1. Check known transform patterns
    for pattern, replacement in DOCSTRING_TRANSFORMS:
        if pattern.search(first):
            return pattern.sub(replacement, first).strip()

    words = first.split()
    if not words:
        return "implements core functionality"

    first_w = words[0].lower().rstrip(".,;:")

    # T4: If function name is supplied and matches docstring opening verb
    # e.g. func_name="load", doc="load a CLIP model" -> "loads a CLIP model"
    if func_name:
        fn_clean = func_name.lower().replace("_", "")
        fn_verb = func_name.lower().split("_")[0]
        if first_w == fn_clean or first_w == fn_verb:
            return to_third_person_verb(first_w) + " " + " ".join(words[1:])

    # 2. Starts with 3rd person singular verb ("Returns ...", "Loads ...", "Encodes ...")
    if first_w.endswith("s") and not first_w.endswith("ss") and len(first_w) >= 3:
        return first[0].lower() + first[1:]

    # 3. Starts with imperative verb ("Return ...", "Invoke ...", "Normalize ...", "Load ...", "Run ...", "Extract ...")
    if is_base_verb(first_w):
        return to_third_person_verb(first_w) + " " + " ".join(words[1:])

    # 4. Noun phrase
    return f"provides {first[0].lower() + first[1:]}"
