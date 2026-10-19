"""
Scene 4: Key Code & Implementation narration (T4, T5, T6, R4).
Selects non-trivial public functions, prevents duplicate verbs ('load load'), and filters stdlib predicates.
"""
from __future__ import annotations

import re
from ..analyze import RepoFacts, TopSymbol, is_auxiliary_or_test_path
from ..schema import Beat, Scene, SourceSpan
from .compress import clean_caption_text
from .speech import humanize_identifier, tts_normalize_speech
from .verbs import convert_docstring_to_verb_phrase

DISALLOWED_CALL_NAMES = {
    "print", "len", "str", "int", "float", "list", "dict", "set", "tuple", "bool",
    "keys", "values", "items", "append", "extend", "get", "split", "strip", "join",
    "replace", "lower", "upper", "startswith", "endswith", "range", "enumerate",
    "is_available", "expanduser", "exists", "isdir", "isfile", "open", "read", "write",
}


def filter_meaningful_calls(calls: list[str]) -> list[str]:
    """T5: Filter meaningful, project-internal or domain calls, stripping stdlib helpers and predicates."""
    res: list[str] = []
    for c in calls:
        if c.startswith("_"):
            continue
        c_clean = c.split(".")[-1].lower()
        if c_clean in DISALLOWED_CALL_NAMES:
            continue
        if c_clean.startswith("is_") or c_clean.startswith("has_"):
            continue
        res.append(c)
        if len(res) >= 3:  # T5: cap at 3
            break
    return res


def build_code_scene(facts: RepoFacts, readme_file: str) -> Scene | None:
    """R4, T4, T5, T6: Selects key code symbol and produces grounded narration."""
    from ..visuals import select_primary_code_symbol
    sym = select_primary_code_symbol(facts)
    if not sym:
        return None

    beats: list[Beat] = []
    calls_clean = filter_meaningful_calls(sym.calls)

    # Beat 1: Purpose & Declaration (T4: strip duplicate function name/verb)
    if sym.docstring:
        doc_phrase = convert_docstring_to_verb_phrase(sym.docstring, func_name=sym.name)
        say1 = f"In {sym.file}, {sym.name} {doc_phrase}."
        caption1 = f"{sym.name}: {clean_caption_text(doc_phrase, 6)}"
        span1 = sym.docstring_span or SourceSpan(
            file=sym.file,
            start_line=sym.start_line,
            end_line=min(sym.start_line + 4, sym.end_line),
            text=sym.docstring,
        )
    elif calls_clean:
        humanized_calls = [humanize_identifier(c) for c in calls_clean]
        calls_str = " and ".join(humanized_calls)
        say1 = f"In {sym.file}, {sym.name} calls {calls_str}."
        caption1 = f"{sym.name}: calls {calls_str}"
        span1 = SourceSpan(
            file=sym.file,
            start_line=sym.start_line,
            end_line=min(sym.start_line + 4, sym.end_line),
            text=sym.def_line or sym.name,
        )
    else:
        say1 = f"In {sym.file}, {sym.name} coordinates module execution."
        caption1 = f"{sym.name} in {sym.file}"
        span1 = SourceSpan(
            file=sym.file,
            start_line=sym.start_line,
            end_line=min(sym.start_line + 4, sym.end_line),
            text=sym.def_line or sym.name,
        )

    beats.append(Beat(
        say=tts_normalize_speech(say1),
        caption=caption1,
        focus=sym.name,
        sources=[span1],
        start_seconds=0.25,
        end_seconds=4.8,
    ))

    # Beat 2: Execution action (T5: humanize identifiers, cap at 3, never 'invokes is available')
    if calls_clean:
        humanized_calls = [humanize_identifier(c) for c in calls_clean]
        calls_str = " and ".join(humanized_calls)
        say2 = f"Inside {sym.name}, it invokes {calls_str}."
        caption2 = f"Calls: {', '.join(calls_clean)}"
        call_line = next((l.strip() for l in sym.code_excerpt.splitlines() if any(c in l for c in calls_clean)), sym.def_line)
        span2 = SourceSpan(
            file=sym.file,
            start_line=sym.start_line,
            end_line=sym.end_line,
            text=call_line or sym.name,
        )
    else:
        say2 = f"In {sym.file}, {sym.name} returns the processed result."
        caption2 = f"{sym.name} execution"
        span2 = SourceSpan(file=sym.file, start_line=sym.start_line, end_line=sym.end_line, text=sym.def_line or sym.name)

    beats.append(Beat(
        say=tts_normalize_speech(say2),
        caption=caption2,
        focus="execution",
        sources=[span2],
        start_seconds=0.25,
        end_seconds=4.8,
    ))

    narration = " ".join(b.say for b in beats)
    return Scene(
        id="code",
        kind="code",
        title="Implementation",
        narration=narration,
        beats=beats,
        duration_seconds=round(len(beats) * 4.8, 2),
    )
