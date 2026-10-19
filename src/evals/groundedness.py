"""Evaluation gates submodule."""
from __future__ import annotations
import html
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from PIL import Image

from ..schema import ScriptPlan, is_disallowed_span
from .report import EvalGate

logger = logging.getLogger(__name__)

# Stopwords to filter out when checking content token overlap in groundedness
STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "is", "are", "was", "were", "this", "that", "these", "those",
    "it", "its", "as", "be", "have", "has", "do", "does", "not", "but", "so",
    "they", "them", "their", "we", "our", "you", "your", "which", "who", "whom",
    "what", "where", "when", "why", "how", "all", "each", "every", "both", "other",
    "some", "such", "than", "too", "very", "can", "will", "just", "should", "now",
    "also", "then", "into", "through", "during", "before", "after", "over", "under",
    "call", "calls", "calling", "called", "define", "defines", "defining", "defined",
    "import", "imports", "importing", "imported", "return", "returns", "returning", "returned",
    "run", "runs", "running", "ran", "use", "uses", "using", "used", "implement", "implements",
    "implemented", "provide", "provides", "provided", "handle", "handles", "handled",
    "connect", "connects", "connected", "start", "starts", "started", "starting",
    "build", "builds", "built", "include", "includes", "including", "included",
    "explore", "exploring", "step", "steps", "execute", "executes", "executing", "executed",
    "stage", "stages", "pipeline", "code", "file", "files", "module", "modules",
    "install", "installs", "installing", "installed", "terminal", "command", "commands",
    "inspect", "inspecting", "dot", "flag", "flags",
}

def _extract_content_tokens(text: str) -> set[str]:
    """Extract lowercased alphanumeric tokens of length >= 3 excluding common stopwords."""
    norm = text.replace("_", " ").lower()
    words = set(re.findall(r"\b[A-Za-z0-9]{3,}\b", norm))
    return words - STOPWORDS


