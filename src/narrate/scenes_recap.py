"""
Scene 7: Takeaways & Recap narration (T1, T8, R3, R9).
Picks first-party entry file (never examples/tests), summarizes grounded takeaways without filler.
"""
from __future__ import annotations

from ..analyze import RepoFacts, is_auxiliary_or_test_path
from ..schema import Beat, Scene, SourceSpan
from .compress import clean_caption_text, compress_sentence, has_verb, is_dangling
from .speech import tts_normalize_speech


def select_recap_entry_file(facts: RepoFacts) -> str | None:
    """T8: Choose first-party package entry file. NEVER examples/, tests/, docs/."""
    candidates = []
    if facts.entry_module and not is_auxiliary_or_test_path(facts.entry_module):
        return facts.entry_module

    for m in facts.ranked_top_modules:
        if not is_auxiliary_or_test_path(m):
            candidates.append(m)

    if candidates:
        return candidates[0]

    for s in facts.top_symbols:
        if s.file and not is_auxiliary_or_test_path(s.file):
            return s.file

    return None


def build_recap_scene(facts: RepoFacts, readme_file: str) -> Scene:
    """R3, R9, T8: Recap scene with truth-only summary and validated entry file."""
    from ..schema import check_for_banned_phrases
    title = facts.readme.title or facts.repo_name
    beats: list[Beat] = []

    # Beat 1: Grounded summary (filter banned buzzwords like 'robust')
    desc_sents = [s for s in facts.readme.description_sentences if s.text and not check_for_banned_phrases(s.text)]
    if desc_sents:
        comp_desc = compress_sentence(desc_sents[0].text, max_words=14)
        summary_phrase = comp_desc[0].rstrip(".") if comp_desc else desc_sents[0].text.rstrip(".")
        say1 = f"In short, {summary_phrase}."
        q_line = desc_sents[0].start_line
        quote1 = desc_sents[0].text
    elif facts.readme.tagline and not check_for_banned_phrases(facts.readme.tagline):
        comp_tag = compress_sentence(facts.readme.tagline, max_words=14)
        summary_phrase = comp_tag[0].rstrip(".") if comp_tag else facts.readme.tagline.rstrip(".")
        say1 = f"In short, {summary_phrase}."
        q_line = 1
        quote1 = facts.readme.tagline
    else:
        say1 = f"In short, this overview outlines the structure of {title}."
        summary_phrase = title
        q_line = 1
        quote1 = title

    beats.append(Beat(
        say=tts_normalize_speech(say1),
        caption=f"Summary: {clean_caption_text(summary_phrase, 6)}",
        focus="recap",
        sources=[SourceSpan(file=readme_file, start_line=q_line, end_line=q_line, text=quote1)],
        start_seconds=0.25,
        end_seconds=4.5,
    ))

    # Beat 2: Entry point to explore (T8: first-party only)
    entry_f = select_recap_entry_file(facts)
    if entry_f:
        say2 = f"To get started, explore {facts.repo_name} starting with {entry_f}."
        caption2 = f"Next Step: inspect {entry_f}"
        m_doc = next((m for m in facts.module_docstrings if m.file == entry_f), None)
        if m_doc:
            span2 = m_doc.span
        else:
            sym = next((s for s in facts.top_symbols if s.file == entry_f), None)
            if sym:
                span2 = SourceSpan(file=entry_f, start_line=sym.start_line, end_line=sym.end_line, text=sym.def_line or sym.name)
            else:
                edge = next((e for e in facts.import_graph if e.source == entry_f and e.raw_line), None)
                if edge:
                    span2 = SourceSpan(file=entry_f, start_line=edge.line_number, end_line=edge.line_number, text=edge.raw_line)
                else:
                    from ..analyze import find_exact_line_range
                    sp2, ep2 = find_exact_line_range(facts.readme.raw_lines, entry_f)
                    txt2 = entry_f if any(entry_f in l for l in facts.readme.raw_lines) else (facts.readme.title or facts.repo_name)
                    span2 = SourceSpan(file=readme_file, start_line=sp2, end_line=ep2, text=txt2)

        beats.append(Beat(
            say=tts_normalize_speech(say2),
            caption=caption2,
            focus="next_steps",
            sources=[span2],
            start_seconds=0.25,
            end_seconds=4.5,
        ))

    narration = " ".join(b.say for b in beats)
    return Scene(
        id="recap",
        kind="recap",
        title="Conclusion",
        narration=narration,
        beats=beats,
        duration_seconds=round(len(beats) * 4.5, 2),
    )
