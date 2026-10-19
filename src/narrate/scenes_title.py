"""
Scene 1: Title & Identity narration (Phase 3 & 7, T1, T2, R10).
Dominant language comes strictly from first-party code. No language claim if no first-party code exists.
"""
from __future__ import annotations

import re
from ..analyze import RepoFacts, find_exact_line_range
from ..schema import Beat, Scene, SourceSpan, check_for_banned_phrases
from .compress import compress_sentence, fit_clause, is_dangling
from .speech import tts_normalize_speech


def build_title_scene(facts: RepoFacts, readme_file: str) -> Scene:
    """R10: dominant code language, owner only when known, R1 compressed title beat."""
    title = facts.readme.title
    if not title or len(title.split()) > 6 or "[" in title or check_for_banned_phrases(title):
        title = facts.repo_name

    tagline = facts.readme.tagline
    if not tagline or check_for_banned_phrases(tagline):
        clean_sents = [s for s in facts.readme.description_sentences if not check_for_banned_phrases(s.text)]
        if clean_sents:
            tagline = clean_sents[0].text

    # T2: Language check: only count first-party languages
    has_code = bool(facts.languages_by_bytes)
    top_lang = next(iter(facts.languages_by_bytes.keys()), None) if has_code else None

    # Truth-first: if no prose exists and no code, state facts honestly
    if not tagline or check_for_banned_phrases(tagline):
        if not has_code:
            short_readme = facts.readme.description or (facts.readme.raw_lines[0].strip() if facts.readme.raw_lines else "")
            if short_readme and len(short_readme.split()) <= 6:
                say_text = f"This repository contains a README that says {short_readme.rstrip('.')}."
            else:
                say_text = f"The repository contains a README and nothing else."
        else:
            say_text = f"{title} is built with {top_lang}."
        tag_phrase = title
        quoted_text = title
        sp, ep = find_exact_line_range(facts.readme.raw_lines, quoted_text)
    else:
        # Compress tagline cleanly per R1
        compressed_tagline = compress_sentence(tagline, max_words=16)
        tag_phrase = compressed_tagline[0] if compressed_tagline else tagline

        clean_title = re.sub(r"[^\w\s-]", "", title).strip().lower()
        starts_with_title = tag_phrase.lower().startswith(title.lower()) or (
            bool(clean_title) and tag_phrase.lower().startswith(clean_title)
        )
        if starts_with_title:
            say_text = tag_phrase
        else:
            say_text = f"{title}. {tag_phrase}"

        quoted_text = tagline
        sp, ep = find_exact_line_range(facts.readme.raw_lines, quoted_text)

    spoken_say = tts_normalize_speech(say_text)
    caption_clause = fit_clause(tag_phrase, max_chars=60)
    clean_title = re.sub(r"[^\w\s-]", "", title).strip().lower()
    caption_starts_with_title = caption_clause.lower().startswith(title.lower()) or (
        bool(clean_title) and caption_clause.lower().startswith(clean_title)
    )
    if caption_starts_with_title:
        caption_text = caption_clause
    else:
        caption_text = f"{title}: {caption_clause}"

    if sp <= 0:
        sp, ep = 1, 1

    source_span = SourceSpan(
        file=readme_file,
        start_line=sp,
        end_line=ep,
        text=quoted_text,
    )

    beat = Beat(
        say=spoken_say,
        caption=caption_text,
        focus=facts.repo_name,
        sources=[source_span],
        start_seconds=0.25,
        end_seconds=4.5,
    )
    return Scene(
        id="title",
        kind="title",
        title="Overview",
        narration=spoken_say,
        beats=[beat],
        duration_seconds=4.5,
    )
