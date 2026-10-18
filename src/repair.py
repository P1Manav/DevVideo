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


class RepairDurationResult(str):
    """Result of repair_duration that behaves as both a string and a (action, rate) tuple."""
    def __new__(cls, action: str, rate: float = 1.0):
        obj = str.__new__(cls, action)
        obj.action = action
        obj.rate = rate
        return obj

    def __iter__(self):
        return iter((self.action, self.rate))


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

    def repair_overflow(self, scenes: list[Scene], overflow_scene_ids: list[str]) -> bool:
        """Step down font and content lines for overflowing scenes."""
        if not self.can_repair() or not overflow_scene_ids:
            return False

        repaired = False
        for s in scenes:
            if s.id in overflow_scene_ids:
                if s.on_screen:
                    # 1. Step down font size
                    if s.on_screen.metadata is None:
                        s.on_screen.metadata = {}
                    s.on_screen.metadata["font_size"] = "13px"
                    # 2. Step down lines if excessive
                    lines = s.on_screen.content.splitlines()
                    if len(lines) > 8:
                        s.on_screen.content = "\n".join(lines[:8]) + "\n... [truncated]"
                    self.repairs_applied.append(f"Reduced font and lines in {s.id} to resolve overflow")
                    repaired = True

        if repaired:
            self.attempts += 1
        return repaired

    def repair_duration(
        self,
        script: ScriptPlan,
        rate_multiplier: float = 1.0,
        tts_backend: Any = None,
    ) -> RepairDurationResult:
        """
        Duration repair sequence:
        1. +8% speech rate once.
        2. Drop recap bullets (trim recap to 1 takeaway) or drop recap scene.
        3. Drop lowest-priority scene.
        """
        if not self.can_repair():
            return RepairDurationResult("max_attempts_exceeded", rate_multiplier)

        self.attempts += 1

        # Attempt 1: +8% speech rate once
        if self.attempts == 1:
            new_rate = round(rate_multiplier * 1.08, 3)
            if tts_backend and hasattr(tts_backend, "speed"):
                tts_backend.speed = int(tts_backend.speed * 1.08)
            self.repairs_applied.append(f"Accelerated speech rate by +8% ({new_rate}x)")
            return RepairDurationResult("speed_increased", new_rate)

        # Attempt 2: Drop recap bullets or entire recap
        recap_idx = next((i for i, s in enumerate(script.scenes) if s.kind == "recap"), None)
        if recap_idx is not None:
            recap_scene = script.scenes[recap_idx]
            if len(recap_scene.beats) > 1 and not tts_backend:
                recap_scene.beats = recap_scene.beats[:1]
                recap_scene.narration = recap_scene.beats[0].say
                if recap_scene.on_screen and recap_scene.on_screen.metadata:
                    t_list = recap_scene.on_screen.metadata.get("takeaways", [])
                    if len(t_list) > 1:
                        recap_scene.on_screen.metadata["takeaways"] = t_list[:1]
                self.repairs_applied.append("Dropped recap bullets (trimmed to 1 takeaway)")
                return RepairDurationResult("dropped_recap_bullets", rate_multiplier)
            else:
                dropped = script.scenes.pop(recap_idx)
                self.repairs_applied.append(f"Dropped lowest-priority scene '{dropped.id}'")
                return RepairDurationResult("dropped_recap", rate_multiplier)

        # Attempt 3: Drop lowest-priority scene
        priority_order = ["terminal", "fit", "diagram", "overview", "recap"]
        for p_kind in priority_order:
            idx = next((i for i, s in enumerate(script.scenes) if s.kind == p_kind), None)
            if idx is not None and len(script.scenes) > 3:
                dropped = script.scenes.pop(idx)
                self.repairs_applied.append(f"Dropped lowest-priority scene '{dropped.id}'")
                return RepairDurationResult(f"dropped_{p_kind}", rate_multiplier)

        return RepairDurationResult("no_action", rate_multiplier)
