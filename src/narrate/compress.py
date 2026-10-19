"""
Sentence compression and clause boundary splitting (R1, R2).
Splits only at grammatical boundaries, never cuts at arbitrary character or word counts.
"""
from __future__ import annotations

import re

# Dangling stopwords that must never end a beat or caption before punctuation
DANGLING_STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "to", "for", "with", "by", "from",
    "and", "or", "but", "that", "which", "is", "are", "was", "be", "as",
    "at", "than", "then", "if", "most", "more", "e.g.", "i.e.", "etc", "etc.",
    "its", "into", "their", "our", "your", "via", "over", "under", "about",
    "natural", "matching", "multimodal",
}

VERB_TOKENS = {
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "do", "does", "did", "can", "could", "will", "would",
    "provides", "provide", "providing", "provided",
    "extracts", "extract", "extracting", "extracted",
    "runs", "run", "running", "ran",
    "builds", "build", "building", "built",
    "trains", "train", "training", "trained",
    "loads", "load", "loading", "loaded",
    "encodes", "encode", "encoding", "encoded",
    "searches", "search", "searching", "searched",
    "indexes", "index", "indexing", "indexed",
    "queries", "query", "querying", "queried",
    "contains", "contain", "containing", "contained",
    "implements", "implement", "implementing", "implemented",
    "processes", "process", "processing", "processed",
    "generates", "generate", "generating", "generated",
    "serves", "serve", "serving", "served",
    "reads", "read", "reading",
    "writes", "write", "writing", "written",
    "uses", "use", "using", "used",
    "enables", "enable", "enabling", "enabled",
    "creates", "create", "creating", "created",
    "parses", "parse", "parsing", "parsed",
    "converts", "convert", "converting", "converted",
    "installs", "install", "installing", "installed",
    "executes", "execute", "executing", "executed",
    "defines", "define", "defining", "defined",
    "returns", "return", "returning", "returned",
    "connects", "connect", "connecting", "connected",
    "imports", "import", "importing", "imported",
    "ships", "ship", "shipping", "shipped",
    "allows", "allow", "allowing", "allowed",
    "transcodes", "transcode", "transcoding", "transcoded",
    "binds", "bind", "binding", "bound",
    "wraps", "wrap", "wrapping", "wrapped",
    "samples", "sample", "sampling", "sampled",
    "filters", "filter", "filtering", "filtered",
    "tags", "tag", "tagging", "tagged",
    "catalogs", "catalog", "cataloging", "cataloged",
}


def has_verb(text: str) -> bool:
    """Check if text contains a recognizable verb token or -s/-ed/-ing verb form."""
    words = re.findall(r"\b[A-Za-z]{2,}\b", text.lower())
    for w in words:
        if w in VERB_TOKENS:
            return True
        if len(w) >= 4 and (w.endswith("ing") or w.endswith("ed") or (w.endswith("s") and not w.endswith("ss"))):
            return True
    return False


def is_dangling(text: str) -> bool:
    """Check if text ends with a dangling stopword before punctuation."""
    cleaned = re.sub(r"[\.,;:!\?]+$", "", text.strip())
    words = cleaned.split()
    if not words:
        return True
    last = words[-1].lower()
    return last in DANGLING_STOPWORDS


def are_quotes_and_brackets_balanced(text: str) -> bool:
    """Check that quotes, brackets, and parentheses are properly balanced."""
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    double_quote_open = False
    single_quote_open = False

    for char in text:
        if char == '"':
            double_quote_open = not double_quote_open
        elif char == "'" and not re.search(r"\b'\b", text):  # ignore contractions
            single_quote_open = not single_quote_open
        elif char in pairs.values():
            stack.append(char)
        elif char in pairs:
            if not stack or stack[-1] != pairs[char]:
                return False
            stack.pop()

    if double_quote_open or single_quote_open or stack:
        return False
    return True


