"""
Scene 4: Key Code & Implementation narration (Phase 4, T4, T5, T6, R4).
Selects non-trivial public functions and generates 2-3 explanatory beats grounded in AST facts.
Highlight focus is constrained to <= 5 lines per beat.
"""
from __future__ import annotations

import re
from ..analyze import RepoFacts, TopSymbol, is_auxiliary_or_test_path
from ..schema import Beat, Scene, SourceSpan
from .compress import clean_caption_text, fit_clause
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
        if len(res) >= 3:
            break
    return res


def build_code_scene(facts: RepoFacts, readme_file: str) -> Scene | None:
    """R4, T4, T5, T6, Phase 4: Produces grounded 2-3 beat code narration from AST facts."""
    from ..visuals import select_primary_code_symbol
    sym = select_primary_code_symbol(facts)
    if not sym:
        return None

    beats: list[Beat] = []
    calls_clean = filter_meaningful_calls(sym.calls)

    sig_start = sym.start_line
    sig_focus_end = min(sym.start_line + 1, sym.end_line) if (sym.end_line - sym.start_line) >= 4 else sym.start_line

    # Beat 1: Purpose & Declaration (T4: verb phrase, signature focus)
    if sym.docstring:
        doc_phrase = convert_docstring_to_verb_phrase(sym.docstring, func_name=sym.name)
        say1 = f"In {sym.file}, {sym.name} {doc_phrase}."
        caption1 = fit_clause(f"{sym.name}: {doc_phrase}", max_chars=55)
        span1 = sym.docstring_span or SourceSpan(
            file=sym.file,
            start_line=sym.start_line,
            end_line=sym.end_line,
            text=sym.docstring,
        )
    elif calls_clean:
        humanized_calls = [humanize_identifier(c) for c in calls_clean]
        calls_str = " and ".join(humanized_calls)
        say1 = f"In {sym.file}, {sym.name} calls {calls_str}."
        caption1 = fit_clause(f"{sym.name}: calls {calls_str}", max_chars=55)
        span1 = SourceSpan(
            file=sym.file,
            start_line=sym.start_line,
            end_line=sym.end_line,
            text=sym.def_line or sym.name,
        )
    else:
        say1 = f"In {sym.file}, {sym.name} coordinates module execution."
        caption1 = f"{sym.name} in {sym.file}"
        span1 = SourceSpan(
            file=sym.file,
            start_line=sym.start_line,
            end_line=sym.end_line,
            text=sym.def_line or sym.name,
        )

    beats.append(Beat(
        say=tts_normalize_speech(say1),
        caption=caption1,
        focus=f"{sig_start}-{sig_focus_end}",
        sources=[span1],
        start_seconds=0.25,
        end_seconds=4.5,
    ))

    # Beat 2: What it takes / does (parameters and calls)
    body_focus = min(sym.start_line + 2, sym.end_line) if sym.end_line > sym.start_line else sym.start_line
    body_focus_end = min(body_focus + 1, sym.end_line) if (sym.end_line - sym.start_line) >= 5 else body_focus

    if sym.parameters and calls_clean:
        params_str = " and ".join(sym.parameters[:2])
        calls_str = " and ".join([humanize_identifier(c) for c in calls_clean[:2]])
        say2 = f"It takes {params_str} and invokes {calls_str}."
        caption2 = f"Invokes {calls_str}"
    elif sym.parameters:
        params_str = " and ".join(sym.parameters[:2])
        say2 = f"It takes {params_str} to configure execution."
        caption2 = f"Takes {params_str}"
    elif calls_clean:
        humanized_calls = [humanize_identifier(c) for c in calls_clean]
        calls_str = " and ".join(humanized_calls)
        say2 = f"Inside {sym.name}, it invokes {calls_str}."
        caption2 = f"Calls {calls_str}"
    else:
        say2 = f"Inside {sym.name}, it performs the core computation."
        caption2 = f"{sym.name} execution"

    call_line = next((l.strip() for l in sym.code_excerpt.splitlines() if any(c in l for c in calls_clean)), "")
    span2 = SourceSpan(
        file=sym.file,
        start_line=sym.start_line,
        end_line=sym.end_line,
        text=call_line or sym.def_line or sym.name,
    )

    beats.append(Beat(
        say=tts_normalize_speech(say2),
        caption=fit_clause(caption2, max_chars=50),
        focus=f"{body_focus}-{body_focus_end}",
        sources=[span2],
        start_seconds=0.25,
        end_seconds=4.5,
    ))

    # Beat 3: What it returns (if function has return statements)
    if sym.has_return:
        ret_line = sym.end_line
        say3 = f"It returns the processed output."
        caption3 = "Returns result"
        span3 = SourceSpan(
            file=sym.file,
            start_line=sym.start_line,
            end_line=sym.end_line,
            text=sym.def_line or sym.name,
        )
        beats.append(Beat(
            say=tts_normalize_speech(say3),
            caption=caption3,
            focus=f"{ret_line}-{ret_line}",
            sources=[span3],
            start_seconds=0.25,
            end_seconds=4.0,
        ))

    narration = " ".join(b.say for b in beats)
    return Scene(
        id="code",
        kind="code",
        title="Implementation",
        narration=narration,
        beats=beats,
        duration_seconds=round(len(beats) * 4.5, 2),
    )
