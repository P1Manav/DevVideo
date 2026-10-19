"""
Scene 6: Video Understanding & Retrieval Fit narration (Phase 2 & 6, R8).
Always present in the final third. Strictly honest: only names evidenced pipeline stages.
"""
from __future__ import annotations

from ..analyze import RepoFacts, find_exact_line_range
from ..schema import Beat, Scene, SourceSpan, is_disallowed_span
from .speech import tts_normalize_speech

# Standard pipeline ordering
PIPELINE_ORDER = ["decode", "transcribe", "embed", "index", "query", "serve"]


def build_fit_scene(facts: RepoFacts, readme_file: str) -> Scene:
    """
    R8, Phase 6: Honest video retrieval pipeline fit scene.
    >= 2 evidenced stages: "<Repo> handles the <stage list> steps of a video retrieval pipeline."
    1 evidenced stage: "<Repo> covers one step of a video retrieval pipeline: <stage>."
    0 stages: "<Repo> is not built for video retrieval, but you can feed this video's transcript, chapters and search index into a retrieval pipeline."
    """
    evidenced_stages = [stage for stage in PIPELINE_ORDER if stage in facts.pipeline_stages]
    beats: list[Beat] = []

    if len(evidenced_stages) >= 2:
        stages_str = ", ".join(evidenced_stages[:-1]) + f" and {evidenced_stages[-1]}"
        say1 = f"{facts.repo_name} handles the {stages_str} steps of a video retrieval pipeline."
        caption1 = f"Pipeline Stages: {stages_str}"

        spans: list[SourceSpan] = []
        for st in evidenced_stages:
            if st in facts.pipeline_stage_spans:
                spans.append(facts.pipeline_stage_spans[st])
            else:
                quote = facts.pipeline_stages.get(st, "")
                sp, ep = find_exact_line_range(facts.readme.raw_lines, quote)
                if sp > 0:
                    spans.append(SourceSpan(file=readme_file, start_line=sp, end_line=ep, text=quote))
                elif facts.readme.description_sentences:
                    first_sent = facts.readme.description_sentences[0]
                    spans.append(SourceSpan(file=readme_file, start_line=first_sent.start_line, end_line=first_sent.end_line, text=first_sent.text))

        beats.append(Beat(
            say=tts_normalize_speech(say1),
            caption=caption1,
            focus="pipeline",
            sources=spans[:4] if spans else [SourceSpan(file=readme_file, start_line=1, end_line=1, text=facts.repo_name)],
            start_seconds=0.25,
            end_seconds=5.0,
        ))

    elif len(evidenced_stages) == 1:
        st = evidenced_stages[0]
        say1 = f"{facts.repo_name} covers one step of a video retrieval pipeline: {st}."
        caption1 = f"Pipeline Stage: {st}"

        span: SourceSpan | None = facts.pipeline_stage_spans.get(st)
        if not span or span.start_line <= 0:
            quote = facts.pipeline_stages.get(st, "")
            sp, ep = find_exact_line_range(facts.readme.raw_lines, quote)
            if sp > 0:
                span = SourceSpan(file=readme_file, start_line=sp, end_line=ep, text=quote)
            elif facts.readme.description_sentences:
                first_sent = facts.readme.description_sentences[0]
                span = SourceSpan(file=readme_file, start_line=first_sent.start_line, end_line=first_sent.end_line, text=first_sent.text)
            else:
                span = SourceSpan(file=readme_file, start_line=1, end_line=1, text=facts.repo_name)

        beats.append(Beat(
            say=tts_normalize_speech(say1),
            caption=caption1,
            focus=st,
            sources=[span],
            start_seconds=0.25,
            end_seconds=4.5,
        ))

    else:
        # 0 stages
        say1 = f"{facts.repo_name} is not built for video retrieval, but you can feed this video's transcript, chapters and search index into a retrieval pipeline."
        caption1 = "Pipeline Fit: general tool"

        prose_line = ""
        prose_line_idx = 1
        for idx, line in enumerate(facts.readme.raw_lines, 1):
            if not is_disallowed_span(line) and line.strip():
                prose_line = line.strip()
                prose_line_idx = idx
                break
        if not prose_line:
            prose_line = facts.readme.tagline or facts.repo_name

        sp, ep = find_exact_line_range(facts.readme.raw_lines, prose_line)
        if sp <= 0:
            sp, ep = prose_line_idx, prose_line_idx

        spans1 = [SourceSpan(
            file=readme_file,
            start_line=sp,
            end_line=ep,
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

    narration = " ".join(b.say for b in beats)
    return Scene(
        id="fit",
        kind="fit",
        title="Pipeline Fit",
        narration=narration,
        beats=beats,
        duration_seconds=round(len(beats) * 5.0, 2),
    )
