"""
Claude CLI adapter: executes queries via `claude -p` subprocess.

Uses stdin for the prompt to avoid Windows ~32K argv limit.
Passes environment through unchanged (with optional CLAUDE_KEY forwarding).
Raises typed exceptions for missing binary, non-zero exit, timeout, or empty output.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)


class ClaudeError(RuntimeError):
    """Base exception for Claude CLI invocation failures."""


class ClaudeMissingBinaryError(ClaudeError):
    """Raised when `claude` is not available on PATH."""


class ClaudeTimeoutError(ClaudeError):
    """Raised when Claude CLI execution times out."""


class ClaudeExecutionError(ClaudeError):
    """Raised when Claude CLI returns a non-zero exit status."""


class ClaudeEmptyOutputError(ClaudeError):
    """Raised when Claude CLI produces empty output."""


class ClaudeLLM:
    """Subprocess adapter calling the Claude CLI with `claude -p`."""
    name = "claude"

    def __init__(self, timeout: int = 180) -> None:
        self.timeout = timeout
        self.binary = shutil.which("claude")
        if not self.binary:
            raise ClaudeMissingBinaryError(
                "Claude CLI binary not found on PATH. Install it or use offline backend."
            )

    def complete(self, prompt: str) -> str:
        """
        Execute `claude -p` via subprocess, passing prompt through stdin.
        Avoids Windows argv command-line length limits.
        """
        cmd = [self.binary, "-p"]


        env = os.environ.copy()
        # VERIFY: Copy CLAUDE_KEY to ANTHROPIC_API_KEY only if unset (unverified live)
        if "CLAUDE_KEY" in env and "ANTHROPIC_API_KEY" not in env:
            env["ANTHROPIC_API_KEY"] = env["CLAUDE_KEY"]

        try:
            # We pass prompt via stdin. If a specific version requires argv, switch to:
            # subprocess.run(["claude", "-p", prompt], ...)
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            raise ClaudeTimeoutError(f"Claude CLI timed out after {self.timeout}s") from e
        except FileNotFoundError as e:
            raise ClaudeMissingBinaryError("Claude CLI binary not found on PATH") from e

        if proc.returncode != 0:
            err = proc.stderr[:500] if proc.stderr else proc.stdout[:500]
            raise ClaudeExecutionError(
                f"Claude CLI exited with code {proc.returncode}: {err}"
            )

        output = proc.stdout.strip()
        if not output:
            raise ClaudeEmptyOutputError("Claude CLI returned empty response")

        return output