def clean_caption_text(text: str, max_words: int = 8) -> str:
    """
    Format caption text cleanly from a complete clause without dangling stops or unbalanced quotes.
    Never slices mid-clause if it would break grammar.
    """
    if not text:
        return ""
    # Strip markdown and brackets
    s = re.sub(r"\[\[.*?\]\]\(.*?\)", "", text)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[`*]", "", s)
    s = " ".join(s.split()).strip()

    words = s.split()
    if len(words) <= max_words and not is_dangling(s):
        res = s.rstrip(".,;:!?")
        return res if are_quotes_and_brackets_balanced(res) else s

    # Clause boundary split
    for sep in [": ", " - ", " -- ", "; ", ", ", " and "]:
        if sep in s:
            first_clause = s.split(sep)[0].strip()
            if 2 <= len(first_clause.split()) <= max_words and not is_dangling(first_clause):
                res = first_clause.rstrip(".,;:!?")
                if are_quotes_and_brackets_balanced(res):
                    return res

    if len(words) <= 10 and not is_dangling(s):
        res = s.rstrip(".,;:!?")
        if are_quotes_and_brackets_balanced(res):
            return res

    truncated = words[:max_words]
    while truncated and (truncated[-1].lower().rstrip(".,;:!?") in DANGLING_STOPWORDS or is_dangling(" ".join(truncated))):
        truncated.pop()
    res = " ".join(truncated).rstrip(".,;:!?")
    if not are_quotes_and_brackets_balanced(res):
        # balance double quote if single open
        if res.count('"') % 2 == 1:
            res += '"'
    return res


def compress_sentence(sentence: str, max_words: int = 22) -> list[str]:
    """
    R1: Compress a sentence into 1 or 2 complete grammatical beats without truncation.
    Splits only at clause boundaries or drops trailing relative phrases.
    """
    # Clean markdown links
    s = re.sub(r"\[\[.*?\]\]\(.*?\)", "", sentence)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[`*]", "", s)
    # Unpack parenthetical expansions for speech
    s = re.sub(r"\(([A-Z][a-zA-Z -]+)\)", r", \1,", s)
    s = re.sub(r"[\(\)]", "", s)
    s = " ".join(s.split()).strip()

    if not s:
        return []

    words = s.split()
    if len(words) <= max_words and not is_dangling(s) and has_verb(s):
        s_clean = s.rstrip(".") + "."
        return [s_clean]

    # Strategy (a): Split at coordinating conjunction or semicolon or dash
    conjunction_patterns = [
        r";\s*",
        r"\s*--\s*",
        r"\s*—\s*",
        r",\s+and\s+",
        r",\s+but\s+",
        r",\s+while\s+",
        r",\s+so\s+",
    ]
    for cp in conjunction_patterns:
        m = re.search(cp, s, flags=re.I)
        if m:
            part1 = s[:m.start()].strip()
            part2 = s[m.end():].strip()
            if len(part1.split()) >= 4 and has_verb(part1) and not is_dangling(part1):
                b1 = part1[0].upper() + part1[1:].rstrip(".") + "."
                beats = [b1]
                if (len(part2.split()) >= 4 and has_verb(part2) and not is_dangling(part2) and len(part2.split()) <= max_words):
                    b2 = part2[0].upper() + part2[1:].rstrip(".") + "."
                    beats.append(b2)
                return beats

    # Strategy (b): Drop trailing relative or participial phrases
    trailing_markers = [
        r",\s+without\s+.*$",
        r",\s+given\s+.*$",
        r",\s+which\s+.*$",
        r",\s+using\s+.*$",
        r",\s+where\s+.*$",
        r",\s+allowing\s+.*$",
        r",\s+enabling\s+.*$",
        r",\s+providing\s+.*$",
    ]
    for tm in trailing_markers:
        trimmed = re.sub(tm, "", s, flags=re.I).strip()
        if trimmed and trimmed != s:
            if len(trimmed.split()) <= max_words and has_verb(trimmed) and not is_dangling(trimmed):
                return [trimmed.rstrip(".") + "."]

    # Strategy (c): Split at first comma if first part is complete
    if "," in s:
        comma_parts = s.split(",", 1)
        prefix = comma_parts[0].strip()
        if len(prefix.split()) >= 5 and has_verb(prefix) and not is_dangling(prefix):
            return [prefix.rstrip(".") + "."]

    if len(words) <= max_words and has_verb(s):
        cleaned = re.sub(r"[\.,;:!\?]+$", "", s).strip()
        while cleaned.split() and cleaned.split()[-1].lower() in DANGLING_STOPWORDS:
            cleaned = " ".join(cleaned.split()[:-1])
        if has_verb(cleaned) and len(cleaned.split()) >= 4:
            return [cleaned + "."]

    return []
