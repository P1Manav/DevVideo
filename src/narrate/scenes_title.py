"""
Scene 1: Title & Identity narration (T1, T2, R10).
Dominant language comes strictly from first-party code. No language claim if no first-party code exists.
"""
from __future__ import annotations

import re
from ..analyze import RepoFacts
from ..schema import Beat, Scene, SourceSpan, check_for_banned_phrases
from .compress import compress_sentence, is_dangling
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
            say_text = f"{title}. The repository contains a README with project documentation."
        else:
            say_text = f"{title} is built with {top_lang}."
        tag_phrase = title
        quoted_text = title
        from ..analyze import find_exact_line_range
        sp, ep = find_exact_line_range(facts.readme.raw_lines, quoted_text)
    else:
        # Compress tagline cleanly per R1
        compressed_tagline = compress_sentence(tagline, max_words=16)
        tag_phrase = compressed_tagline[0] if compressed_tagline else tagline

        if tag_phrase.lower().startswith(title.lower()):
            say_text = tag_phrase
        else:
            say_text = f"{title}. {tag_phrase}"

        from ..analyze import find_exact_line_range
        quoted_text = tagline
        sp, ep = find_exact_line_range(facts.readme.raw_lines, quoted_text)

    from .compress import clean_caption_text
    spoken_say = tts_normalize_speech(say_text)
    caption_text = f"{title}: {clean_caption_text(tag_phrase, 8)}"

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