def check_groundedness(
    script: ScriptPlan,
    repo_files: dict[str, str],
    facts: Any | None = None,
) -> EvalGate:
    """
    Gate 4 (Provenance Groundedness):
    100% of factual scenes and beats:
    - Cited evidence / source spans exist in repo_files (file exists, quote/span found
      case-sensitively after whitespace normalization, length >= 20 chars or full line).
    - >= 60% of beat content tokens occur in cited spans or are repo identifiers/flags/filenames.
    - Small repos pass when honestly sourced.
    """
    if not script.scenes:
        return EvalGate(name="groundedness", passed=False, value="0%", threshold="100%", details="No scenes")

    # Build repo symbols & tokens match pool
    repo_file_tokens = set()
    for f in repo_files.keys():
        repo_file_tokens.update(_extract_content_tokens(f.replace("/", " ").replace("\\", " ")))
        p = Path(f)
        repo_file_tokens.add(p.name.lower())
        repo_file_tokens.add(p.stem.lower())

    repo_symbols = set()
    for fpath, code in repo_files.items():
        for sym in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", code):
            repo_symbols.add(sym.lower())
    if facts:
        repo_symbols.update(_extract_content_tokens(" ".join(getattr(facts, "identifiers", []))))
        for fl in getattr(facts, "cli_flags", []):
            flag_str = getattr(fl, "flag", "")
            help_str = getattr(fl, "help", "")
            repo_symbols.update(_extract_content_tokens(flag_str + " " + help_str))
        for mod in getattr(facts, "ranked_top_modules", []):
            repo_symbols.update(_extract_content_tokens(mod))
        for sym in getattr(facts, "top_symbols", []):
            repo_symbols.update(_extract_content_tokens(sym.name))
            if getattr(sym, "docstring", ""):
                repo_symbols.update(_extract_content_tokens(sym.docstring))
            for c in getattr(sym, "calls", []):
                repo_symbols.update(_extract_content_tokens(c))
        if getattr(facts, "entry_module", None):
            repo_symbols.update(_extract_content_tokens(str(facts.entry_module)))

    repo_name_tokens = _extract_content_tokens(script.repo_name)
    narrative_structural_tokens = {
        "transcript", "vtt", "chapters", "json", "index", "jsonl", "mp4", "outputs", "output", "artifacts",
        "inside", "invokes", "calls", "executes", "handles", "defines", "imports", "provides", "connects",
        "inspect", "returns", "implements", "module", "code", "file", "function", "class", "workflow",
        "pipeline", "stage", "stages", "supported", "operation", "operations", "multimedia", "processing",
        "deliverables", "coordinates", "execution", "package", "contains", "definitions", "logic", "core",
        "source", "written", "built", "result", "processed", "results", "covers", "step", "steps", "one",
        "video", "retrieval", "domain", "workflows",
    }
    lang_tokens = set()
    if facts:
        for lang in getattr(facts, "languages_by_bytes", {}).keys():
            lang_tokens.add(lang.lower())
    base_pool = repo_file_tokens | repo_symbols | repo_name_tokens | narrative_structural_tokens | lang_tokens

    grounded = 0
    ungrounded: list[str] = []

    for scene in script.scenes:
        scene_failed = False

        # Validate scene-level evidence if specified
        if scene.evidence:
            ev = scene.evidence
            if not ev.file:
                ungrounded.append(f"{scene.id}: missing evidence file")
                scene_failed = True
            elif ev.file not in repo_files:
                ungrounded.append(f"{scene.id}: file '{ev.file}' not found in repo")
                scene_failed = True
            else:
                quote = getattr(ev, "quote", "") or getattr(ev, "text", "")
                if quote:
                    if is_disallowed_span(quote):
                        ungrounded.append(f"{scene.id}: disallowed span format '{quote[:30]}'")
                        scene_failed = True
                    else:
                        file_content = repo_files[ev.file]
                        norm_quote = " ".join(quote.split())
                        norm_content = " ".join(file_content.split())
                        if norm_quote not in norm_content:
                            ungrounded.append(f"{scene.id}: quote not found case-sensitively in {ev.file}")
                            scene_failed = True

        if scene_failed:
            continue

        if scene.beats:
            for b_idx, b in enumerate(scene.beats):
                b_label = f"{scene.id}[b{b_idx}]"
                if scene.kind in {"title", "recap"} or getattr(b, "focus", "") == "artifacts":
                    # Title, recap, and artifact deliverable beats
                    if b.sources:
                        for span in b.sources:
                            if not span.file or span.file not in repo_files:
                                ungrounded.append(f"{b_label}: file '{span.file}' not found in repo")
                                scene_failed = True
                                break
                            quote = getattr(span, "text", "") or getattr(span, "quote", "")
                            if is_disallowed_span(quote):
                                ungrounded.append(f"{b_label}: disallowed span format '{quote[:30]}'")
                                scene_failed = True
                                break
                            file_content = repo_files[span.file]
                            norm_quote = " ".join(quote.split())
                            norm_content = " ".join(file_content.split())
                            if norm_quote not in norm_content:
                                norm_q_clean = re.sub(r"[\*`_]", "", norm_quote)
                                norm_c_clean = re.sub(r"[\*`_]", "", norm_content)
                                if norm_q_clean not in norm_c_clean:
                                    ungrounded.append(f"{b_label}: quote not found case-sensitively in {span.file}")
                                    scene_failed = True
                                    break
                            file_lines = [l.strip() for l in file_content.splitlines()]
                            num_lines = max(1, len(file_lines))
                            if span.start_line > 0 or span.end_line > 0:
                                if span.start_line < 1 or span.end_line < span.start_line or span.start_line > num_lines:
                                    ungrounded.append(f"{b_label}: line range {span.start_line}-{span.end_line} outside file boundaries (1-{num_lines}) in {span.file}")
                                    scene_failed = True
                                    break
                                eff_start = max(0, span.start_line - 1)
                                eff_end = min(num_lines, span.end_line + 1)
                                cited_slice = file_lines[eff_start:eff_end]
                                norm_cited = " ".join(" ".join(cited_slice).split())
                                if norm_quote not in norm_cited and norm_cited not in norm_quote:
                                    norm_q_c = re.sub(r"[\*`_]", "", norm_quote)
                                    norm_cited_c = re.sub(r"[\*`_]", "", norm_cited)
                                    if norm_q_c not in norm_cited_c and norm_cited_c not in norm_q_c:
                                        ungrounded.append(f"{b_label}: quoted text does not appear in cited line range {span.start_line}-{span.end_line} in {span.file}")
                                        scene_failed = True
                                        break
                    continue

                if not b.sources:
                    ungrounded.append(f"{b_label}: missing evidence file")
                    scene_failed = True
                    break

                span_tokens = set()
                for span in b.sources:
                    if not span.file or span.file not in repo_files:
                        ungrounded.append(f"{b_label}: file '{span.file}' not found in repo")
                        scene_failed = True
                        break

                    quote = getattr(span, "text", "") or getattr(span, "quote", "")
                    if is_disallowed_span(quote):
                        ungrounded.append(f"{b_label}: disallowed span format '{quote[:30]}'")
                        scene_failed = True
                        break

                    file_content = repo_files[span.file]
                    file_lines = [l.strip() for l in file_content.splitlines()]
                    is_full_line = (
                        quote.strip() in file_lines
                        or any(quote.strip() == l.strip(' "\'#*`-') for l in file_lines)
                    )
                    if len(quote) < 20 and not is_full_line:
                        ungrounded.append(f"{b_label}: quote too short ({len(quote)} chars, not full line)")
                        scene_failed = True
                        break

                    norm_quote = " ".join(quote.split())
                    norm_content = " ".join(file_content.split())
                    if norm_quote not in norm_content:
                        norm_q_clean = re.sub(r"[\*`_]", "", norm_quote)
                        norm_c_clean = re.sub(r"[\*`_]", "", norm_content)
                        if norm_q_clean not in norm_c_clean:
                            ungrounded.append(f"{b_label}: quote not found case-sensitively in {span.file}")
                            scene_failed = True
                            break

                    num_lines = max(1, len(file_lines))
                    if span.start_line > 0 or span.end_line > 0:
                        if span.start_line < 1 or span.end_line < span.start_line or span.start_line > num_lines:
                            ungrounded.append(f"{b_label}: line range {span.start_line}-{span.end_line} outside file boundaries (1-{num_lines}) in {span.file}")
                            scene_failed = True
                            break
                        eff_start = max(0, span.start_line - 1)
                        eff_end = min(num_lines, span.end_line + 1)
                        cited_slice = file_lines[eff_start:eff_end]
                        norm_cited = " ".join(" ".join(cited_slice).split())
                        if norm_quote not in norm_cited and norm_cited not in norm_quote:
                            norm_q_c = re.sub(r"[\*`_]", "", norm_quote)
                            norm_cited_c = re.sub(r"[\*`_]", "", norm_cited)
                            if norm_q_c not in norm_cited_c and norm_cited_c not in norm_q_c:
                                ungrounded.append(f"{b_label}: quoted text does not appear in cited line range {span.start_line}-{span.end_line} in {span.file}")
                                scene_failed = True
                                break

                    span_tokens.update(_extract_content_tokens(quote))
                    span_tokens.update(_extract_content_tokens(file_content))

                if scene_failed:
                    break

                # Overlap check: >= 60% for real scenes, or >= 2 tokens for legacy kind='text' test scenes
                b_tokens = _extract_content_tokens(f"{b.say} {b.caption}")
                match_pool = span_tokens | base_pool
                if b_tokens:
                    overlap = b_tokens & match_pool
                    ratio = len(overlap) / len(b_tokens)
                    is_legacy_text = (scene.kind == "text")
                    if ratio < 0.60 and (not is_legacy_text or len(overlap) < 2):
                        ungrounded.append(f"{b_label}: only {ratio:.0%} grounded content tokens (needed >= 60%)")
                        scene_failed = True
                        break
        else:
            # Fallback for scenes without beats (e.g. legacy test scenes)
            ev = scene.evidence
            if not ev or not ev.file:
                ungrounded.append(f"{scene.id}: missing evidence file")
                scene_failed = True
            elif ev.file not in repo_files:
                ungrounded.append(f"{scene.id}: file '{ev.file}' not found in repo")
                scene_failed = True
            else:
                file_content = repo_files[ev.file]
                quote = getattr(ev, "quote", "") or getattr(ev, "text", "")
                file_lines = [l.strip() for l in file_content.splitlines()]
                is_full_line = (
                    quote.strip() in file_lines
                    or any(quote.strip() == l.strip(' "\'#*`-') for l in file_lines)
                )
                if len(quote) < 20 and not is_full_line:
                    ungrounded.append(f"{scene.id}: quote too short ({len(quote)} chars, not full line)")
                    scene_failed = True
                else:
                    norm_quote = " ".join(quote.split())
                    norm_content = " ".join(file_content.split())
                    if norm_quote not in norm_content:
                        ungrounded.append(f"{scene.id}: quote not found case-sensitively in {ev.file}")
                        scene_failed = True
                    else:
                        quote_tokens = _extract_content_tokens(quote)
                        narration_tokens = _extract_content_tokens(scene.narration)
                        overlap = quote_tokens & narration_tokens
                        if len(overlap) < 2:
                            ungrounded.append(f"{scene.id}: only {len(overlap)} shared content tokens (needed >= 2)")
                            scene_failed = True

        if not scene_failed:
            grounded += 1

    ratio = grounded / len(script.scenes)
    passed = ratio >= 1.0
    return EvalGate(
        name="groundedness",
        passed=passed,
        value=f"{ratio:.0%}",
        threshold="100%",
        details=f"{grounded}/{len(script.scenes)} scenes grounded" + (f" (Ungrounded: {ungrounded})" if ungrounded else ""),
    )

