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
    "primary implementation logic",
    "structured solutions",
    "developer workflows",
    "we explore",
    "this project organizes",
    "provides critical",
    "utilizes",
    "powers multimodal",
    "modular",
    "readable",
    "robust",
    "leverage",
    "seamless",
    "state of the art",
    "critical processing components",
    "structured for extension",
)


def normalize_speech(text: str) -> str:
    """
    Normalize spoken text for natural TTS pronunciation:
    - Replaces filenames like 'ingest.py' with 'ingest dot py'
    - Replaces underscores with spaces (e.g. 'search_video_index' -> 'search video index')
    - Replaces CLI flags like '--top-k' with 'top k'
    - Strips markdown formatting characters (#, *, `, >)
    - Normalizes punctuation and whitespace
    """
    if not text:
        return ""
    # Flag replacement (--foo-bar -> foo bar)
    t = re.sub(r"--([a-zA-Z0-9_-]+)", lambda m: m.group(1).replace("-", " ").replace("_", " "), text)
    # Extension replacement
    t = re.sub(
        r"\b([a-zA-Z0-9_-]+)\.(py|js|ts|json|jsonl|vtt|srt|mp4|wav|png|jpg|faiss|md|txt|yml|yaml|toml)\b",
        r"\1 dot \2",
        t,
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


class SourceSpan(BaseModel):
    """
    Source provenance tracking a slice of text in a repo file:
    - file: Relative POSIX path in the repository
    - start_line: 1-indexed start line
    - end_line: 1-indexed end line
    - text: Verbatim text slice
    """
    file: str = Field(..., min_length=1)
    start_line: int = 1
    end_line: int = 1
    text: str = ""


def is_disallowed_span(text: str) -> bool:
    """Disallow spans whose text is a link row, badge, heading-only, table row or an HTML tag line."""
    t = text.strip()
    if not t:
        return True
    # Badge or markdown image [![...](...)] or ![...](...)
    if re.match(r"^\[?!\[.*?\]\(.*?\)\]?", t):
        return True
    # Link row (multiple [[Link]](...) or [Link](...))
    if re.match(r"^(?:\[+[^\]]+\]+\([^)]+\)\s*)+$", t):
        return True
    # Heading only (# Heading)
    if re.match(r"^#{1,6}\s+", t):
        return True
    # Table row (| col1 | col2 |)
    if t.startswith("|") and t.endswith("|"):
        return True
    # HTML tag line (<div>, <br>, <h1>...</h1>)
    if re.match(r"^<[^>]+>$", t) or re.match(r"^<[a-z0-9_-]+(\s+[^>]*?)?>.*?</[a-z0-9_-]+>$", t, re.I):
        return True
    return False


class Beat(BaseModel):
    """
    One rhythm beat within a scene:
    - say: Spoken text (phonetically normalized for TTS)
    - caption: On-screen caption (short sentence, <= 22 words)
    - focus: Visual element ID, line range 'a-b', command index, or bullet index
    - sources: Provenance citations justifying this beat (deduped, max 3)
    """
    say: str
    caption: str
    focus: str | None = None
    sources: list[SourceSpan] = Field(default_factory=list)
    start_seconds: float = 0.0
    end_seconds: float = 0.0

    @model_validator(mode="after")
    def deduplicate_and_cap_sources(self) -> Beat:
        seen = set()
        deduped = []
        for s in self.sources:
            key = (s.file, s.start_line, s.end_line, s.text.strip())
            if key not in seen:
                seen.add(key)
                deduped.append(s)
            if len(deduped) == 3:
                break
        self.sources = deduped
        return self


class OnScreen(BaseModel):
    """Visual asset specification for a scene (authored by visuals.py from RepoFacts)."""
    type: Literal["title", "overview", "diagram", "code", "terminal", "fit", "recap", "text"] = "text"
    content: str = Field(default="pending visuals", min_length=1, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    """
    Grounding evidence citing a real file in the repository (compatibility layer).
    """
    file: str = Field(default="README.md")
    quote: str = Field(default="", max_length=1000)


class Scene(BaseModel):
    """One scene in the explainer video."""
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    kind: Literal["title", "overview", "diagram", "code", "terminal", "fit", "recap", "text"] = "text"
    title: str = ""
    narration: str = Field(default="", min_length=10, max_length=1200)
    beats: list[Beat] = Field(default_factory=list)
    on_screen: OnScreen = Field(default_factory=lambda: OnScreen(type="text", content="pending visuals"))
    evidence: Evidence = Field(default_factory=lambda: Evidence(file="README.md", quote=""))
    duration_seconds: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def validate_raw_data(cls, data: Any) -> Any:
        if isinstance(data, dict):
            narr = data.get("narration", "")
            beats = data.get("beats", [])
            if not narr and beats:
                data["narration"] = " ".join(
                    b.get("say", "") if isinstance(b, dict) else getattr(b, "say", "")
                    for b in beats
                )
            elif narr:
                if not str(narr).strip():
                    raise ValueError("narration must contain non-whitespace text")
            # Default kind to id if known
            if "kind" not in data or data.get("kind") == "text":
                cid = data.get("id", "")
                if cid in ("title", "overview", "diagram", "code", "terminal", "fit", "recap"):
                    data["kind"] = cid
        return data

    @model_validator(mode="after")
    def sync_narration_and_beats(self) -> Scene:
        """Keep narration, beats, evidence, and provenance in sync."""
        if not self.narration.strip():
            raise ValueError("narration must contain non-whitespace text")

        if self.beats and not self.narration:
            self.narration = " ".join(b.say for b in self.beats)
        elif self.narration and not self.beats:
            srcs = []
            if self.evidence and self.evidence.file:
                srcs.append(
                    SourceSpan(
                        file=self.evidence.file,
                        start_line=1,
                        end_line=1,
                        text=self.evidence.quote or self.narration,
                    )
                )
            self.beats = [
                Beat(
                    say=normalize_speech(self.narration),
                    caption=self.narration[:100],
                    sources=srcs,
                )
            ]
        elif self.narration and self.beats:
            self.narration = " ".join(b.say for b in self.beats)

        # Enforce provenance rule:
        # A beat without >= 1 source is invalid unless kind in {title, recap}
        if self.kind not in ("title", "recap"):
            for i, beat in enumerate(self.beats):
                if not beat.sources:
                    if self.evidence and self.evidence.file and self.evidence.quote:
                        beat.sources.append(
                            SourceSpan(
                                file=self.evidence.file,
                                start_line=1,
                                end_line=1,
                                text=self.evidence.quote,
                            )
                        )
                    else:
                        raise ValueError(
                            f"Beat {i} in scene '{self.id}' (kind='{self.kind}') must have at least 1 source span"
                        )

        # Compatibility: ensure evidence is set from first beat source if missing
        if (not self.evidence or not self.evidence.quote) and self.beats:
            for b in self.beats:
                if b.sources and b.sources[0].text:
                    self.evidence = Evidence(file=b.sources[0].file, quote=b.sources[0].text)
                    break

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
