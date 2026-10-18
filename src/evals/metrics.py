"""
Soft evaluation metrics (informational, never gate publication).
"""

from __future__ import annotations

import logging
import re
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
