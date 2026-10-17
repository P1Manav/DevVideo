"""
Schema definitions for the video generation pipeline.

Scene = one segment of the final video (narration + visual + evidence).
ScriptPlan = the full ordered list of scenes for one video.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OnScreen(BaseModel):
    """What the viewer sees during this scene."""
    type: Literal["code", "text", "diagram"] = "text"
    content: str = Field(..., min_length=1, max_length=2000)


class Evidence(BaseModel):
    """
    Links a scene's claims back to a real file in the repo.
    `file` is a relative path inside the cloned repo.
    `quote` is a verbatim substring that must appear in that file.
    """
    file: str = Field(..., min_length=1)
    quote: str = Field(..., min_length=1, max_length=500)


class Scene(BaseModel):
    """One scene in the video script."""
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    narration: str = Field(..., min_length=10, max_length=600)
    on_screen: OnScreen
    evidence: Evidence

    @field_validator("narration")
    @classmethod
    def narration_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("narration must contain non-whitespace text")
        return v


class ScriptPlan(BaseModel):
    """The full script: an ordered list of scenes."""
    repo_name: str
    scenes: list[Scene] = Field(..., min_length=2, max_length=8)

    def estimated_duration_seconds(self) -> float:
        """Rough estimate: ~150 words per minute for narration."""
        total_words = sum(len(s.narration.split()) for s in self.scenes)
        return (total_words / 150.0) * 60.0
