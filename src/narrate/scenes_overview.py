"""
Scene 2: Overview & Purpose narration (Phase 3 & S1, T1, T3, T9, R7).
SAY LESS, NEVER FILL. Spoken sentences strictly derived from cited source spans.
Overview captions and on-screen points align directly with spoken clauses.
"""
from __future__ import annotations

import re
from ..analyze import RepoFacts, find_exact_line_range
from ..schema import Beat, Scene, SourceSpan, check_for_banned_phrases
from .compress import compress_sentence, fit_clause, has_verb
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
            caption = "README repository"
        else:
            top_lang = next(iter(facts.languages_by_bytes.keys()))
            say = f"{title} includes source files written in {top_lang}."
            caption = f"Source files: {top_lang}"

        txt = title
        sp, ep = find_exact_line_range(facts.readme.raw_lines, txt)
        if sp <= 0:
            sp, ep = 1, 1

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
        if not has_verb(say1):
            transformed = transform_bullet_to_sentence(b1_sent.lstrip("-*• "))
            say1 = transformed if transformed else f"{facts.repo_name} provides {b1_sent.lstrip('-*• ').rstrip('.')}."
        caption1 = fit_clause(say1, max_chars=60)
        sp1 = desc_sents[0].start_line
        ep1 = desc_sents[0].end_line
        quote1 = b1_sent
    elif features:
        transformed = transform_bullet_to_sentence(features[0])
        say1 = transformed if transformed else f"{facts.repo_name} provides {features[0].rstrip('.')}."
        caption1 = fit_clause(features[0], max_chars=60)
        quote1 = features[0]
        sp1, ep1 = find_exact_line_range(facts.readme.raw_lines, quote1)
        if sp1 <= 0:
            sp1, ep1 = 1, 1
    else:
        say1 = facts.readme.tagline or facts.repo_name
        caption1 = fit_clause(say1, max_chars=60)
        quote1 = say1
        sp1, ep1 = find_exact_line_range(facts.readme.raw_lines, quote1)
        if sp1 <= 0:
            sp1, ep1 = 1, 1

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
        if not has_verb(say2):
            transformed = transform_bullet_to_sentence(b2_sent.lstrip("-*• "))
            say2 = transformed if transformed else f"{facts.repo_name} includes {b2_sent.lstrip('-*• ').rstrip('.')}."
        caption2 = fit_clause(say2, max_chars=60)
        beats.append(Beat(
            say=tts_normalize_speech(say2),
            caption=caption2,
            focus="operation",
            sources=[SourceSpan(file=readme_file, start_line=desc_sents[1].start_line, end_line=desc_sents[1].end_line, text=b2_sent)],
            start_seconds=0.25,
            end_seconds=5.0,
        ))
    elif features:
        bullet_idx = 1 if len(features) > 1 and desc_sents else 0
        feat_raw = features[bullet_idx]
        transformed = transform_bullet_to_sentence(feat_raw)
        if transformed:
            say2 = transformed
            caption2 = fit_clause(feat_raw, max_chars=60)
            sp2, ep2 = find_exact_line_range(facts.readme.raw_lines, feat_raw)
            if sp2 <= 0:
                sp2, ep2 = 1, 1
            beats.append(Beat(
                say=tts_normalize_speech(say2),
                caption=caption2,
                focus="operation",
                sources=[SourceSpan(file=readme_file, start_line=sp2, end_line=ep2, text=feat_raw)],
                start_seconds=0.25,
                end_seconds=5.0,
            ))

    # Beat 3: What you get (if CLI flags or additional features exist)
    flag_help = (facts.cli_flag_details[0].help.strip() if facts.cli_flag_details and facts.cli_flag_details[0].help else "")
    flag_in_readme = False
    if flag_help and find_exact_line_range(facts.readme.raw_lines, flag_help)[0] > 0:
        flag_in_readme = True
    elif facts.cli_flags and find_exact_line_range(facts.readme.raw_lines, facts.cli_flags[0])[0] > 0:
        flag_in_readme = True

    if facts.cli_flags and flag_in_readme:
        flags_str = " and ".join(facts.cli_flags[:2])
        say3 = f"It supports the {flags_str} command line flags."
        caption3 = f"CLI Flags: {flags_str}"
        quote3 = flag_help or facts.cli_flags[0]
        sp3, ep3 = find_exact_line_range(facts.readme.raw_lines, quote3)
        if sp3 <= 0:
            sp3, ep3 = (desc_sents[0].start_line if desc_sents else 1), (desc_sents[0].end_line if desc_sents else 1)
        beats.append(Beat(
            say=tts_normalize_speech(say3),
            caption=caption3,
            focus="features",
            sources=[SourceSpan(file=readme_file, start_line=sp3, end_line=ep3, text=quote3)],
            start_seconds=0.25,
            end_seconds=4.5,
        ))
    elif len(features) > (2 if desc_sents else 1):
        bullet_idx = 2 if desc_sents else 1
        feat_raw = features[bullet_idx]
        transformed = transform_bullet_to_sentence(feat_raw)
        say3 = transformed if transformed else f"{facts.repo_name} provides {feat_raw.rstrip('.')}."
        caption3 = fit_clause(feat_raw, max_chars=60)
        sp3, ep3 = find_exact_line_range(facts.readme.raw_lines, feat_raw)
        if sp3 <= 0:
            sp3, ep3 = (desc_sents[0].start_line if desc_sents else 1), (desc_sents[0].end_line if desc_sents else 1)
        beats.append(Beat(
            say=tts_normalize_speech(say3),
            caption=caption3,
            focus="features",
            sources=[SourceSpan(file=readme_file, start_line=sp3, end_line=ep3, text=feat_raw)],
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
