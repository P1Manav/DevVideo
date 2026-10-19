"""
Scene 6: Video Understanding & Retrieval Fit narration (Phase 4, N3, R8).
Always present in the final third. Strictly honest: only names evidenced pipeline stages.
"""
from __future__ import annotations

from ..analyze import RepoFacts
from ..schema import Beat, Scene, SourceSpan, is_disallowed_span
from .speech import tts_normalize_speech

# Standard pipeline ordering
PIPELINE_ORDER = ["decode", "transcribe", "embed", "index", "query", "serve"]


def build_fit_scene(facts: RepoFacts, readme_file: str) -> Scene:
    """
    R8, Phase 4: Honest video retrieval pipeline fit scene.
    >= 2 evidenced stages: narrate in pipeline order with repo evidence.
    0-1 evidenced stages: honest sentence:
      "<Repo> is not built for video retrieval, but you can feed this video's transcript, chapters and search index into a retrieval pipeline."
      plus second sentence about evidenced capability if 1 stage exists.
    """
    evidenced_stages = [stage for stage in PIPELINE_ORDER if stage in facts.pipeline_stages]

    beats: list[Beat] = []

    if len(evidenced_stages) >= 2:
        stages_str = ", ".join(evidenced_stages[:-1]) + f" and {evidenced_stages[-1]}"
        say1 = f"In video retrieval workflows, {facts.repo_name} covers the {stages_str} stages."
        caption1 = f"Pipeline Stages: {stages_str}"

        spans: list[SourceSpan] = []
        for st in evidenced_stages[:2]:
            quote = facts.pipeline_stages[st]
            q_line = 1
            for idx, line in enumerate(facts.readme.raw_lines, 1):
                if quote in line:
                    q_line = idx
                    break
            spans.append(SourceSpan(file=readme_file, start_line=q_line, end_line=q_line, text=quote))

        beats.append(Beat(
            say=tts_normalize_speech(say1),
            caption=caption1,
            focus="pipeline",
            sources=spans,
            start_seconds=0.25,
            end_seconds=5.0,
        ))
    else:
        # Honest fallback (0 or 1 evidenced stage)
        say1 = f"{facts.repo_name} is not built for video retrieval, but you can feed this video's transcript, chapters and search index into a retrieval pipeline."
        caption1 = "General tool: exports transcript, chapters, and index"

        prose_line = ""
        prose_line_idx = 1
        for idx, line in enumerate(facts.readme.raw_lines, 1):
            if not is_disallowed_span(line):
                prose_line = line.strip()
                prose_line_idx = idx
                break
        if not prose_line:
            prose_line = facts.readme.tagline or facts.repo_name

        spans1 = [SourceSpan(
            file=readme_file,
            start_line=prose_line_idx,
            end_line=prose_line_idx,
            text=prose_line,
        )]

        beats.append(Beat(
            say=tts_normalize_speech(say1),
            caption=caption1,
            focus="artifacts",
            sources=spans1,
            start_seconds=0.25,
            end_seconds=5.5,
        ))

        if len(evidenced_stages) == 1:
            st = evidenced_stages[0]
            quote = facts.pipeline_stages[st]
            say2 = f"It does handle {st} operations within multimedia processing."
            caption2 = f"Supported operation: {st}"
            from ..analyze import find_exact_line_range
            sp2, ep2 = find_exact_line_range(facts.readme.raw_lines, quote)
            beats.append(Beat(
                say=tts_normalize_speech(say2),
                caption=caption2,
                focus=st,
                sources=[SourceSpan(file=readme_file, start_line=sp2, end_line=ep2, text=quote)],
                start_seconds=0.25,
                end_seconds=4.0,
            ))

    narration = " ".join(b.say for b in beats)
    return Scene(
        id="fit",
        kind="fit",
        title="Pipeline Fit",
        narration=narration,
        beats=beats,
        duration_seconds=round(len(beats) * 5.0, 2),
    )
