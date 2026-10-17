"""
LLM adapter: Protocol-based interface with offline, mock, claude, and auto backends.

Environment variables:
  LLM_BACKEND = auto | offline | mock | claude   (default: auto)
  CLAUDE_KEY  = (optional, used by auto-detection for claude)
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from typing import Protocol

from .schema import ScriptPlan, Scene, OnScreen, Evidence

logger = logging.getLogger(__name__)


class LLMBackend(Protocol):
    """Interface for LLM backends."""
    name: str

    def complete(self, prompt: str) -> str:
        """Send a prompt to the LLM and return the raw text response."""
        ...


# ---------------------------------------------------------------------------
# Offline Planner (Default when Claude is unavailable: extractive, deterministic)
# ---------------------------------------------------------------------------

class OfflinePlanner:
    """
    Deterministic extractive script planner.
    Constructs 4-6 grounded scenes from real repository content without external network:
    1. Title & Tagline
    2. Installation command
    3. Usage example / code snippet
    4. Key module or function
    5. Domain relevance: how it fits video understanding / retrieval pipelines.

    Every scene strictly cites a real file and verbatim quote found within it.
    """
    name = "offline"

    def __init__(self, fallback_reason: str = "") -> None:
        self.fallback_reason = fallback_reason

    def complete(self, prompt: str) -> str:
        repo_name, owner, files = self._parse_prompt_data(prompt)
        plan = self.build_plan(repo_name, files)
        return plan.model_dump_json()

    @staticmethod
    def _parse_prompt_data(prompt: str) -> tuple[str, str, dict[str, str]]:
        repo_name = "repository"
        owner = "developer"
        files: dict[str, str] = {}

        data_match = re.search(
            r"=== UNTRUSTED DATA BLOCK.*?===\s*\n(.*?)=== END UNTRUSTED DATA BLOCK ===",
            prompt,
            re.DOTALL,
        )
        data_text = data_match.group(1) if data_match else prompt

        rm = re.search(r"^Repository:\s*(.+)$", data_text, re.MULTILINE)
        if rm:
            repo_name = rm.group(1).strip()

        om = re.search(r"^Owner:\s*(.+)$", data_text, re.MULTILINE)
        if om:
            owner = om.group(1).strip()

        chunks = re.split(r"\n--- FILE:\s*([^\n]+)\s*---\n", data_text)
        for i in range(1, len(chunks), 2):
            fpath = chunks[i].strip()
            content = chunks[i + 1] if i + 1 < len(chunks) else ""
            files[fpath] = content

        return repo_name, owner, files

    def build_plan(self, repo_name: str, files: dict[str, str]) -> ScriptPlan:
        scenes: list[Scene] = []

        readme_path = None
        for cand in ["README.md", "readme.md", "README.rst", "README.txt"]:
            if cand in files and files[cand].strip():
                readme_path = cand
                break

        # 1. Title & Tagline Scene
        if readme_path:
            content = files[readme_path]
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            header_line = lines[0] if lines else repo_name
            clean_title = header_line.lstrip("#").strip()

            desc = ""
            for line in lines[1:]:
                if not line.startswith("#") and len(line) > 15:
                    desc = line
                    break

            quote = desc if (desc and desc in content) else header_line
            narration = (
                f"Welcome to this walkthrough of {clean_title or repo_name}. "
                f"{desc[:120] if desc else 'This repository provides modular, grounded components for developer workflows.'} "
                "Built for developers integrating video understanding and retrieval engines."
            )
            scenes.append(Scene(
                id="intro",
                narration=narration,
                on_screen=OnScreen(type="text", content=f"{clean_title or repo_name}\nDeveloper Walkthrough"),
                evidence=Evidence(file=readme_path, quote=quote),
            ))

        # 2. Installation Scene
        install_found = False
        if readme_path:
            rm_text = files[readme_path]
            m = re.search(r"```(?:bash|sh)?\s*\n([^`]*?(?:pip|npm|cargo|install)[^`]*?)\n```", rm_text, re.IGNORECASE)
            if m:
                for line in m.group(1).strip().splitlines():
                    clean_l = line.strip()
                    if any(kw in clean_l.lower() for kw in ["pip", "npm", "cargo", "install", "git clone"]) and clean_l in rm_text:
                        scenes.append(Scene(
                            id="installation",
                            narration=f"To install and configure {repo_name}, run the project installation command in your local environment.",
                            on_screen=OnScreen(type="code", content=clean_l),
                            evidence=Evidence(file=readme_path, quote=clean_l),
                        ))
                        install_found = True
                        break

        if not install_found and "requirements.txt" in files and files["requirements.txt"].strip():
            req_lines = [l.strip() for l in files["requirements.txt"].splitlines() if l.strip() and not l.startswith("#")]
            if req_lines and req_lines[0] in files["requirements.txt"]:
                scenes.append(Scene(
                    id="installation",
                    narration=f"Install the necessary dependencies from requirements.txt to prepare the environment for {repo_name}.",
                    on_screen=OnScreen(type="code", content=f"pip install -r requirements.txt\n# Includes {req_lines[0]}"),
                    evidence=Evidence(file="requirements.txt", quote=req_lines[0]),
                ))
                install_found = True

        # 3. Usage Scene
        usage_found = False
        for path in [readme_path, "docs/usage.md", "usage.md"]:
            if path and path in files:
                f_text = files[path]
                m = re.search(r"```(?:python|py|bash|sh)?\s*\n([^`]+?)\n```", f_text)
                if m:
                    code_snippet = m.group(1).strip()
                    first_line = code_snippet.splitlines()[0].strip()
                    if first_line in f_text and len(first_line) > 3 and not first_line.startswith("pip install"):
                        scenes.append(Scene(
                            id="usage",
                            narration=f"Here is how developers import, initialize, and execute {repo_name} to process inputs.",
                            on_screen=OnScreen(type="code", content=code_snippet[:220]),
                            evidence=Evidence(file=path, quote=first_line),
                        ))
                        usage_found = True
                        break

        # 4. Key Module Scene
        for path, f_content in files.items():
            if path.endswith(".py") and not path.startswith("test") and f_content.strip():
                m = re.search(r"(def\s+[a-zA-Z0-9_]+\s*\([^)]*\)[^:]*:|class\s+[a-zA-Z0-9_]+[^:]*:)", f_content)
                if m and m.group(1) in f_content:
                    quote = m.group(1)
                    scenes.append(Scene(
                        id="architecture",
                        narration=f"The core implementation in {path} is modular, readable, and structured for straightforward extension.",
                        on_screen=OnScreen(type="code", content=f"# {path}\n{quote}"),
                        evidence=Evidence(file=path, quote=quote),
                    ))
                    break

        # 5. Domain Relevance Scene (AI video understanding & retrieval engines)
        for path in [readme_path, "docs/usage.md"]:
            if path and path in files:
                text = files[path]
                for sentence in re.split(r"[.\n]", text):
                    clean_s = sentence.strip()
                    if len(clean_s) > 15 and any(k in clean_s.lower() for k in ["video", "retrieval", "search", "engine", "ai", "sample", "project"]):
                        if clean_s in text:
                            scenes.append(Scene(
                                id="pipeline_integration",
                                narration="In an AI video understanding or retrieval engine pipeline, this repository provides critical processing components for indexing, query processing, and metadata extraction.",
                                on_screen=OnScreen(type="diagram", content="Video Understanding Pipeline\nIngest -> Neural Index -> Retrieval Engine"),
                                evidence=Evidence(file=path, quote=clean_s),
                            ))
                            break
                break

        # Schema fallback guarantee: at least 2 grounded scenes
        if len(scenes) < 2 and files:
            first_path = list(files.keys())[0]
            content = files[first_path]
            first_line = content.splitlines()[0].strip() if content.splitlines() else "content"
            quote = first_line if first_line in content else content[:30]
            scenes.append(Scene(
                id="summary",
                narration=f"Summary of {repo_name} covering foundational components and repository structure for developers.",
                on_screen=OnScreen(type="text", content=f"{repo_name}\nDeveloper Summary"),
                evidence=Evidence(file=first_path, quote=quote),
            ))

        return ScriptPlan(repo_name=repo_name, scenes=scenes)


# ---------------------------------------------------------------------------
# Mock backend (retained for testing revise loop with deliberate failure)
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
        repo_name = "fixture-repo"

        if not self._force_valid and self._call_count == 1:
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
                    "on_screen": {"type": "code", "content": "pip install -r requirements.txt\\npython main.py"},
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
    - Uses `claude -p` to send prompt via argument/stdin.
    - Environment (including CLAUDE_KEY) is passed through unchanged.
    - If binary is missing or exits non-zero, raises RuntimeError.
    """
    name = "claude"

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude CLI binary not found on PATH. Install it or use offline backend."
            )

    def complete(self, prompt: str) -> str:
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")
        except FileNotFoundError:
            raise RuntimeError("Claude CLI binary not found on PATH")

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}"
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
    2. Otherwise -> offline (deterministic extractive planner)
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
                logger.warning(f"Claude init failed ({e}), falling back to offline planner")
                return OfflinePlanner(fallback_reason=str(e))

        logger.info("Auto-selected offline planner (claude not available)")
        return OfflinePlanner()

    raise ValueError(f"Unknown LLM backend: {backend_name!r}")
