"""
Domain relevance calculation and pipeline stage extraction.
Enforces Phase 2 & 6: strictly ground named stages in README prose or first-party code docstrings.
"""
from __future__ import annotations

import re
from ..schema import SourceSpan
from .models import (
    RELEVANCE_KEYWORDS,
    STAGE_KEYWORDS,
    CleanedReadme,
    ModuleDocstring,
    ReadmeSentence,
    TopSymbol,
)

CONTENT_SEARCH_CONTEXT_WORDS = {
    "video", "image", "audio", "clip", "frame", "vector", "embedding",
    "feature", "multimodal", "similarity", "nearest", "neighbor",
    "text", "document", "item", "corpus", "collection", "database",
    "index", "engine", "semantic", "dense", "sparse", "retrieval", "search",
}


def is_content_search_sentence(text: str) -> bool:
    """Check that a sentence matches query/search in the context of content retrieval."""
    t_lower = text.lower()
    # Reject non-content retrieval like retrieving CLI arguments, status, etc.
    if re.search(r"\bretrieve\s+(?:the\s+)?(?:command\s+line\s+)?arguments\b", t_lower):
        return False
    if re.search(r"\bretrieve\s+(?:the\s+)?(?:status|value|config|result\s+code)\b", t_lower):
        return False
    tokens = set(re.findall(r"\b[a-z0-9_-]+\b", t_lower))
    return bool(tokens & CONTENT_SEARCH_CONTEXT_WORDS)


def compute_domain_relevance(text: str) -> tuple[float, list[str]]:
    """
    Compute domain relevance using strict word-boundary matching.
    Avoids false positives like matching 'ai' inside 'maintain'.
    """
    if not text:
        return 0.0, []

    matched = []
    for kw in RELEVANCE_KEYWORDS:
        if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
            matched.append(kw)

    unique_matched = sorted(set(matched))
    score = min(1.0, round(len(unique_matched) / 10.0, 2))
    return score, unique_matched


def extract_pipeline_stages(
    readme: CleanedReadme,
    top_symbols: list[TopSymbol],
    module_docstrings: list[ModuleDocstring],
    readme_file: str = "README.md",
) -> tuple[dict[str, str], dict[str, SourceSpan]]:
    """
    Phase 2/6: Detect evidenced pipeline stages.
    Stage terms must appear in:
    (a) a README prose sentence from allowed sections, OR
    (b) a first-party docstring/identifier/CLI help text.
    Tests, examples, dependencies, and docs do NOT count.
    Returns (evidenced_quotes, evidenced_spans).
    """
    evidenced: dict[str, str] = {}
    evidenced_spans: dict[str, SourceSpan] = {}

    # Pool of candidate prose lines from allowed README sections
    candidate_sentences: list[ReadmeSentence] = []
    for rs in readme.description_sentences:
        candidate_sentences.append(rs)
    for fs in readme.feature_sentences:
        candidate_sentences.append(fs)

    # First-party docstrings and symbol names
    first_party_sources: list[tuple[str, str, SourceSpan]] = []
    for sym in top_symbols:
        f_lower = sym.file.lower()
        if not ("test" in f_lower or "example" in f_lower or "doc" in f_lower):
            if sym.docstring:
                span = sym.docstring_span or SourceSpan(
                    file=sym.file,
                    start_line=sym.start_line,
                    end_line=min(sym.start_line + 4, sym.end_line),
                    text=sym.docstring,
                )
                first_party_sources.append((sym.name, sym.docstring, span))
    for m in module_docstrings:
        f_lower = m.file.lower()
        if not ("test" in f_lower or "example" in f_lower or "doc" in f_lower):
            if m.docstring:
                first_party_sources.append((m.file, m.docstring, m.span))

    # Match in standardized pipeline order: decode -> transcribe -> embed -> index -> query -> serve
    pipeline_order = ["decode", "transcribe", "embed", "index", "query", "serve"]
    for stage_name in pipeline_order:
        kws = STAGE_KEYWORDS.get(stage_name, [])

        # 1. Search README candidate prose sentences first
        found = False
        for s in candidate_sentences:
            text = s.text
            if any(re.search(rf"\b{re.escape(k)}\b", text, re.I) for k in kws):
                if stage_name == "query" and not is_content_search_sentence(text):
                    continue
                span_text = getattr(s, "raw_text", None) or s.text
                evidenced[stage_name] = span_text
                evidenced_spans[stage_name] = SourceSpan(
                    file=readme_file,
                    start_line=s.start_line,
                    end_line=s.end_line,
                    text=span_text,
                )
                found = True
                break
        if found:
            continue

        # 2. Search first-party docstrings/symbols
        for src_name, doc, span in first_party_sources:
            if any(re.search(rf"\b{re.escape(k)}\b", doc, re.I) for k in kws):
                if stage_name == "query" and not is_content_search_sentence(doc):
                    continue
                evidenced[stage_name] = f"{src_name}: {doc}"
                evidenced_spans[stage_name] = span
                break

    return evidenced, evidenced_spans
