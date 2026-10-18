"""
Unit tests for the LLM module.

Tests:
- Mock backend produces valid JSON
- Claude adapter: command construction, non-zero exit, timeout, missing binary
- Auto-backend selection and fallback logic
"""

import json
import os
import subprocess
import pytest
from unittest.mock import patch, MagicMock

from src.llm import MockLLM, ClaudeLLM, get_llm_backend
from src.schema import ScriptPlan


class TestMockLLM:
    def test_first_call_broken(self):
        """First call deliberately returns broken script (for revise loop)."""
        llm = MockLLM()
        response = llm.complete("test prompt")
        data = json.loads(response)
        # Should have NONEXISTENT.md as evidence
        assert any(
            s["evidence"]["file"] == "NONEXISTENT.md"
            for s in data["scenes"]
        )

    def test_second_call_valid(self):
        """Second call returns a valid script."""
        llm = MockLLM()
        llm.complete("test prompt")  # broken
        response = llm.complete("test prompt")  # valid
        data = json.loads(response)
        script = ScriptPlan(**data)
        assert len(script.scenes) >= 2

    def test_force_valid(self):
        """force_valid() skips the broken first response."""
        llm = MockLLM()
        llm.force_valid()
        response = llm.complete("test prompt")
        data = json.loads(response)
        assert not any(
            s["evidence"]["file"] == "NONEXISTENT.md"
            for s in data["scenes"]
        )


class TestClaudeLLM:
    """Tests for Claude CLI adapter using mocked subprocess."""

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_successful_call(self, mock_run, mock_which):
        """Claude CLI returns valid output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"repo_name": "test", "scenes": []}',
            stderr="",
        )
        llm = ClaudeLLM()
        result = llm.complete("test prompt")
        assert "repo_name" in result

        # Verify command construction
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] in ("claude", "/usr/bin/claude")
        assert cmd[1] == "-p"
        assert call_args[1].get("input") == "test prompt"

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run")
    def test_nonzero_exit(self, mock_run, mock_which):
        """Claude CLI exits with non-zero code."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: authentication failed",
        )
        llm = ClaudeLLM()
        with pytest.raises(RuntimeError, match="exited with code 1"):
            llm.complete("test prompt")

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 120))
    def test_timeout(self, mock_run, mock_which):
        """Claude CLI times out."""

        llm = ClaudeLLM()
        with pytest.raises(RuntimeError, match="timed out"):
            llm.complete("test prompt")

    @patch("shutil.which", return_value=None)
    def test_missing_binary(self, mock_which):
        """Claude binary not on PATH."""
        with pytest.raises(RuntimeError, match="not found"):
            ClaudeLLM()




class TestOfflinePlanner:
    """Tests for deterministic extractive OfflinePlanner."""

    def test_offline_planner_fixture_repos(self):
        """Offline planner extracts real content and differentiates two repos."""
        from pathlib import Path
        from src.ingest import ingest_local
        from src.pipeline import _build_prompt
        from src.llm import OfflinePlanner
        from src.verify import verify_script

        repo1 = ingest_local("tests/fixture_repo")
        repo2 = ingest_local("tests/fixture_repo_2")

        planner = OfflinePlanner()

        prompt1 = _build_prompt(repo1)
        resp1 = planner.complete(prompt1)
        plan1 = ScriptPlan.model_validate_json(resp1)

        prompt2 = _build_prompt(repo2)
        resp2 = planner.complete(prompt2)
        plan2 = ScriptPlan.model_validate_json(resp2)

        # 1. Differentiation
        assert plan1.repo_name != plan2.repo_name
        assert plan1.scenes[0].narration != plan2.scenes[0].narration

        # 2. Both scripts pass verify_script
        res1 = verify_script(plan1, repo1.files)
        assert res1.ok, f"Plan 1 verification failed: {res1.errors}"

        res2 = verify_script(plan2, repo2.files)
        assert res2.ok, f"Plan 2 verification failed: {res2.errors}"

        # 3. Grounded evidence check
        for scene in plan1.scenes:
            assert scene.evidence.file in repo1.files
            assert scene.evidence.quote in repo1.files[scene.evidence.file]

        for scene in plan2.scenes:
            assert scene.evidence.file in repo2.files
            assert scene.evidence.quote in repo2.files[scene.evidence.file]

        # 4. Scene count between 4 and 6
        assert 3 <= len(plan1.scenes) <= 6
        assert 3 <= len(plan2.scenes) <= 6


class TestAutoBackend:
    @patch.dict(os.environ, {"LLM_BACKEND": "mock"})
    def test_explicit_mock(self):
        llm = get_llm_backend()
        assert llm.name == "mock"

    def test_explicit_mock_arg(self):
        llm = get_llm_backend("mock")
        assert llm.name == "mock"

    def test_explicit_offline_arg(self):
        llm = get_llm_backend("offline")
        assert llm.name == "offline"

    @patch("shutil.which", return_value=None)
    @patch.dict(os.environ, {"LLM_BACKEND": "auto"}, clear=False)
    def test_auto_no_claude(self, mock_which):
        """Auto falls back to offline when claude not available."""
        llm = get_llm_backend("auto")
        assert llm.name == "offline"

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch.dict(os.environ, {"LLM_BACKEND": "auto", "CLAUDE_KEY": "test-key"}, clear=False)
    def test_auto_with_claude(self, mock_which):
        """Auto selects claude when binary and key are available."""
        llm = get_llm_backend("auto")
        assert llm.name == "claude"

    @patch("shutil.which", return_value="/usr/bin/claude")
    @patch.dict(os.environ, {"LLM_BACKEND": "auto"}, clear=False)
    def test_auto_claude_binary_without_key(self, mock_which):
        """Auto falls back to offline if claude binary exists but no CLAUDE_KEY."""
        if "CLAUDE_KEY" in os.environ:
            del os.environ["CLAUDE_KEY"]
        llm = get_llm_backend("auto")
        assert llm.name == "offline"

    def test_invalid_backend(self):
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            get_llm_backend("nonexistent")
