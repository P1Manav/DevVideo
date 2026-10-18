"""
LLM module: Single source of truth for planner backend selection.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any, Protocol

from .analyze import RepoFacts
from .claude import ClaudeLLM, ClaudeMissingBinaryError
from .plan import ClaudePlanner, OfflinePlanner, Planner
from .schema import ScriptPlan

logger = logging.getLogger(__name__)


def select_planners(requested: str = "auto") -> tuple[list[Planner], str, str]:
    """
    Select script planners based on requested option ('auto', 'claude', 'offline', 'mock').
    Returns (planners_list, requested_backend, initial_fallback_reason).
    Single source of truth for both pipeline and CLI.
    """
    req = (requested or "auto").lower()

    if req == "mock":
        try:
            from tests.helpers.mock_llm import MockPlanner
            return [MockPlanner()], "mock", ""
        except ImportError:
            return [OfflinePlanner()], "offline", "mock helper unavailable"

    if req == "offline":
        return [OfflinePlanner()], "offline", ""

    if req == "claude":
        has_claude = shutil.which("claude") is not None
        if not has_claude:
            return [OfflinePlanner()], "offline", "claude: binary not found on PATH"
        try:
            return [ClaudePlanner(), OfflinePlanner()], "claude", ""
        except Exception as e:
            return [OfflinePlanner()], "offline", f"claude: init error: {e}"

    if req == "auto":
        has_claude = shutil.which("claude") is not None
        has_key = bool(os.environ.get("CLAUDE_KEY")) or bool(os.environ.get("ANTHROPIC_API_KEY"))

        if has_claude and has_key:
            try:
                return [ClaudePlanner(), OfflinePlanner()], "auto", ""
            except Exception as e:
                logger.info(f"Claude init failed ({e}); selecting offline planner")
                return [OfflinePlanner()], "offline", f"claude: init error: {e}"

        return [OfflinePlanner()], "offline", ""

    raise ValueError(f"Unknown LLM backend: {requested!r}")


# Backwards compatibility layer for legacy test suites
try:
    from tests.helpers.mock_llm import MockLLM
except ImportError:
    pass


def get_llm_backend(requested: str | None = None) -> Any:
    """Backwards compatibility for legacy callers."""
    req = (requested or os.environ.get("LLM_BACKEND", "auto")).lower()
    if req == "mock":
        from tests.helpers.mock_llm import MockLLM
        return MockLLM()
    if req == "offline":
        return OfflinePlanner()
    if req == "claude":
        return ClaudeLLM()
    if req == "auto":
        planners, _, _ = select_planners("auto")
        if any(isinstance(p, ClaudePlanner) for p in planners):
            return ClaudeLLM()
        return OfflinePlanner()
    raise ValueError(f"Unknown LLM backend: {requested!r}")
