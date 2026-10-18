"""
Repair module: bounded automatic repairs before rejecting a video.

Bounded repairs (max 2 attempts):
1. Text overflow -> fewer lines / smaller font
2. Duration > 58s -> speak 8% faster once, then drop lowest-priority scene (recap)
3. Invalid command -> replace by verified README line or drop it
"""

from __future__ import annotations

import logging
from typing import Any

from .evals.gates import extract_commands
from .schema import ScriptPlan, Scene

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 2


class RepairManager:
    """Coordinates up to 2 automatic repair attempts before final rejection."""

    def __init__(self, max_attempts: int = MAX_REPAIR_ATTEMPTS) -> None:
        self.max_attempts = max_attempts
        self.attempts = 0
        self.repairs_applied: list[str] = []

    def can_repair(self) -> bool:
        return self.attempts < self.max_attempts

    def repair_invalid_commands(self, script: ScriptPlan, repo_files: dict[str, str]) -> bool:
        """Replace unverified commands with valid repo commands or drop them."""
        if not self.can_repair():
            return False

        all_repo_text = "\n".join(repo_files.values())
        # Find all valid commands in repo
        valid_pool = extract_commands(all_repo_text)

        repaired = False
        for scene in script.scenes:
            cmds = extract_commands(scene.on_screen.content)
            new_lines = []
            for line in scene.on_screen.content.splitlines():
                line_cmd = line.strip()
                if line_cmd.startswith("$ "):
                    cmd_val = line_cmd[2:].strip()
                else:
                    cmd_val = line_cmd

                if cmd_val in cmds and cmd_val not in all_repo_text:
                    # Invalid command found! Try replacing with a valid command from pool
                    if valid_pool:
                        replacement = valid_pool[0]
                        prefix = "$ " if line_cmd.startswith("$ ") else ""
                        new_lines.append(f"{prefix}{replacement}")
                        self.repairs_applied.append(f"Replaced invalid command '{cmd_val}' with '{replacement}' in {scene.id}")
                    else:
                        self.repairs_applied.append(f"Dropped invalid command '{cmd_val}' from {scene.id}")
                    repaired = True
                else:
                    new_lines.append(line)
            scene.on_screen.content = "\n".join(new_lines)

        if repaired:
            self.attempts += 1
        return repaired

    def repair_overflow(self, scenes: list[Scene], overflow_scene_ids: list[str]) -> bool:
        """Step down content lines for overflowing scenes."""
        if not self.can_repair() or not overflow_scene_ids:
            return False

        repaired = False
        for s in scenes:
            if s.id in overflow_scene_ids:
                lines = s.on_screen.content.splitlines()
                if len(lines) > 8:
                    s.on_screen.content = "\n".join(lines[:8]) + "\n... [truncated]"
                    self.repairs_applied.append(f"Truncated content in {s.id} to 8 lines to resolve overflow")
                    repaired = True

        if repaired:
            self.attempts += 1
        return repaired

    def repair_duration(self, script: ScriptPlan, tts_backend: Any = None) -> str:
        """
        Repair duration > 58s:
        Attempt 1: speed up TTS by 8%.
        Attempt 2: drop lowest-priority scene (recap).
        """
        if not self.can_repair():
            return "max_attempts_exceeded"

        self.attempts += 1
        # Attempt 1: Speed up speech
        if self.attempts == 1 and tts_backend and hasattr(tts_backend, "speed"):
            old_speed = tts_backend.speed
            tts_backend.speed = int(old_speed * 1.08)
            action = f"Increased TTS speed from {old_speed} to {tts_backend.speed}"
            self.repairs_applied.append(action)
            return "speed_increased"

        # Attempt 2: Drop lowest priority scene (recap)
        recap_idx = next((i for i, s in enumerate(script.scenes) if s.kind == "recap"), None)
        if recap_idx is not None:
            dropped = script.scenes.pop(recap_idx)
            action = f"Dropped lowest-priority scene '{dropped.id}'"
            self.repairs_applied.append(action)
            return "dropped_recap"

        return "no_action"
