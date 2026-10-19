"""
Scene 2: Overview & Purpose narration (T1, T3, T9, R7).
SAY LESS, NEVER FILL. Spoken sentences strictly derived from cited source spans.
"""
from __future__ import annotations

import re
from ..analyze import RepoFacts
from ..schema import Beat, Scene, SourceSpan, check_for_banned_phrases
from .compress import clean_caption_text, compress_sentence
from .speech import tts_normalize_speech
from .verbs import transform_bullet_to_sentence


def build_overview_scene(facts: RepoFacts, readme_file: str) -> Scene:
    """
    R7/T9: Overview scene with up to 3 beats:
    Beat 1: What it is (primary description sentence)
    Beat 2: What it does (next description sentence or transformed bullet)
    Beat 3: What you get (feature bullet or CLI flag)
    If no prose exists (readme_only / no_prose_readme), state facts honestly.
    """
    beats: list[Beat] = []
    tagline_lower = facts.readme.tagline.strip().lower() if facts.readme.tagline else ""
    desc_sents = [
        s for s in facts.readme.description_sentences
        if not check_for_banned_phrases(s.text) and (not tagline_lower or s.text.strip().lower() != tagline_lower)
    ]
    features = [f for f in facts.readme.features if not check_for_banned_phrases(f)]

    # Handle repos with no prose (e.g. readme_only, no_prose_readme)
    if not desc_sents and not features and not facts.readme.feature_sentences:
        title = facts.readme.title or facts.repo_name
        has_code = bool(facts.languages_by_bytes)
        if not has_code:
            say = f"The repository contains a README and nothing else."
            caption = "README only repository"
        else:
            top_lang = next(iter(facts.languages_by_bytes.keys()))
            say = f"{title} includes source files written in {top_lang}."
            caption = f"Source files: {top_lang}"

        from ..analyze import find_exact_line_range
        txt = title
        sp, ep = find_exact_line_range(facts.readme.raw_lines, txt)

        beats.append(Beat(
            say=tts_normalize_speech(say),
            caption=caption,
            focus="concept",
            sources=[SourceSpan(file=readme_file, start_line=sp, end_line=ep, text=txt)],
            start_seconds=0.25,
            end_seconds=4.5,
        ))

        return Scene(
            id="overview",
            kind="overview",
            title="Purpose",
            narration=beats[0].say,
            beats=beats,
            duration_seconds=4.5,
        )

    # Beat 1: What it is
    if desc_sents:
        b1_sent = desc_sents[0].text
        comp_b1 = compress_sentence(b1_sent, max_words=18)
        say1 = comp_b1[0] if comp_b1 else b1_sent
        caption1 = f"What it is: {clean_caption_text(say1, 6)}"
        sp1 = desc_sents[0].start_line
        ep1 = desc_sents[0].end_line
        quote1 = b1_sent
    elif features:
        transformed = transform_bullet_to_sentence(features[0])
        say1 = transformed if transformed else f"{facts.repo_name} provides {features[0].rstrip('.')}."
        caption1 = clean_caption_text(features[0], 6)
        quote1 = features[0]
        sp1 = 1
        ep1 = 1
        for idx, line in enumerate(facts.readme.raw_lines, 1):
            if quote1 in line:
                sp1, ep1 = idx, idx
                break
    else:
        say1 = facts.readme.tagline or facts.repo_name
        caption1 = clean_caption_text(say1, 6)
        quote1 = say1
        from ..analyze import find_exact_line_range
        sp1, ep1 = find_exact_line_range(facts.readme.raw_lines, quote1)

    beats.append(Beat(
        say=tts_normalize_speech(say1),
        caption=caption1,
        focus="concept",
        sources=[SourceSpan(file=readme_file, start_line=sp1, end_line=ep1, text=quote1)],
        start_seconds=0.25,
        end_seconds=5.0,
    ))

    # Beat 2: What it does
    if len(desc_sents) > 1:
        b2_sent = desc_sents[1].text
        comp_b2 = compress_sentence(b2_sent, max_words=18)
        say2 = comp_b2[0] if comp_b2 else b2_sent
        caption2 = f"Capabilities: {clean_caption_text(say2, 6)}"
        beats.append(Beat(
            say=tts_normalize_speech(say2),
            caption=caption2,
            focus="operation",
            sources=[SourceSpan(file=readme_file, start_line=desc_sents[1].start_line, end_line=desc_sents[1].end_line, text=b2_sent)],
            start_seconds=0.25,
            end_seconds=5.0,
        ))
    elif features:
        # Use first or second bullet transformed
        bullet_idx = 1 if len(features) > 1 and desc_sents else 0
        feat_raw = features[bullet_idx]
        transformed = transform_bullet_to_sentence(feat_raw)
        if transformed:
            say2 = transformed
            caption2 = f"Capabilities: {clean_caption_text(feat_raw, 6)}"
            sp2 = 1
            ep2 = 1
            for idx, line in enumerate(facts.readme.raw_lines, 1):
                if feat_raw in line:
                    sp2, ep2 = idx, idx
                    break
            beats.append(Beat(
                say=tts_normalize_speech(say2),
                caption=caption2,
                focus="operation",
                sources=[SourceSpan(file=readme_file, start_line=sp2, end_line=ep2, text=feat_raw)],
                start_seconds=0.25,
                end_seconds=5.0,
            ))

    # Beat 3: What you get (if CLI flags or additional features exist)
    if facts.cli_flags:
        flags_str = " and ".join(facts.cli_flags[:2])
        say3 = f"It supports the {flags_str} command line flags."
        caption3 = f"Flags: {flags_str}"
        quote3 = facts.cli_flag_details[0].help if facts.cli_flag_details else flags_str
        beats.append(Beat(
            say=tts_normalize_speech(say3),
            caption=caption3,
            focus="features",
            sources=[SourceSpan(file=readme_file, start_line=1, end_line=1, text=quote3)],
            start_seconds=0.25,
            end_seconds=4.5,
        ))

    narration = " ".join(b.say for b in beats)
    return Scene(
        id="overview",
        kind="overview",
        title="Purpose",
        narration=narration,
        beats=beats,
        duration_seconds=round(len(beats) * 4.8, 2),
    )
