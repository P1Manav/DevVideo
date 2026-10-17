"""
LLM adapter: Protocol-based interface with mock, claude, and auto backends.

Environment variables:
  LLM_BACKEND = auto | mock | claude | gemini   (default: auto)
  CLAUDE_KEY  = (optional, used by auto-detection)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Protocol

from .schema import ScriptPlan

logger = logging.getLogger(__name__)


class LLMBackend(Protocol):
    """Interface for LLM backends."""
    name: str

    def complete(self, prompt: str) -> str:
        """Send a prompt to the LLM and return the raw text response."""
        ...


# ---------------------------------------------------------------------------
# Mock backend (default for tests, used when no real LLM is available)
# ---------------------------------------------------------------------------

class MockLLM:
    """
    Returns a canned script grounded in a fixture repo.
    The first call returns a deliberately broken script (missing evidence)
    so the verify-revise loop is exercised. The second call returns a valid one.
    """
    name = "mock"

    def __init__(self) -> None:
        self._call_count = 0
        self._force_valid = False

    def force_valid(self) -> None:
        """Skip the deliberately-broken first response."""
        self._force_valid = True

    def complete(self, prompt: str) -> str:
        self._call_count += 1

        # Extract repo name from prompt for grounding
        repo_name = "fixture-repo"
        if '"repo_name"' in prompt:
            # Try to find it
            pass

        if not self._force_valid and self._call_count == 1:
            # Deliberately broken: evidence file doesn't exist
            return json.dumps({
                "repo_name": repo_name,
                "scenes": [
                    {
                        "id": "intro",
                        "narration": "Welcome to this walkthrough of the fixture repository, a demonstration project for AI video understanding and retrieval systems.",
                        "on_screen": {"type": "text", "content": "Fixture Repo\\nAI Video Understanding"},
                        "evidence": {"file": "NONEXISTENT.md", "quote": "does not exist"}
                    },
                    {
                        "id": "overview",
                        "narration": "This repository showcases how to build documentation-driven developer videos grounded in actual repository content and code.",
                        "on_screen": {"type": "code", "content": "# Overview\\nprint('hello')"},
                        "evidence": {"file": "README.md", "quote": "fixture repo"}
                    },
                ]
            })

        # Valid response
        return json.dumps({
            "repo_name": repo_name,
            "scenes": [
                {
                    "id": "intro",
                    "narration": "Welcome to this walkthrough of the fixture repository. This project demonstrates how AI-powered video understanding systems can automatically generate developer documentation videos from source code repositories.",
                    "on_screen": {"type": "text", "content": "Fixture Repo\\nDeveloper Video Generator"},
                    "evidence": {"file": "README.md", "quote": "fixture repo"}
                },
                {
                    "id": "architecture",
                    "narration": "The repository follows a modular architecture with clear separation of concerns. The main module handles orchestration while specialized components handle ingestion, rendering, and video assembly.",
                    "on_screen": {"type": "code", "content": "# Architecture\\nsrc/\\n  main.py\\n  ingest.py\\n  render.py"},
                    "evidence": {"file": "README.md", "quote": "sample project"}
                },
                {
                    "id": "usage",
                    "narration": "To get started, clone the repository and install the dependencies. Then run the main command with a GitHub URL to generate your developer video automatically.",
                    "on_screen": {"type": "code", "content": "pip install -r requirements.txt\\npython -m devvideo generate <url>"},
                    "evidence": {"file": "docs/usage.md", "quote": "install"}
                },
                {
                    "id": "conclusion",
                    "narration": "This project bridges the gap between code documentation and video content, enabling AI retrieval engines to index and search developer knowledge in video format.",
                    "on_screen": {"type": "text", "content": "AI Video Understanding\\nRetrieval-Ready Content"},
                    "evidence": {"file": "README.md", "quote": "fixture repo"}
                },
            ]
        })


# ---------------------------------------------------------------------------
# Claude backend (subprocess `claude -p`)
# ---------------------------------------------------------------------------

class ClaudeLLM:
    """
    Calls the Claude CLI via subprocess.

    VERIFY against official Claude CLI docs:
    - We use `claude -p` to send a prompt via stdin/argument.
    - Environment (including CLAUDE_KEY) is passed through unchanged.
    - If the binary is missing or returns non-zero, we raise clearly.
    """
    name = "claude"

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout
        # Check that the binary exists at init time
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude CLI binary not found on PATH. "
                "Install it or set LLM_BACKEND=mock."
            )

    def complete(self, prompt: str) -> str:
        """
        Run `claude -p "<prompt>"` and return stdout.

        VERIFY: This is the simplest invocation. The official Claude CLI
        may support different flags. We intentionally keep this minimal.
        """
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                # Pass environment through unchanged so CLAUDE_KEY works
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Claude CLI timed out after {self.timeout}s"
            )
        except FileNotFoundError:
            raise RuntimeError("Claude CLI binary not found on PATH")

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude CLI exited with code {result.returncode}: "
                f"{result.stderr[:500]}"
            )

        return result.stdout.strip()


# ---------------------------------------------------------------------------
# Auto-selection logic
# ---------------------------------------------------------------------------

def get_llm_backend(requested: str | None = None) -> LLMBackend:
    """
    Select an LLM backend based on LLM_BACKEND env var or explicit request.

    Auto logic:
    1. If claude binary is on PATH AND CLAUDE_KEY is set -> claude
    2. Otherwise -> mock

    If claude is requested but fails to init, falls back to mock with warning.
    """
    backend_name = requested or os.environ.get("LLM_BACKEND", "auto")

    if backend_name == "mock":
        return MockLLM()

    if backend_name == "claude":
        return ClaudeLLM()

    if backend_name == "gemini":
        # Placeholder for optional gemini backend
        logger.warning("Gemini backend not implemented, falling back to mock")
        return MockLLM()

    # auto: try claude, fall back to mock
    if backend_name == "auto":
        has_claude = shutil.which("claude") is not None
        has_key = bool(os.environ.get("CLAUDE_KEY"))

        if has_claude and has_key:
            try:
                return ClaudeLLM()
            except RuntimeError as e:
                logger.warning(f"Claude init failed, falling back to mock: {e}")
                return MockLLM()

        logger.info("Auto-selected mock LLM (claude not available)")
        return MockLLM()

    raise ValueError(f"Unknown LLM backend: {backend_name!r}")
