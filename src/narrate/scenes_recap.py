"""
Scene 7: Takeaways & Recap narration (Phase 3 & 7, T1, T8, R3, R9).
Picks first-party entry file (never examples/tests), summarizes grounded takeaways without filler.
Never repeats the title scene sentence.
"""
from __future__ import annotations

from pathlib import Path
import re
from ..analyze import RepoFacts, find_exact_line_range, is_auxiliary_or_test_path
from ..schema import Beat, Scene, SourceSpan
from .compress import compress_sentence, fit_clause
from .speech import tts_normalize_speech


def select_recap_entry_file(facts: RepoFacts) -> str | None:
    """T8: Choose first-party package entry file. NEVER examples/, tests/, docs/."""
    candidates = []
    if facts.entry_module and not is_auxiliary_or_test_path(facts.entry_module):
        return facts.entry_module

    candidates = [m for m in facts.ranked_top_modules if not is_auxiliary_or_test_path(m)]
    # Prefer public non-underscore modules (e.g. ffmpeg/nodes.py over internal ffmpeg/_filters.py)
    public = [m for m in candidates if not Path(m).name.startswith("_") or Path(m).name == "__init__.py"]
    if public:
        return public[0]
    if candidates:
        return candidates[0]

    for s in facts.top_symbols:
        if s.file and not is_auxiliary_or_test_path(s.file):
            return s.file

    return None


def _lower_lead_in(text: str) -> str:
    if not text:
        return text
    words = text.split(maxsplit=1)
    first_word = words[0]
    rest = (" " + words[1]) if len(words) > 1 else ""
    if first_word.isupper() or first_word in ("Python", "FFmpeg", "CLIP", "VidSearch", "Faiss", "OpenCLIP", "HTML"):
        return text
    return first_word.lower() + rest


def build_recap_scene(facts: RepoFacts, readme_file: str) -> Scene:
    """R3, R9, T8: Recap scene with truth-only summary and validated entry file."""
    from ..schema import check_for_banned_phrases
    title = facts.readme.title or facts.repo_name
    beats: list[Beat] = []

    # Exclude sentence used in title scene to prevent repeating the exact same sentence
    title_text = (facts.readme.tagline or "").strip().lower()
    desc_sents = [
        s for s in facts.readme.description_sentences
        if s.text and not check_for_banned_phrases(s.text)
    ]
    from .compress import has_verb
    from .verbs import transform_bullet_to_sentence
    diff_sents = [s for s in desc_sents if s.text.strip().lower() != title_text]

    if diff_sents:
        raw_text = diff_sents[0].text.lstrip("-*• ")
        comp_desc = compress_sentence(raw_text, max_words=14)
        summary_phrase = comp_desc[0].rstrip(".") if comp_desc else raw_text.rstrip(".")
        if not has_verb(summary_phrase):
            transformed = transform_bullet_to_sentence(summary_phrase)
            summary_phrase = transformed if transformed else f"{title} provides {summary_phrase}"
        say1 = f"In summary, {_lower_lead_in(summary_phrase)}."
        span1 = SourceSpan(file=readme_file, start_line=diff_sents[0].start_line, end_line=diff_sents[0].end_line, text=diff_sents[0].text)
    elif facts.readme and facts.readme.features:
        feat_clean = facts.readme.features[0].rstrip(".")
        say1 = f"In summary, {title} provides {feat_clean}."
        summary_phrase = f"{title} provides {feat_clean}"
        sp, ep = find_exact_line_range(facts.readme.raw_lines, feat_clean)
        span1 = SourceSpan(file=readme_file, start_line=sp if sp > 0 else 1, end_line=ep if ep > 0 else 1, text=feat_clean)
    elif facts.ranked_top_modules:
        top_mod = facts.ranked_top_modules[0]
        mods_str = ", ".join(facts.ranked_top_modules[:3])
        say1 = f"In summary, {title} organizes logic across {mods_str}."
        summary_phrase = f"Modules: {mods_str}"
        m_doc = next((m for m in facts.module_docstrings if m.file == top_mod), None)
        sym = next((s for s in facts.top_symbols if s.file == top_mod), None)
        edge = next((e for e in facts.import_graph if e.source == top_mod and e.raw_line), None)
        if m_doc:
            span1 = m_doc.span
        elif sym:
            span1 = SourceSpan(file=top_mod, start_line=sym.start_line, end_line=sym.end_line, text=sym.def_line or sym.name)
        elif edge:
            span1 = SourceSpan(file=top_mod, start_line=edge.line_number, end_line=edge.line_number, text=edge.raw_line)
        else:
            sp1, ep1 = find_exact_line_range(facts.readme.raw_lines, title)
            span1 = SourceSpan(file=readme_file, start_line=sp1 if sp1 > 0 else 1, end_line=ep1 if ep1 > 0 else 1, text=title)
    else:
        say1 = f"This concludes the overview of {title}."
        summary_phrase = title
        sp1, ep1 = find_exact_line_range(facts.readme.raw_lines, title)
        span1 = SourceSpan(file=readme_file, start_line=sp1 if sp1 > 0 else 1, end_line=ep1 if ep1 > 0 else 1, text=title)

    beats.append(Beat(
        say=tts_normalize_speech(say1),
        caption=fit_clause(summary_phrase, max_chars=60),
        focus="recap",
        sources=[span1],
        start_seconds=0.25,
        end_seconds=4.5,
    ))

    # Beat 2: Entry point to explore (T8: first-party only)
    entry_f = select_recap_entry_file(facts)
    if entry_f:
        say2 = f"To dive in, open {entry_f}."
        caption2 = f"Next step: open {entry_f}"
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
                    sp2, ep2 = find_exact_line_range(facts.readme.raw_lines, entry_f)
                    txt2 = entry_f if any(entry_f in l for l in facts.readme.raw_lines) else (facts.readme.title or facts.repo_name)
                    span2 = SourceSpan(file=readme_file, start_line=sp2 if sp2 > 0 else 1, end_line=ep2 if ep2 > 0 else 1, text=txt2)

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
