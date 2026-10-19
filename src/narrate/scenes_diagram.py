"""
Scene 3: Architecture Diagram narration (R5, T8).
Excludes tests, examples, docs, and setup files from architecture nodes.
"""
from __future__ import annotations

from ..analyze import RepoFacts, is_auxiliary_or_test_path
from ..schema import Beat, Scene, SourceSpan
from .compress import clean_caption_text
from .speech import tts_normalize_speech
from .verbs import convert_docstring_to_verb_phrase


def build_diagram_scene(facts: RepoFacts, readme_file: str) -> Scene | None:
    """R5: Architecture selection excluding tests/examples, connecting core modules with real roles."""
    core_mods = [m for m in facts.ranked_top_modules if not is_auxiliary_or_test_path(m)]
    if not core_mods:
        return None

    beats: list[Beat] = []
    mod_doc_map = {m.file: m.docstring for m in facts.module_docstrings}

    mod1 = core_mods[0]
    m_doc1 = mod_doc_map.get(mod1, "")
    sym1 = next((s for s in facts.top_symbols if s.file == mod1), None)
    edge1 = next((e for e in facts.import_graph if e.source == mod1 and e.raw_line), None)

    if m_doc1:
        role1 = convert_docstring_to_verb_phrase(m_doc1)
        say1 = f"{mod1} {role1}."
        caption1 = f"{mod1}: {clean_caption_text(role1, 6)}"
        m_doc_obj = next((m for m in facts.module_docstrings if m.file == mod1), None)
        span1 = m_doc_obj.span if m_doc_obj else SourceSpan(file=mod1, start_line=1, end_line=1, text=m_doc1)
    elif sym1:
        say1 = f"{mod1} defines {sym1.name}."
        caption1 = f"{mod1}: defines {sym1.name}"
        span1 = SourceSpan(file=mod1, start_line=sym1.start_line, end_line=sym1.end_line, text=sym1.def_line or sym1.name)
    elif edge1:
        say1 = f"{mod1} imports from {edge1.target}."
        caption1 = f"{mod1}: imports {edge1.target}"
        span1 = SourceSpan(file=mod1, start_line=edge1.line_number, end_line=edge1.line_number, text=edge1.raw_line)
    else:
        say1 = f"{mod1} contains core package implementation."
        caption1 = f"{mod1}: core package"
        span1 = SourceSpan(file=mod1, start_line=1, end_line=1, text=mod1)

    beats.append(Beat(
        say=tts_normalize_speech(say1),
        caption=caption1,
        focus=mod1,
        sources=[span1],
        start_seconds=0.25,
        end_seconds=4.8,
    ))

    if len(core_mods) >= 2:
        mod2 = core_mods[1]
        m_doc2 = mod_doc_map.get(mod2, "")
        sym2 = next((s for s in facts.top_symbols if s.file == mod2), None)
        edge2_out = next((e for e in facts.import_graph if e.source == mod2 and e.raw_line), None)
        edge2_in = next((e for e in facts.import_graph if e.target == mod2 and e.raw_line), None) if not edge2_out else None

        if m_doc2:
            role2 = convert_docstring_to_verb_phrase(m_doc2)
            say2 = f"It connects to {mod2}, which {role2}."
            caption2 = f"{mod2}: {clean_caption_text(role2, 6)}"
            m_doc_obj2 = next((m for m in facts.module_docstrings if m.file == mod2), None)
            span2 = m_doc_obj2.span if m_doc_obj2 else SourceSpan(file=mod2, start_line=1, end_line=1, text=m_doc2)
        elif sym2:
            say2 = f"It connects to {mod2}, which defines {sym2.name}."
            caption2 = f"{mod2}: defines {sym2.name}"
            span2 = SourceSpan(file=mod2, start_line=sym2.start_line, end_line=sym2.end_line, text=sym2.def_line or sym2.name)
        elif edge2_out:
            say2 = f"It connects to {mod2}, which imports {edge2_out.target}."
            caption2 = f"{mod2}: imports {edge2_out.target}"
            span2 = SourceSpan(file=mod2, start_line=edge2_out.line_number, end_line=edge2_out.line_number, text=edge2_out.raw_line)
        elif edge2_in:
            say2 = f"It connects to {mod2}, imported by {edge2_in.source}."
            caption2 = f"{mod2}: imported"
            span2 = SourceSpan(file=edge2_in.source, start_line=edge2_in.line_number, end_line=edge2_in.line_number, text=edge2_in.raw_line)
        else:
            say2 = f"It connects to {mod2}."
            caption2 = f"{mod2}: connection"
            span2 = SourceSpan(file=mod2, start_line=1, end_line=1, text=mod2)

        beats.append(Beat(
            say=tts_normalize_speech(say2),
            caption=caption2,
            focus=mod2,
            sources=[span2],
            start_seconds=0.25,
            end_seconds=4.8,
        ))

    narration = " ".join(b.say for b in beats)
    return Scene(
        id="diagram",
        kind="diagram",
        title="Architecture",
        narration=narration,
        beats=beats,
        duration_seconds=round(len(beats) * 4.8, 2),
    )
