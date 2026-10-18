"""
Soft evaluation metrics (informational, never gate publication).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ..schema import ScriptPlan

logger = logging.getLogger(__name__)

DOMAIN_KEYWORDS = [
    "video", "ai", "retrieval", "understanding", "search", "index",
    "embedding", "model", "neural", "documentation", "developer",
    "pipeline", "inference", "vision", "multimodal", "query", "clip", "faiss",
]


def compute_domain_relevance(source: ScriptPlan | str | Any) -> float:
    """
    Score 0.0 - 1.0 based on whole-word domain keyword matching.
    Uses regex word boundaries so 'ai' does not match inside 'maintain'.
    """
    if isinstance(source, ScriptPlan):
        text = " ".join(s.narration for s in source.scenes)
    elif isinstance(source, str):
        text = source
    elif hasattr(source, "relevance_score"):
        return float(source.relevance_score)
    else:
        text = str(source)

    text_lower = text.lower()
    matches = sum(1 for kw in DOMAIN_KEYWORDS if re.search(rf"\b{kw}\b", text_lower))
    score = min(1.0, round(matches / (len(DOMAIN_KEYWORDS) * 0.35), 2))
    return score


def check_coverage(script: ScriptPlan) -> dict[str, bool]:
    """Check whether script contains core structural explainer scenes."""
    kinds = {s.kind for s in script.scenes}
    return {
        "has_title": "title" in kinds,
        "has_overview": "overview" in kinds,
        "has_diagram": "diagram" in kinds,
        "has_code": "code" in kinds,
        "has_terminal": "terminal" in kinds,
        "has_fit": "fit" in kinds,
        "has_recap": "recap" in kinds,
    }


def evaluate_clarity(script: ScriptPlan, llm_used: str = "offline") -> str:
    """
    Evaluate clarity metric.
    Honesty rule: returns 'skipped' unless Claude was actually used and evaluated.
    Never write 'evaluated' unless a real score exists.
    """
    if llm_used != "claude":
        return "skipped"

    try:
        from ..claude import ClaudeLLM
        claude = ClaudeLLM()
        prompt = (
            "Evaluate this explainer script on a 1-5 scale for technical clarity, "
            "conciseness, and precision. Return ONLY a single digit 1-5.\n\n"
            + "\n".join(f"[{s.id}]: {s.narration}" for s in script.scenes)
        )
        res = claude.invoke(prompt, timeout_seconds=15)
        m = re.search(r"\b([1-5])\b", res)
        if m:
            return f"{m.group(1)}/5 (LLM judge)"
    except Exception as e:
        logger.debug(f"Clarity evaluation skipped due to LLM error: {e}")

    return "skipped"


def compute_readme_coverage(script: ScriptPlan, facts: Any | None = None) -> float:
    """Share of description-sentence content words mentioned in script narration."""
    if not facts or not getattr(facts, "readme_description_sentences", []):
        return 1.0
    desc_words: set[str] = set()
    for s in facts.readme_description_sentences:
        text_val = s if isinstance(s, str) else getattr(s, "text", "")
        for w in re.findall(r"\b[A-Za-z0-9]{4,}\b", text_val):
            desc_words.add(w.lower())
    if not desc_words:
        return 1.0
    all_narr = " ".join(s.narration for s in script.scenes).lower()
    matches = sum(1 for w in desc_words if re.search(rf"\b{re.escape(w)}\b", all_narr))
    return round(matches / len(desc_words), 2)


def compute_repo_specific_terms_count(
    script: ScriptPlan,
    repo_files: dict[str, str],
    facts: Any | None = None,
) -> int:
    """Count of unique repo-specific terms named in narration."""
    terms: set[str] = set()
    for f in repo_files:
        terms.add(Path(f).name.lower())
        terms.add(Path(f).stem.lower())
    terms.add(script.repo_name.lower())
    if facts:
        for fl in getattr(facts, "cli_flags", []):
            flag_name = getattr(fl, "flag", "").lstrip("-").lower()
            if flag_name:
                terms.add(flag_name)
        for ident in getattr(facts, "identifiers", []):
            if len(ident) >= 3:
                terms.add(ident.lower())
        for dep in getattr(facts, "dependencies", {}):
            terms.add(dep.lower())
    all_narr = " ".join(s.narration for s in script.scenes).lower()
    matched = sum(1 for t in terms if len(t) >= 3 and re.search(rf"\b{re.escape(t)}\b", all_narr))
    return matched
