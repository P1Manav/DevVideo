"""
Mock LLM implementation for test suites.
"""

from __future__ import annotations

import json
from typing import Any
from src.schema import Beat, Evidence, OnScreen, Scene, ScriptPlan, SourceSpan


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
                        "kind": "title",
                        "narration": "Welcome to this walkthrough of the fixture repository.",
                        "on_screen": {"type": "text", "content": "Fixture Repo"},
                        "evidence": {"file": "NONEXISTENT.md", "quote": "does not exist"},
                    },
                    {
                        "id": "overview",
                        "kind": "overview",
                        "narration": "This repository showcases documentation-driven developer videos.",
                        "on_screen": {"type": "text", "content": "Overview"},
                        "evidence": {"file": "README.md", "quote": "fixture repo"},
                    },
                ],
            })

        return json.dumps({
            "repo_name": repo_name,
            "scenes": [
                {
                    "id": "intro",
                    "kind": "title",
                    "title": "Overview",
                    "narration": "This is a sample project for testing the developer video generator.",
                    "on_screen": {"type": "title", "content": "Fixture Repo\nDeveloper Video Generator"},
                    "evidence": {"file": "README.md", "quote": "This is a sample project for testing the developer video generator."},
                },
                {
                    "id": "architecture",
                    "kind": "diagram",
                    "title": "Architecture",
                    "narration": "It represents a fixture repo for AI video understanding and retrieval systems.",
                    "on_screen": {"type": "diagram", "content": "src/main.py -> src/render.py"},
                    "evidence": {"file": "README.md", "quote": "It represents a fixture repo for AI video understanding and retrieval systems."},
                },
                {
                    "id": "usage",
                    "kind": "terminal",
                    "title": "Quickstart",
                    "narration": "Install dependencies with pip install to run this sample project.",
                    "on_screen": {"type": "terminal", "content": "pip install -r requirements.txt"},
                    "evidence": {"file": "docs/usage.md", "quote": "pip install -r requirements.txt"},
                },
                {
                    "id": "conclusion",
                    "kind": "recap",
                    "title": "Takeaways",
                    "narration": "This fixture repo contains sample documentation and code for testing purposes.",
                    "on_screen": {"type": "recap", "content": "Structured Video Assets"},
                    "evidence": {"file": "README.md", "quote": "This fixture repo contains sample documentation and code for testing purposes."},
                },
            ],
        })


class MockPlanner:
    """Mock planner implementing the Planner protocol."""
    name = "mock"

    def __init__(self, mock_llm: MockLLM | None = None) -> None:
        self.mock_llm = mock_llm or MockLLM()

    def plan(
        self,
        facts: Any,
        limits: dict[str, Any] | None = None,
        feedback: list[str] | None = None,
    ) -> ScriptPlan:
        from src.plan import extract_json_object
        raw = self.mock_llm.complete("")
        data = extract_json_object(raw)
        return ScriptPlan(**data)
