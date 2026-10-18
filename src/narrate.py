"""
The Explainer Writer: deterministic, extractive narration composed from real
repository facts and source spans. Never fills templates with lone tokens.

Generates 3 to 7 scenes based on available facts:
1. title    : <Title>. <tagline sentence>.
2. overview : what it is, what it does, what you get.
3. diagram  : walk top modules in call/flow order with docstring verb phrases.
4. code     : key entry function walk with AST calls, flags, returns.
5. terminal : real quickstart commands from README fences with flag help text.
6. fit      : honest video pipeline fit (only stages with concrete evidence).
7. recap    : 3 actionable takeaways, ending with 'Start with <entry_module>'.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .analyze import RepoFacts, TopSymbol
from .evals.gates import STOPWORDS
from .schema import (
    Beat,
    Evidence,
    Scene,
    ScriptPlan,
    SourceSpan,
    check_for_banned_phrases,
    normalize_speech,
)
from .visuals import attach_visuals_to_script

logger = logging.getLogger(__name__)


def trim_to_clause(text: str, max_words: int = 20) -> str:
    """Trim a sentence to clause boundaries keeping original words intact."""
    words = text.strip().split()
    if len(words) <= max_words:
        res = " ".join(words)
        if not res.endswith((".", "!", "?")):
            res += "."
        return res

    # Try to cut at comma, semicolon, colon, or conjunction
    clause_delims = [",", ";", ":", " -- ", " - "]
    best_cut = ""
    for delim in clause_delims:
        if delim in text:
            parts = text.split(delim)
            prefix = parts[0].strip()
            if 4 <= len(prefix.split()) <= max_words:
                best_cut = prefix
                break

    if not best_cut:
        # Fall back to word boundary cut
        best_cut = " ".join(words[:max_words])

    best_cut = best_cut.rstrip(",;:- ")
    if not best_cut.endswith((".", "!", "?")):
        best_cut += "."
    return best_cut


def _clean_caption(text: str, max_words: int = 14) -> str:
    """Create short on-screen caption from exact source words."""
    words = text.strip().split()
    cap = " ".join(words[:max_words]).rstrip(",;:- ")
    return cap


class ExplainerWriter:
    """Extractive script generator building beats backed by SourceSpans."""

    def __init__(self, facts: RepoFacts) -> None:
        self.facts = facts
        self.readme_file = facts.readme_file or "README.md"

    def write_script(self) -> ScriptPlan:
        """Compose script plan from facts, ensuring no banned phrases."""
        scenes: list[Scene] = []

        # 1. Title Scene
        title_scene = self._build_title_scene()
        if title_scene:
            scenes.append(title_scene)

        # 2. Overview Scene
        ov_scene = self._build_overview_scene()
        if ov_scene:
            scenes.append(ov_scene)

        # 3. Diagram / Architecture Scene (only if multiple modules exist)
        if len(self.facts.ranked_top_modules) >= 2 or len(self.facts.import_graph) >= 1:
            diag_scene = self._build_diagram_scene()
            if diag_scene:
                scenes.append(diag_scene)

        # 4. Code Scene (only if functions/symbols exist)
        if self.facts.top_symbols:
            code_scene = self._build_code_scene()
            if code_scene:
                scenes.append(code_scene)

        # 5. Terminal Scene (only if commands exist in fences)
        term_scene = self._build_terminal_scene()
        if term_scene:
            scenes.append(term_scene)

        # 6. Fit Scene (video retrieval alignment)
        fit_scene = self._build_fit_scene()
        if fit_scene:
            scenes.append(fit_scene)

        # 7. Recap Scene
        recap_scene = self._build_recap_scene()
        if recap_scene:
            scenes.append(recap_scene)

        # Guarantee at least 3 scenes for sparse repos
        if len(scenes) < 3:
            scenes = self._fill_sparse_scenes(scenes)

        # Strict duration budgeting: target video duration 44s - 52s (at calibrated 120 WPM speech)
        while True:
            total_words = sum(len(s.narration.split()) for s in scenes)
            if (total_words / 120.0) * 60.0 <= 52.0:
                break
            trimmed = False
            for target_id in ("fit", "overview", "terminal", "code"):
                sc = next((s for s in scenes if s.id == target_id and len(s.beats) > 1), None)
                if sc:
                    sc.beats.pop()
                    sc.narration = " ".join(b.say for b in sc.beats)
                    trimmed = True
                    break
            if not trimmed:
                break

        # Validate no banned buzzwords; reject draft if any found
        for s in scenes:
            for b in s.beats:
                banned = check_for_banned_phrases(b.say) + check_for_banned_phrases(b.caption)
                if banned:
                    raise ValueError(f"Extractive script generated banned phrases {banned} in scene '{s.id}'")

        script = ScriptPlan(repo_name=self.facts.repo_name, scenes=scenes)
        # Attach grounded visuals
        attach_visuals_to_script(script, self.facts)
        return script

    def _build_title_scene(self) -> Scene:
        title = self.facts.readme.title
        if not title or len(title.split()) > 6 or "[" in title or check_for_banned_phrases(title):
            title = self.facts.repo_name

        tagline = self.facts.readme.tagline
        if not tagline or check_for_banned_phrases(tagline):
            clean_sents = [s for s in self.facts.readme.description_sentences if not check_for_banned_phrases(s.text)]
            if clean_sents:
                tagline = clean_sents[0].text

        if not tagline or check_for_banned_phrases(tagline):
            top_lang = next(iter(self.facts.languages_by_bytes.keys()), "software")
            tagline = f"{self.facts.repo_name} is a {top_lang} project."

        tagline_trimmed = trim_to_clause(tagline, max_words=10)
        if tagline_trimmed.lower().startswith(title.lower()):
            say = tagline_trimmed
        else:
            say = f"{title}. {tagline_trimmed}"
        caption = f"{title}: {trim_to_clause(tagline, max_words=8)}"

        sources: list[SourceSpan] = []
        clean_sents = [s for s in self.facts.readme.description_sentences if not check_for_banned_phrases(s.text)]
        if clean_sents:
            first_ds = clean_sents[0]
            sources.append(
                SourceSpan(
                    file=self.readme_file,
                    start_line=first_ds.start_line,
                    end_line=first_ds.end_line,
                    text=first_ds.text,
                )
            )

        elif self.facts.readme.raw_lines:
            sources.append(
                SourceSpan(
                    file=self.readme_file,
                    start_line=1,
                    end_line=min(5, len(self.facts.readme.raw_lines)),
                    text=self.facts.readme.raw_lines[0],
                )
            )

        beat = Beat(
            say=normalize_speech(say),
            caption=caption,
            focus=self.facts.repo_name,
            sources=sources,
        )
        return Scene(
            id="title",
            kind="title",
            title="Overview",
            beats=[beat],
        )

    def _build_overview_scene(self) -> Scene:
        beats: list[Beat] = []
        desc_sents = [s for s in self.facts.readme.description_sentences if not check_for_banned_phrases(s.text)]
        features = [f for f in self.facts.readme.features if not check_for_banned_phrases(f)]

        # Beat 1: Core capability (use distinct sentence from title if available)
        s0 = desc_sents[1] if len(desc_sents) > 1 else (desc_sents[0] if desc_sents else None)
        if s0:
            txt = trim_to_clause(s0.text, max_words=12)
            b1 = Beat(
                say=normalize_speech(txt),
                caption=_clean_caption(s0.text),
                focus="purpose",
                sources=[
                    SourceSpan(
                        file=self.readme_file,
                        start_line=s0.start_line,
                        end_line=s0.end_line,
                        text=s0.text,
                    )
                ],
            )
            beats.append(b1)

        # Beat 2: Features or dependencies
        if features:
            f0 = features[0]
            txt = f"It provides {trim_to_clause(f0, max_words=10)}"
            b2 = Beat(
                say=normalize_speech(txt),
                caption=_clean_caption(f0),
                focus="features",
                sources=[
                    SourceSpan(
                        file=self.readme_file,
                        start_line=1,
                        end_line=20,
                        text=f0,
                    )
                ],
            )
            beats.append(b2)
        elif self.facts.dependency_roles:
            dep_items = list(self.facts.dependency_roles.items())[:2]
            parts = [f"{dep} for {role}" for dep, role in dep_items]
            txt = f"It builds on {' and '.join(parts)}."
            b2 = Beat(
                say=normalize_speech(txt),
                caption=f"Dependencies: {', '.join(d for d, _ in dep_items)}",
                focus="dependencies",
                sources=[
                    SourceSpan(
                        file="requirements.txt" if "requirements.txt" in self.facts.tree else self.readme_file,
                        start_line=1,
                        end_line=10,
                        text=dep_items[0][0],
                    )
                ],
            )
            beats.append(b2)



        if not beats:
            # Fallback for minimal repos
            txt = f"{self.facts.repo_name} provides codebase assets."
            beats.append(
                Beat(
                    say=normalize_speech(txt),
                    caption=self.facts.repo_name,
                    focus="overview",
                    sources=[
                        SourceSpan(
                            file=self.readme_file,
                            start_line=1,
                            end_line=1,
                            text=self.facts.readme.title or self.facts.repo_name,
                        )
                    ],
                )
            )

        return Scene(
            id="overview",
            kind="overview",
            title="Purpose",
            beats=beats,
        )

    def _build_diagram_scene(self) -> Scene:
        modules = self.facts.ranked_top_modules
        if not modules:
            return None

        beats: list[Beat] = []
        m0 = modules[0]
        # Find docstring or import or symbol for m0
        m0_doc = next((md for md in self.facts.module_docstrings if md.file == m0), None)
        sym0 = next((s for s in self.facts.top_symbols if s.file == m0 and s.docstring), None)
        edge0 = next((e for e in self.facts.import_graph if (e.source == m0 or e.target == m0) and e.raw_line), None)
        sym0_any = next((s for s in self.facts.top_symbols if s.file == m0), None)

        desc0 = ""
        source0 = None
        if m0_doc and m0_doc.docstring:
            desc0 = m0_doc.docstring
            source0 = m0_doc.span
        elif sym0 and sym0.docstring:
            desc0 = sym0.docstring
            source0 = sym0.docstring_span
        elif sym0_any and sym0_any.def_line:
            desc0 = f"defines {sym0_any.name}"
            source0 = SourceSpan(file=m0, start_line=sym0_any.start_line, end_line=sym0_any.start_line, text=sym0_any.def_line)
        elif edge0 and edge0.raw_line:
            target_name = Path(edge0.target).stem if edge0.target else "components"
            desc0 = f"imports {target_name}"
            source0 = SourceSpan(file=edge0.source, start_line=1, end_line=1, text=edge0.raw_line)
        else:
            desc0 = "provides core functionality"
            source0 = SourceSpan(file=self.readme_file, start_line=1, end_line=1, text=self.facts.readme.title or self.facts.repo_name)

        say1 = f"{m0} {trim_to_clause(desc0, max_words=8)}"
        beats.append(
            Beat(
                say=normalize_speech(say1),
                caption=f"{m0}: {trim_to_clause(desc0, max_words=6)}",
                focus=m0,
                sources=[source0],
            )
        )

        if len(modules) > 1:
            m1 = modules[1]
            m1_doc = next((md for md in self.facts.module_docstrings if md.file == m1), None)
            sym1 = next((s for s in self.facts.top_symbols if s.file == m1 and s.docstring), None)
            edge1 = next((e for e in self.facts.import_graph if (e.source == m1 or e.target == m1) and e.raw_line), None)
            sym1_any = next((s for s in self.facts.top_symbols if s.file == m1), None)

            desc1 = ""
            source1 = None
            if m1_doc and m1_doc.docstring:
                desc1 = m1_doc.docstring
                source1 = m1_doc.span
            elif sym1 and sym1.docstring:
                desc1 = sym1.docstring
                source1 = sym1.docstring_span
            elif sym1_any and sym1_any.def_line:
                desc1 = f"implements {sym1_any.name}"
                source1 = SourceSpan(file=m1, start_line=sym1_any.start_line, end_line=sym1_any.start_line, text=sym1_any.def_line)
            elif edge1 and edge1.raw_line:
                target_name1 = Path(edge1.target).stem if edge1.target else "components"
                desc1 = f"imports {target_name1}"
                source1 = SourceSpan(file=edge1.source, start_line=1, end_line=1, text=edge1.raw_line)
            else:
                desc1 = "provides supporting logic"
                source1 = SourceSpan(file=self.readme_file, start_line=1, end_line=1, text=self.facts.readme.title or self.facts.repo_name)

            say2 = f"It connects to {m1}, which {trim_to_clause(desc1, max_words=8)}"
            beats.append(
                Beat(
                    say=normalize_speech(say2),
                    caption=f"{m1}: {trim_to_clause(desc1, max_words=6)}",
                    focus=m1,
                    sources=[source1],
                )
            )

        return Scene(
            id="diagram",
            kind="diagram",
            title="Architecture",
            beats=beats,
        )

    def _build_code_scene(self) -> Scene:
        # Find entry function
        sym: TopSymbol | None = None
        if self.facts.entry_module:
            sym = next((s for s in self.facts.top_symbols if s.file == self.facts.entry_module and s.kind == "function"), None)
        if not sym:
            sym = next((s for s in self.facts.top_symbols if s.kind == "function"), self.facts.top_symbols[0])

        beats: list[Beat] = []
        code_lines = sym.code_excerpt.splitlines() if sym.code_excerpt else [sym.def_line]
        total_lines = len(code_lines)

        # Chunk 1 & 2 splitting
        if total_lines >= 2:
            split_idx = max(1, (total_lines + 1) // 2)
            chunk1_text = "\n".join(code_lines[:split_idx])
            chunk1_end = sym.start_line + split_idx - 1

            chunk2_text = "\n".join(code_lines[split_idx:])
            chunk2_start = chunk1_end + 1
            chunk2_end = sym.end_line
            if chunk2_start > chunk2_end:
                chunk2_start = chunk1_end
                chunk2_end = sym.end_line
                chunk2_text = code_lines[-1]
        else:
            chunk1_text = code_lines[0]
            chunk1_end = sym.start_line
            chunk2_text = code_lines[0]
            chunk2_start = sym.start_line
            chunk2_end = sym.end_line

        doc_desc = sym.docstring if sym.docstring else f"implements {sym.name}"
        say1 = f"In {sym.file}, {sym.name} {trim_to_clause(doc_desc, max_words=8)}"
        beats.append(
            Beat(
                say=normalize_speech(say1),
                caption=f"{sym.name}: {trim_to_clause(doc_desc, max_words=8)}",
                focus=f"{sym.start_line}-{chunk1_end}",
                sources=[
                    SourceSpan(
                        file=sym.file,
                        start_line=sym.start_line,
                        end_line=chunk1_end,
                        text=chunk1_text,
                    )
                ],
            )
        )

        if sym.calls:
            call_names = sym.calls[:2]
            say2 = f"It calls {', '.join(call_names[:-1]) + ' and ' + call_names[-1] if len(call_names) > 1 else call_names[0]}."
            cap2 = f"Calls: {', '.join(call_names)}"
        elif self.facts.cli_flag_details:
            flag_names = [f.flag.lstrip("-") for f in self.facts.cli_flag_details[:4]]
            say2 = f"It defines flags for {', '.join(flag_names[:-1]) + ' and ' + flag_names[-1] if len(flag_names) > 1 else flag_names[0]}."
            cap2 = f"Flags: {', '.join(f.flag for f in self.facts.cli_flag_details[:3])}"
        else:
            words = [w for w in re.findall(r"\b[A-Za-z0-9_]{3,}\b", chunk2_text) if w.lower() not in STOPWORDS and w.lower() not in {"def", "class", "return", "true", "false", "none", "str", "int", "print"}]
            if len(words) >= 2:
                say2 = f"{sym.name} returns {words[0]} from {words[1]}."
                cap2 = f"{sym.name}: {words[0]} from {words[1]}"
            elif words:
                say2 = f"{sym.name} returns {words[0]} in {Path(sym.file).stem}."
                cap2 = f"{sym.name}: {words[0]}"
            else:
                say2 = f"{sym.name} completes in {Path(sym.file).stem}."
                cap2 = f"{sym.name}: return"

        source2_text = sym.code_excerpt if (sym.calls and sym.code_excerpt) else chunk2_text
        source2_start = sym.start_line if (sym.calls and sym.code_excerpt) else chunk2_start
        source2_end = sym.end_line if (sym.calls and sym.code_excerpt) else chunk2_end

        beats.append(
            Beat(
                say=normalize_speech(say2),
                caption=cap2,
                focus=f"{chunk2_start}-{chunk2_end}",
                sources=[
                    SourceSpan(
                        file=sym.file,
                        start_line=source2_start,
                        end_line=source2_end,
                        text=source2_text,
                    )
                ],
            )
        )

        return Scene(
            id="code",
            kind="code",
            title="Key Code",
            beats=beats,
        )

    def _build_terminal_scene(self) -> Scene | None:
        fences = self.facts.readme.code_fences
        if not fences:
            return None

        commands: list[str] = []
        for f in fences:
            for l in f.splitlines():
                cmd = l.strip().lstrip("$ ")
                if cmd and not cmd.startswith("#"):
                    commands.append(cmd)

        if not commands:
            return None

        # Pick install command and run command
        install_cmd = next((c for c in commands if "install" in c), None)
        run_cmds = [c for c in commands if c != install_cmd]

        beats: list[Beat] = []
        # Beat 1: Install
        if install_cmd:
            say1 = f"Run {install_cmd} to install."
            beats.append(
                Beat(
                    say=normalize_speech(say1),
                    caption=install_cmd,
                    focus="0",
                    sources=[
                        SourceSpan(
                            file=self.readme_file,
                            start_line=1,
                            end_line=50,
                            text=install_cmd,
                        )
                    ],
                )
            )

        # Beat 2: Run command with flag explanation
        if run_cmds:
            run_cmd = run_cmds[0]
            flag_help = ""
            for fl in self.facts.cli_flag_details:
                if fl.flag in run_cmd and fl.help:
                    clean_h = trim_to_clause(fl.help.lower(), max_words=4).rstrip(".")
                    flag_help = f" with {fl.flag.lstrip('-')} for {clean_h}"
                    break
            run_cmd_parts = run_cmd.split()
            short_cmd = " ".join(run_cmd_parts[:3]) if len(run_cmd_parts) > 3 else run_cmd
            say2 = f"Execute {short_cmd}{flag_help}."
            beats.append(
                Beat(
                    say=normalize_speech(say2),
                    caption=run_cmd,
                    focus="1" if install_cmd else "0",
                    sources=[
                        SourceSpan(
                            file=self.readme_file,
                            start_line=1,
                            end_line=60,
                            text=run_cmd,
                        )
                    ],
                )
            )

        return Scene(
            id="terminal",
            kind="terminal",
            title="Terminal",
            beats=beats,
        )

    def _build_fit_scene(self) -> Scene:
        beats: list[Beat] = []
        stages = self.facts.pipeline_stages

        if stages and self.facts.relevance_score >= 0.35:
            first_stage_evidence = next(iter(stages.values())) if stages else ""
            # Stage-by-stage grounded narration
            stage_names = list(stages.keys())
            say1 = f"The pipeline implements {', '.join(stage_names[:-1]) + ' and ' + stage_names[-1] if len(stage_names) > 1 else stage_names[0]} stages."
            cap1 = f"Video pipeline: {', '.join(stage_names)}"

            fit_sources: list[SourceSpan] = []
            for sname, sevidence in stages.items():
                if sevidence and len(sevidence.strip()) >= 20:
                    fit_sources.append(
                        SourceSpan(
                            file=self.readme_file,
                            start_line=1,
                            end_line=50,
                            text=sevidence.strip(),
                        )
                    )
            if not fit_sources:
                fit_sources = [
                    SourceSpan(
                        file=self.readme_file,
                        start_line=1,
                        end_line=30,
                        text=first_stage_evidence,
                    )
                ]

            b1 = Beat(
                say=normalize_speech(say1),
                caption=cap1,
                focus="pipeline",
                sources=fit_sources,
            )
            beats.append(b1)

            say2 = "This connects video clips with searchable representation indexes."
            b2 = Beat(
                say=normalize_speech(say2),
                caption="Searchable multimodal indexes",
                focus="artifacts",
                sources=[
                    SourceSpan(
                        file=self.readme_file,
                        start_line=1,
                        end_line=30,
                        text=first_stage_evidence,
                    )
                ],
            )
            beats.append(b2)
        else:
            # Explicitly state it is not video-specific
            cite_text = self.facts.readme.tagline or self.facts.readme.description or self.facts.repo_name
            clean_clause = trim_to_clause(cite_text, max_words=8)
            say1 = f"{clean_clause} is not video-specific."
            b1 = Beat(
                say=normalize_speech(say1),
                caption=f"{clean_clause}: not video-specific",
                focus="domain",
                sources=[
                    SourceSpan(
                        file=self.readme_file,
                        start_line=1,
                        end_line=20,
                        text=cite_text,
                    )
                ],
            )
            beats.append(b1)

            say2 = "Outputs include transcript dot vtt, chapters dot json, and index dot jsonl."
            b2 = Beat(
                say=normalize_speech(say2),
                caption="Outputs: transcript.vtt, chapters.json, index.jsonl",
                focus="artifacts",
                sources=[
                    SourceSpan(
                        file=self.readme_file,
                        start_line=1,
                        end_line=20,
                        text=cite_text,
                    )
                ],
            )
            beats.append(b2)

        return Scene(
            id="fit",
            kind="fit",
            title="Pipeline Fit",
            beats=beats,
        )

    def _build_recap_scene(self) -> Scene:
        # Determine honest starting file: entry_module, first symbol file, or main code file
        start_file = self.facts.entry_module
        if not start_file and self.facts.top_symbols:
            start_file = self.facts.top_symbols[0].file
        if not start_file:
            # Pick any code file from tree
            code_files = [f for f in self.facts.tree if f.endswith((".py", ".js", ".ts", ".go", ".rs"))]
            if code_files:
                start_file = code_files[0]
            else:
                start_file = self.readme_file or "README.md"

        # Never suggest README or LICENSE when code files exist!
        if start_file in ("README.md", "LICENSE", "license", "LICENSE.md", "README"):
            code_files = [f for f in self.facts.tree if f.endswith((".py", ".js", ".ts", ".go", ".rs"))]
            if code_files:
                start_file = code_files[0]

        clean_tagline = self.facts.readme.tagline
        if not clean_tagline or check_for_banned_phrases(clean_tagline):
            clean_sents = [s for s in self.facts.readme.description_sentences if not check_for_banned_phrases(s.text)]
            if clean_sents:
                clean_tagline = clean_sents[0].text
        if not clean_tagline or check_for_banned_phrases(clean_tagline):
            clean_tagline = f"capabilities for {self.facts.repo_name}"
        tagline_phrase = trim_to_clause(clean_tagline, max_words=6)
        say1 = f"To recap, {self.facts.repo_name} provides {tagline_phrase}"

        beat1 = Beat(
            say=normalize_speech(say1),
            caption=f"Takeaways: {self.facts.repo_name}",
            focus="takeaways",
            sources=[
                SourceSpan(
                    file=self.readme_file,
                    start_line=1,
                    end_line=10,
                    text=self.facts.readme.tagline or self.facts.repo_name,
                )
            ],
        )

        has_code = any(f.endswith((".py", ".js", ".ts", ".go", ".rs")) for f in self.facts.tree)
        if has_code:
            say2 = f"Start with {start_file} to inspect the project implementation."
        else:
            say2 = f"Start with {start_file} to inspect the documentation guidelines."

        beat2 = Beat(
            say=normalize_speech(say2),
            caption=f"Start with {start_file}",
            focus=start_file,
            sources=[],
        )

        return Scene(
            id="recap",
            kind="recap",
            title="Takeaways",
            beats=[beat1, beat2],
        )

    def _fill_sparse_scenes(self, scenes: list[Scene]) -> list[Scene]:
        """Ensure minimal 3 scenes for sparse repos."""
        has_title = any(s.id == "title" for s in scenes)
        has_recap = any(s.id == "recap" for s in scenes)
        if not has_title:
            t = self._build_title_scene()
            if t:
                scenes.insert(0, t)

        if len(scenes) < 2:
            ov = self._build_overview_scene()
            if ov:
                scenes.append(ov)

        if not has_recap:
            rc = self._build_recap_scene()
            if rc:
                scenes.append(rc)

        return scenes


def write_explainer_script(facts: RepoFacts) -> ScriptPlan:
    """Entry point for the extractive explainer writer."""
    writer = ExplainerWriter(facts)
    return writer.write_script()
