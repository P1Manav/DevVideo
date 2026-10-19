"""
Scene 5: Terminal Quickstart narration (T7, R6).
Validates real shell commands, rejects python statements / cd / clone, limits spoken length to 8 tokens.
"""
from __future__ import annotations

import re
from ..analyze import RepoFacts, is_valid_shell_command
from ..schema import Beat, Scene, SourceSpan
from .compress import are_quotes_and_brackets_balanced
from .speech import tts_normalize_speech


def select_best_install_command(commands: list[str]) -> str | None:
    """T7: Choose ONE install command: prefer pip/npm/yarn/cargo over conda/apt."""
    valid = [c for c in commands if is_valid_shell_command(c)]
    if not valid:
        return None
    for pref in ("pip ", "pip3 ", "npm ", "yarn ", "cargo "):
        for cmd in valid:
            if cmd.startswith(pref):
                return cmd
    return valid[0]


def select_best_usage_command(commands: list[str]) -> str | None:
    """T7: Choose ONE usage command that is a real shell command."""
    valid = [c for c in commands if is_valid_shell_command(c)]
    return valid[0] if valid else None


def build_terminal_scene(facts: RepoFacts, readme_file: str) -> Scene | None:
    """R6, T7: Builds terminal scene with valid shell commands only."""
    install_cmd = select_best_install_command(facts.readme.install_commands)
    usage_cmd = select_best_usage_command(facts.readme.usage_commands)

    if not install_cmd and not usage_cmd:
        return None

    beats: list[Beat] = []

    if install_cmd:
        tokens = install_cmd.split()
        if len(tokens) > 8:
            say1 = f"Run the install command shown on screen for {facts.repo_name}."
        else:
            say1 = f"Run {install_cmd} to install dependencies for {facts.repo_name}."

        i_line = 1
        for idx, line in enumerate(facts.readme.raw_lines, 1):
            if install_cmd in line:
                i_line = idx
                break

        span1 = SourceSpan(file=readme_file, start_line=i_line, end_line=i_line, text=install_cmd)
        beats.append(Beat(
            say=tts_normalize_speech(say1),
            caption=f"Install: {install_cmd}",
            focus="install",
            sources=[span1],
            start_seconds=0.25,
            end_seconds=4.5,
        ))

    if usage_cmd:
        tokens = usage_cmd.split()
        if len(tokens) > 8:
            say2 = f"Next, execute the quickstart command shown on screen."
        else:
            say2 = f"Then execute {usage_cmd} to run {facts.repo_name}."

        u_line = 1
        for idx, line in enumerate(facts.readme.raw_lines, 1):
            if usage_cmd in line:
                u_line = idx
                break

        span2 = SourceSpan(file=readme_file, start_line=u_line, end_line=u_line, text=usage_cmd)
        beats.append(Beat(
            say=tts_normalize_speech(say2),
            caption=f"Run: {usage_cmd}",
            focus="run",
            sources=[span2],
            start_seconds=0.25,
            end_seconds=4.5,
        ))

    narration = " ".join(b.say for b in beats)
    return Scene(
        id="terminal",
        kind="terminal",
        title="Quickstart",
        narration=narration,
        beats=beats,
        duration_seconds=round(len(beats) * 4.5, 2),
    )
