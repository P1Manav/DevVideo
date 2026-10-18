"""
Schema definitions for the video generation pipeline.

Scene blueprint:
1. title    : repo name, owner, one-line purpose, language chips
2. overview : 'what it is / why it exists' from cleaned README
3. diagram  : architecture / module map from internal import graph
4. code     : key code path (<= 14 lines, verbatim from file)
5. terminal : typed quickstart commands (verbatim from README/CLI)
6. fit      : pipeline fit (domain relevance to video retrieval)
7. recap    : 3 takeaways + next files to check

Each scene has 2-4 beats (one sentence each, <= 22 words).
Visual state transitions beat-by-beat.
"""

from __future__ import annotations

import re
from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

BANNED_PHRASES = (
    "modular",
    "readable",
    "robust",
    "leverage",
    "seamless",
    "critical processing components",
    "state of the art",
    "structured for extension",
)


def normalize_speech(text: str) -> str:
    """
    Normalize spoken text for natural TTS pronunciation:
    - Replaces filenames like 'ingest.py' with 'ingest dot py'
    - Replaces underscores with spaces (e.g. 'search_video_index' -> 'search video index')
    - Strips markdown formatting characters (#, *, `, >)
    - Normalizes punctuation and whitespace
    """
    if not text:
        return ""
    # Extension replacement
    t = re.sub(
        r"\b([a-zA-Z0-9_-]+)\.(py|js|ts|json|jsonl|vtt|srt|mp4|wav|png|jpg|faiss|md|txt|yml|yaml|toml)\b",
        r"\1 dot \2",
        text,
    )
    # Underscores to spaces
    t = t.replace("_", " ")
    # Strip markdown symbols
    t = re.sub(r"[`#*<>]", "", t)
    # Normalize spaces
    return " ".join(t.split())


def check_for_banned_phrases(text: str) -> list[str]:
    """Return any banned buzzwords found in the text."""
    lower = text.lower()
    return [phrase for phrase in BANNED_PHRASES if phrase in lower]


class Beat(BaseModel):
    """
    One rhythm beat within a scene:
    - say: Spoken text (phonetically normalized for TTS)
    - caption: On-screen caption (short sentence, <= 22 words)
    - focus: Visual element ID, line number, or command to highlight
    """
    say: str
    caption: str
    focus: str | None = None
    start_seconds: float = 0.0
    end_seconds: float = 0.0


class OnScreen(BaseModel):
    """Visual asset specification for a scene."""
    type: Literal["title", "overview", "diagram", "code", "terminal", "fit", "recap", "text"] = "text"
    content: str = Field(..., min_length=1, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """
    Grounding evidence citing a real file in the repository:
    - file: Relative POSIX path in the repository
    - quote: Verbatim substring found in that file
    """
    file: str = Field(..., min_length=1)
    quote: str = Field(..., min_length=1, max_length=1000)


class Scene(BaseModel):
    """One scene in the explainer video."""
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    kind: Literal["title", "overview", "diagram", "code", "terminal", "fit", "recap", "text"] = "text"
    title: str = ""
    narration: str = Field(default="", min_length=10, max_length=1200)
    beats: list[Beat] = Field(default_factory=list)
    on_screen: OnScreen
    evidence: Evidence
    duration_seconds: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def validate_raw_narration(cls, data: Any) -> Any:
        if isinstance(data, dict):
            narr = data.get("narration", "")
            beats = data.get("beats", [])
            if not narr and beats:
                data["narration"] = " ".join(b.get("say", "") if isinstance(b, dict) else b.say for b in beats)
            elif narr:
                if not narr.strip():
                    raise ValueError("narration must contain non-whitespace text")
        return data

    @model_validator(mode="after")
    def sync_narration_and_beats(self) -> Scene:
        """Keep narration and beats in sync."""
        if not self.narration.strip():
            raise ValueError("narration must contain non-whitespace text")
        if self.beats and not self.narration:
            self.narration = " ".join(b.say for b in self.beats)
        elif self.narration and not self.beats:
            self.beats = [
                Beat(
                    say=normalize_speech(self.narration),
                    caption=self.narration[:100],
                )
            ]
        elif self.narration and self.beats:
            self.narration = " ".join(b.say for b in self.beats)
        return self

    def estimated_duration(self, wpm: float = 150.0) -> float:
        """Estimate narration duration in seconds based on word count."""
        words = len(self.narration.split())
        return max(2.0, (words / wpm) * 60.0)


class ScriptPlan(BaseModel):
    """Full script plan containing ordered scenes."""
    repo_name: str
    scenes: list[Scene] = Field(..., min_length=2, max_length=10)

    def estimated_duration_seconds(self, wpm: float = 150.0) -> float:
        """Estimate total speech duration across all scenes."""
        total_words = sum(len(s.narration.split()) for s in self.scenes)
        return max(2.0, (total_words / wpm) * 60.0)
