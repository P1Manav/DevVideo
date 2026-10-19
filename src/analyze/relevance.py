"""
Domain relevance calculation and pipeline stage extraction.
Enforces Phase 4: strictly ground named stages in README prose or first-party code docstrings.
"""
from __future__ import annotations

import re
from .models import RELEVANCE_KEYWORDS, STAGE_KEYWORDS, CleanedReadme, ModuleDocstring, TopSymbol


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
) -> dict[str, str]:
    """
    Phase 4: Detect evidenced pipeline stages.
    Stage terms must appear in:
    (a) a README prose sentence, OR
    (b) a first-party docstring/identifier/CLI help text.
    Tests, examples, dependencies, and docs do NOT count.
    Returns dict of stage -> evidenced quote line.
    """
    evidenced: dict[str, str] = {}

    # Pool of candidate prose lines from README
    candidate_lines: list[str] = []
    for rs in readme.description_sentences:
        candidate_lines.append(rs.text)
    for fs in readme.feature_sentences:
        candidate_lines.append(fs.text)

    # First-party docstrings and symbol names
    first_party_sources: list[tuple[str, str]] = []
    for sym in top_symbols:
        if not ("test" in sym.file.lower() or "example" in sym.file.lower()):
            if sym.docstring:
                first_party_sources.append((sym.name, sym.docstring))
    for m in module_docstrings:
        if not ("test" in m.file.lower() or "example" in m.file.lower()):
            if m.docstring:
                first_party_sources.append((m.file, m.docstring))

    # Match in standardized pipeline order: decode -> embed -> index -> query -> transcribe -> serve
    for stage_name, kws in STAGE_KEYWORDS.items():
        # 1. Search README candidate prose lines first
        found = False
        for l in candidate_lines:
            if any(re.search(rf"\b{re.escape(k)}\b", l, re.I) for k in kws):
                evidenced[stage_name] = l
                found = True
                break
        if found:
            continue

        # 2. Search first-party docstrings/symbols
        for src_name, doc in first_party_sources:
            if any(re.search(rf"\b{re.escape(k)}\b", doc, re.I) for k in kws):
                evidenced[stage_name] = f"{src_name}: {doc}"
                break

    return evidenced
