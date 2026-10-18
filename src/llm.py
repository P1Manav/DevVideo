"""
LLM module: Adapter interfaces and backend selection.

Delegates core execution to:
- src.claude : Subprocess-based Claude CLI adapter
- src.plan   : Fact-based OfflinePlanner & prompt-based ClaudePlanner
- src.reason : Verifying reasoning loop with fallback chain
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Protocol

from .analyze import RepoFacts, analyze_repo
from .claude import ClaudeLLM, ClaudeError
from .ingest import RepoContent
from .plan import OfflinePlanner, ClaudePlanner, Planner, extract_json_object
from .reason import reason_and_plan, verify_script_plan, ScriptRejected
from .schema import ScriptPlan, Scene, OnScreen, Evidence

logger = logging.getLogger(__name__)


class LLMBackend(Protocol):
    """Interface for text-completion LLM backends."""
    name: str

    def complete(self, prompt: str) -> str:
        """Send a prompt and return the raw text response."""
        ...


class MockLLM:
    """
    Mock backend for test suites.
    The first call returns a broken script (missing evidence file) to exercise the revise loop.
    Subsequent calls (or force_valid) return a valid grounded script.
    """
    name = "mock"

    def __init__(self) -> None:
        self._call_count = 0
        self._force_valid = False

    def force_valid(self) -> None:
        """Skip the deliberately broken first response."""
        self._force_valid = True

    def complete(self, prompt: str) -> str:
        self._call_count += 1
        repo_name = "fixture-repo"

        if not self._force_valid and self._call_count == 1:
            return json.dumps({
                "repo_name": repo_name,
                "scenes": [
                    {
                        "id": "intro",
                        "narration": "Welcome to this walkthrough of the fixture repository.",
                        "on_screen": {"type": "text", "content": "Fixture Repo"},
                        "evidence": {"file": "NONEXISTENT.md", "quote": "does not exist"}
                    },
                    {
                        "id": "overview",
                        "narration": "This repository showcases documentation-driven developer videos.",
                        "on_screen": {"type": "text", "content": "Overview"},
                        "evidence": {"file": "README.md", "quote": "fixture repo"}
                    },
                ]
            })

        return json.dumps({
            "repo_name": repo_name,
            "scenes": [
                {
                    "id": "intro",
                    "title": "Overview",
                    "narration": "Welcome to this walkthrough of the fixture repository.",
                    "on_screen": {"type": "title", "content": "Fixture Repo\nDeveloper Video Generator"},
                    "evidence": {"file": "README.md", "quote": "fixture repo"}
                },
                {
                    "id": "architecture",
                    "title": "Architecture",
                    "narration": "The repository organizes components for ingestion, rendering, and assembly.",
                    "on_screen": {"type": "diagram", "content": "src/main.py -> src/render.py"},
                    "evidence": {"file": "README.md", "quote": "sample project"}
                },
                {
                    "id": "usage",
                    "title": "Quickstart",
                    "narration": "Install requirements and run the main entrypoint command.",
                    "on_screen": {"type": "terminal", "content": "pip install -r requirements.txt"},
                    "evidence": {"file": "docs/usage.md", "quote": "install"}
                },
                {
                    "id": "conclusion",
                    "title": "Takeaways",
                    "narration": "This project produces structured retrieval assets including transcripts and chapters.",
                    "on_screen": {"type": "recap", "content": "Structured Video Assets"},
                    "evidence": {"file": "README.md", "quote": "fixture repo"}
                },
            ]
        })


def get_llm_backend(requested: str | None = None) -> LLMBackend | Planner:
    """
    Select an LLM backend or Planner based on LLM_BACKEND env var or explicit argument.
    Auto logic:
    1. If claude binary is on PATH AND CLAUDE_KEY is set -> claude
    2. Otherwise -> offline (deterministic extractive planner)
    Selection is recorded cleanly without false fallback warnings.
    """
    backend_name = requested or os.environ.get("LLM_BACKEND", "auto")

    if backend_name == "mock":
        return MockLLM()

    if backend_name == "offline":
        return OfflinePlanner()

    if backend_name == "claude":
        return ClaudeLLM()

    if backend_name == "auto":
        has_claude = shutil.which("claude") is not None
        has_key = bool(os.environ.get("CLAUDE_KEY"))

        if has_claude and has_key:
            try:
                return ClaudeLLM()
            except RuntimeError as e:
                logger.info(f"Claude init failed ({e}); selecting offline planner")
                return OfflinePlanner()

        logger.info("Auto-selected offline planner (claude not available or key unset)")
        return OfflinePlanner()

    raise ValueError(f"Unknown LLM backend: {backend_name!r}")


def generate_script(
    repo: RepoContent,
    llm: LLMBackend | Planner,
    wpm: float = 150.0,
    max_duration: float = 58.0,
) -> tuple[ScriptPlan, list[str]]:
    """
    Generate a grounded ScriptPlan via semantic analysis and the verify-revise loop.
    Guaranteed to never raise UnboundLocalError or fail on README-less repos.
    """
    facts = analyze_repo(repo)

    # Build planner candidate list based on requested LLM
    planners: list[Planner] = []
    if isinstance(llm, ClaudeLLM):
        planners = [ClaudePlanner(llm), OfflinePlanner()]
    elif isinstance(llm, MockLLM):
        # Wrap mock in a simple adapter
        class MockPlanner:
            name = "mock"
            def plan(self, f: RepoFacts, limits=None, feedback=None) -> ScriptPlan:
                resp = llm.complete("prompt")
                return ScriptPlan(**extract_json_object(resp))
        planners = [MockPlanner(), OfflinePlanner()]
    elif isinstance(llm, OfflinePlanner):
        planners = [llm]
    else:
        planners = [OfflinePlanner()]

    script, revision_history, _, _ = reason_and_plan(
        facts=facts,
        repo_files=repo.files,
        planners=planners,
        wpm=wpm,
        max_duration=max_duration,
    )
    return script, revision_history
