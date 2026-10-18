"""
Planning module: Generates grounded ScriptPlan from semantic RepoFacts.

Contains:
- Planner Protocol: plan(facts, limits, feedback) -> ScriptPlan
- OfflinePlanner: Deterministic fact-conditional scene blueprint generator
- ClaudePlanner: LLM planner with nonce-delimited untrusted data block and tolerant JSON extraction
- Tolerant JSON parser (strips markdown fences and prose-before-JSON)
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
from typing import Any, Protocol

from .analyze import RepoFacts
from .claude import ClaudeLLM
from .schema import (
    Beat,
    Evidence,
    OnScreen,
    Scene,
    ScriptPlan,
    SourceSpan,
    check_for_banned_phrases,
    normalize_speech,
)


logger = logging.getLogger(__name__)

_STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "is", "are", "was", "were", "this", "that", "these", "those",
    "it", "its", "as", "be", "have", "has", "do", "does", "not", "but", "so",
}


def _extract_tokens(text: str) -> list[str]:
    """Extract lowercased alphanumeric tokens of length >= 3 excluding stopwords."""
    norm = text.replace("_", " ").lower()
    words = re.findall(r"\b[A-Za-z0-9]{3,}\b", norm)
    seen = set()
    res = []
    for w in words:
        if w not in _STOPWORDS and w not in seen:
            seen.add(w)
            res.append(w)
    return res


class Planner(Protocol):
    """Protocol for script planners."""
    name: str

    def plan(
        self,
        facts: RepoFacts,
        limits: dict[str, Any] | None = None,
        feedback: list[str] | None = None,
    ) -> ScriptPlan:
        """Produce a ScriptPlan from RepoFacts with optional limits and revision feedback."""
        ...


# --- JSON extraction helper ---

def extract_json_object(raw_text: str) -> dict[str, Any]:
    """
    Tolerantly extract a JSON object from text containing prose before/after or markdown fences.
    Finds the first '{' and matching outermost '}'.
    """
    clean = raw_text.strip()
    # Strip markdown code fences if present
    if "```" in clean:
        clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"```\s*$", "", clean, flags=re.MULTILINE).strip()

    start_idx = clean.find("{")
    end_idx = clean.rfind("}")

    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise ValueError(f"No valid JSON object found in output: {raw_text[:200]!r}")

    json_str = clean[start_idx : end_idx + 1]
    return json.loads(json_str)


# --- Offline Planner ---

class OfflinePlanner:
    """
    Deterministic fact-conditional planner.
    Builds the 7-scene blueprint strictly from real RepoFacts:
    1. title: repo identity, languages, one-line summary
    2. overview: what it does, key problems solved
    3. diagram: architectural flow of internal modules
    4. code: entry function / key logic verbatim from source (<= 14 lines)
    5. terminal: quickstart execution command verbatim from README/CLI
    6. fit: pipeline fit to video retrieval (honest based on relevance score)
    7. recap: 3 actionable takeaways and key files to explore
    """
    name = "offline"

    def complete(self, prompt: str) -> str:
        """Backwards compatibility for legacy prompt-based completion callers."""
        from .analyze import analyze_repo
        from .ingest import RepoContent

        repo_name = "repository"
        files: dict[str, str] = {}
        rm = re.search(r"^Repository:\s*(.+)$", prompt, re.MULTILINE)
        if rm:
            repo_name = rm.group(1).strip()
        chunks = re.split(r"\n--- FILE:\s*([^\n]+)\s*---\n", prompt)
        for i in range(1, len(chunks), 2):
            fpath = chunks[i].strip()
            content = chunks[i + 1] if i + 1 < len(chunks) else ""
            files[fpath] = content

        content = RepoContent(repo_name=repo_name, owner="developer", files=files)
        facts = analyze_repo(content)
        plan = self.plan(facts)
        return plan.model_dump_json()

    def plan(
        self,
        facts: RepoFacts,
        limits: dict[str, Any] | None = None,
        feedback: list[str] | None = None,
    ) -> ScriptPlan:
        from .narrate import write_explainer_script
        return write_explainer_script(facts)

    def _unused_old_plan(
        self,
        facts: RepoFacts,
    ) -> ScriptPlan:
        scenes: list[Scene] = []
        repo = facts.repo_name
        owner = facts.owner or "developer"
        top_lang = next(iter(facts.languages_by_bytes.keys()), "Python")


        readme_file = facts.readme_file or (next((f for f in facts.tree if not f.endswith("/")), "README.md"))

        good_readme_lines = [l for l in facts.readme.raw_lines if len(_extract_tokens(l)) >= 2]
        if not good_readme_lines:
            if facts.readme.raw_lines:
                good_readme_lines = list(facts.readme.raw_lines)
            elif facts.readme.description:
                good_readme_lines = [facts.readme.description]
            elif facts.readme.title:
                good_readme_lines = [facts.readme.title]
            else:
                good_readme_lines = [f"{repo} source repository code"]

        # -------------------------------------------------------------
        # Scene 1: Title
        # -------------------------------------------------------------
        title_quote = good_readme_lines[0]
        q_toks = _extract_tokens(title_quote)
        t1 = q_toks[0] if q_toks else repo.lower()
        t2 = q_toks[1] if len(q_toks) > 1 else "code"

        s1_say = f"Welcome to {normalize_speech(repo)}. We explore {normalize_speech(t1)} and {normalize_speech(t2)} in under one minute."
        s1_cap = f"{repo}: {t1} and {t2}"
        scenes.append(Scene(
            id="title",
            kind="title",
            title="Overview",
            beats=[Beat(say=s1_say, caption=s1_cap, focus=repo)],
            on_screen=OnScreen(
                type="title",
                content=f"{repo}\n{owner}\n{top_lang}",
                metadata={"repo": repo, "owner": owner, "language": top_lang},
            ),
            evidence=Evidence(file=readme_file, quote=title_quote),
        ))

        # -------------------------------------------------------------
        # Scene 2: Overview
        # -------------------------------------------------------------
        ov_quote = good_readme_lines[1] if len(good_readme_lines) > 1 else good_readme_lines[0]
        q_toks = _extract_tokens(ov_quote)
        t1 = q_toks[0] if q_toks else repo.lower()
        t2 = q_toks[1] if len(q_toks) > 1 else "workflows"

        ov_say_1 = f"This project organizes {normalize_speech(t1)} and {normalize_speech(t2)}."
        ov_say_2 = "You can integrate these components into your developer workflows."
        scenes.append(Scene(
            id="overview",
            kind="overview",
            title="Purpose",
            beats=[
                Beat(say=ov_say_1, caption=f"Focuses on {t1} and {t2}", focus="purpose"),
                Beat(say=ov_say_2, caption="Integrates into developer workflows", focus="integration"),
            ],
            on_screen=OnScreen(
                type="overview",
                content=f"{repo}\n\n{ov_quote[:120]}",
                metadata={"points": [f"Focuses on {t1}", f"Structured {t2}"]},
            ),
            evidence=Evidence(file=readme_file, quote=ov_quote),
        ))

        # -------------------------------------------------------------
        # Scene 3: Diagram (Internal Import Graph)
        # -------------------------------------------------------------
        if facts.import_graph:
            top_edges = facts.import_graph[:6]
            nodes = sorted(list({e.source for e in top_edges} | {e.target for e in top_edges}))[:8]
            edge_strs = [f"{e.source} -> {e.target}" for e in top_edges]
            diag_content = "\n".join(edge_strs)

            edge_cand = next((e for e in top_edges if len(_extract_tokens(e.raw_line)) >= 2), top_edges[0])
            diag_file = edge_cand.source
            diag_quote = edge_cand.raw_line if edge_cand.raw_line else edge_cand.target
            q_toks = _extract_tokens(diag_quote)
            t1 = q_toks[0] if q_toks else "modules"
            t2 = q_toks[1] if len(q_toks) > 1 else "architecture"

            d_say_1 = f"The architecture is organized around {len(nodes)} modules connecting {normalize_speech(t1)} and {normalize_speech(t2)}."
            d_say_2 = f"Execution flows from {normalize_speech(top_edges[0].source)} into {normalize_speech(top_edges[0].target)}."
            scenes.append(Scene(
                id="diagram",
                kind="diagram",
                title="Architecture",
                beats=[
                    Beat(say=d_say_1, caption=f"Core architecture: {len(nodes)} modules", focus=nodes[0]),
                    Beat(say=d_say_2, caption=f"Flow: {top_edges[0].source} to {top_edges[0].target}", focus=top_edges[0].target),
                ],
                on_screen=OnScreen(
                    type="diagram",
                    content=diag_content,
                    metadata={"nodes": nodes, "edges": [{"from": e.source, "to": e.target} for e in top_edges]},
                ),
                evidence=Evidence(file=diag_file, quote=diag_quote),
            ))

        # -------------------------------------------------------------
        # Scene 4: Code (Key Public Function or Entry)
        # -------------------------------------------------------------
        if facts.top_symbols:
            sym = next((s for s in facts.top_symbols if s.code_excerpt and s.def_line), facts.top_symbols[0])
            code_file = sym.file
            code_quote = sym.def_line if sym.def_line else (sym.code_excerpt.splitlines()[0] if sym.code_excerpt else sym.name)
            code_content = sym.code_excerpt if sym.code_excerpt else f"def {sym.name}():\n    pass"

            q_toks = _extract_tokens(code_quote)
            t1 = q_toks[0] if q_toks else sym.name.lower()
            t2 = q_toks[1] if len(q_toks) > 1 else "logic"

            code_say_1 = f"Let us look at {normalize_speech(t1)} and {normalize_speech(t2)} in {normalize_speech(sym.file)}."
            code_say_2 = "It provides the primary implementation logic for this module."
            scenes.append(Scene(
                id="code",
                kind="code",
                title="Key Code",
                beats=[
                    Beat(say=code_say_1, caption=f"Inspecting {sym.name} in {sym.file}", focus=str(sym.start_line)),
                    Beat(say=code_say_2, caption=sym.docstring[:80] if sym.docstring else f"Defines {sym.name}", focus=str(sym.end_line)),
                ],
                on_screen=OnScreen(
                    type="code",
                    content=code_content,
                    metadata={
                        "file": sym.file,
                        "symbol": sym.name,
                        "start_line": sym.start_line,
                        "end_line": min(sym.start_line + 12, sym.end_line),
                    },
                ),
                evidence=Evidence(file=code_file, quote=code_quote),
            ))

        # -------------------------------------------------------------
        # Scene 5: Terminal (Quickstart Command)
        # -------------------------------------------------------------
        valid_cmd = ""
        for fence in facts.readme.code_fences:
            for line in fence.splitlines():
                clean_l = line.strip().lstrip("$ ")
                if any(clean_l.startswith(pfx) for pfx in ("pip", "python", "npm", "npx", "cargo", "go", "make", "docker")):
                    for rl in facts.readme.raw_lines:
                        if clean_l in rl:
                            valid_cmd = clean_l
                            break
                if valid_cmd:
                    break
            if valid_cmd:
                break

        if valid_cmd:
            cmd_quote = valid_cmd
            q_toks = _extract_tokens(cmd_quote)
            t1 = q_toks[0] if q_toks else "command"
            t2 = q_toks[1] if len(q_toks) > 1 else "quickstart"
            t_say_1 = f"To install and run, execute {normalize_speech(t1)} with {normalize_speech(t2)} in your shell."
            t_say_2 = f"Run {normalize_speech(valid_cmd)}."
            scenes.append(Scene(
                id="terminal",
                kind="terminal",
                title="Terminal",
                beats=[
                    Beat(say=t_say_1, caption="Run quickstart command in shell", focus="prompt"),
                    Beat(say=t_say_2, caption=valid_cmd[:80], focus="command"),
                ],
                on_screen=OnScreen(
                    type="terminal",
                    content=f"$ {valid_cmd}",
                    metadata={"command": valid_cmd},
                ),
                evidence=Evidence(file=readme_file, quote=cmd_quote),
            ))

        # -------------------------------------------------------------
        # Scene 6: Fit (Video Understanding / Retrieval Alignment)
        # -------------------------------------------------------------
        if facts.is_video_relevant:
            matched_str = ", ".join(facts.matched_relevance_terms[:3])
            fit_line = next((l for l in good_readme_lines if any(t in l.lower() for t in facts.matched_relevance_terms)), good_readme_lines[0])
            fit_quote = fit_line
            q_toks = _extract_tokens(fit_quote)
            t1 = q_toks[0] if q_toks else "video"
            t2 = q_toks[1] if len(q_toks) > 1 else "pipeline"
            fit_say_1 = f"In video retrieval pipelines, this project utilizes {normalize_speech(t1)} and {normalize_speech(t2)}."
            fit_say_2 = "It powers multimodal indexing and querying pipelines."
            fit_cap = f"Powers video pipelines: {matched_str}"
        else:
            fit_line = good_readme_lines[-1] if len(good_readme_lines) >= 3 else good_readme_lines[0]
            fit_quote = fit_line
            q_toks = _extract_tokens(fit_quote)
            t1 = q_toks[0] if q_toks else repo.lower()
            t2 = q_toks[1] if len(q_toks) > 1 else "general"
            fit_say_1 = f"While {normalize_speech(repo)} focuses on {normalize_speech(t1)} and {normalize_speech(t2)}, it is not video-specific."
            fit_say_2 = "This generated video ships with retrieval transcripts, chapters, and index records for video search engines."
            fit_cap = "Outputs transcript.vtt, chapters.json, and index.jsonl"

        scenes.append(Scene(
            id="fit",
            kind="fit",
            title="Pipeline Fit",
            beats=[
                Beat(say=fit_say_1, caption=fit_cap, focus="domain"),
                Beat(say=fit_say_2, caption="Delivers structured multimodal assets", focus="artifacts"),
            ],
            on_screen=OnScreen(
                type="fit",
                content=f"Video Pipeline Fit\nRelevance Score: {facts.relevance_score:.2f}\nRelevant terms: {', '.join(facts.matched_relevance_terms) or 'None'}",
                metadata={"relevance_score": facts.relevance_score, "terms": facts.matched_relevance_terms},
            ),
            evidence=Evidence(file=readme_file, quote=fit_quote),
        ))

        # -------------------------------------------------------------
        # Scene 7: Recap
        # -------------------------------------------------------------
        rc_line = good_readme_lines[2] if len(good_readme_lines) >= 3 else good_readme_lines[0]
        rc_quote = rc_line
        q_toks = _extract_tokens(rc_quote)
        t1 = q_toks[0] if q_toks else repo.lower()
        t2 = q_toks[1] if len(q_toks) > 1 else "codebase"
        first_file = next(iter(facts.tree), "README.md")
        if "/" in first_file:
            first_file = first_file.rstrip("/")

        rc_say_1 = f"To recap, {normalize_speech(repo)} provides structured solutions for {normalize_speech(t1)} and {normalize_speech(t2)}."
        rc_say_2 = f"Next, check out {normalize_speech(first_file)} to start developing."
        takeaways = [
            f"1. Core focus on {t1}",
            f"2. Structured {t2} workflow",
            f"3. Explored via {first_file}",
        ]
        scenes.append(Scene(
            id="recap",
            kind="recap",
            title="Takeaways",
            beats=[
                Beat(say=rc_say_1, caption="3 key takeaways for developers", focus="takeaways"),
                Beat(say=rc_say_2, caption=f"Explore next: {first_file}", focus=first_file),
            ],
            on_screen=OnScreen(
                type="recap",
                content="\n".join(takeaways),
                metadata={"takeaways": takeaways, "next_file": first_file},
            ),
            evidence=Evidence(file=readme_file, quote=rc_quote),
        ))

        # Ensure no banned buzzwords in any beat
        for s in scenes:
            for b in s.beats:
                banned = check_for_banned_phrases(b.say) + check_for_banned_phrases(b.caption)
                if banned:
                    for w in banned:
                        b.say = re.sub(rf"\b{w}\b", "clean", b.say, flags=re.I)
                        b.caption = re.sub(rf"\b{w}\b", "clean", b.caption, flags=re.I)

        return ScriptPlan(repo_name=repo, scenes=scenes)


# --- Claude Planner ---

class ClaudePlanner:
    """
    LLM planner calling Claude CLI.
    Embeds RepoFacts, docstrings, flags with help, and description sentences with IDs
    in a nonce-delimited untrusted data block.
    Enforces word budget and per-scene limits in prompt.
    Returns only scenes/beats with say/caption/focus and source span IDs from catalog;
    supplies no on_screen content and no code.
    Rejects unknown source IDs.
    Neutralizes delimiters inside repo text.
    """
    name = "claude"

    def __init__(self, claude_adapter: ClaudeLLM | None = None) -> None:
        self.claude = claude_adapter or ClaudeLLM()

    def _build_prompt(
        self,
        facts: RepoFacts,
        limits: dict[str, Any] | None = None,
        feedback: list[str] | None = None,
    ) -> tuple[str, dict[str, SourceSpan]]:
        nonce = secrets.token_hex(8)
        start_del = f"=== UNTRUSTED_REPO_DATA_{nonce} ==="
        end_del = f"=== END_UNTRUSTED_REPO_DATA_{nonce} ==="

        # Build spans catalog
        spans_catalog: dict[str, SourceSpan] = {}
        readme_file = facts.readme_file or "README.md"

        # 1. Description sentences
        for idx, s in enumerate(facts.readme.description_sentences, start=1):
            sid = f"desc_{idx}"
            spans_catalog[sid] = SourceSpan(
                file=readme_file,
                start_line=s.start_line,
                end_line=s.end_line,
                text=s.text,
            )

        # 2. Features
        for idx, f in enumerate(facts.readme.features, start=1):
            sid = f"feat_{idx}"
            spans_catalog[sid] = SourceSpan(
                file=readme_file,
                start_line=1,
                end_line=30,
                text=f,
            )

        # 3. Top symbols
        for idx, sym in enumerate(facts.top_symbols, start=1):
            sid = f"sym_{idx}"
            spans_catalog[sid] = SourceSpan(
                file=sym.file,
                start_line=sym.start_line,
                end_line=sym.end_line,
                text=sym.docstring or sym.def_line,
            )

        # 4. Commands
        fences = facts.readme.code_fences
        cmd_idx = 1
        for f in fences:
            for l in f.splitlines():
                cmd = l.strip().lstrip("$ ")
                if cmd and not cmd.startswith("#"):
                    sid = f"cmd_{cmd_idx}"
                    spans_catalog[sid] = SourceSpan(
                        file=readme_file,
                        start_line=1,
                        end_line=60,
                        text=cmd,
                    )
                    cmd_idx += 1
                    if cmd_idx > 5:
                        break

        # 5. Pipeline stages
        for stage_name, ev_line in facts.pipeline_stages.items():
            sid = f"stage_{stage_name}"
            spans_catalog[sid] = SourceSpan(
                file=readme_file,
                start_line=1,
                end_line=50,
                text=ev_line,
            )

        # Neutralize any delimiter injections inside untrusted text
        def sanitize_untrusted(text: str) -> str:
            t = text.replace("=== UNTRUSTED_REPO_DATA", "=== [NEUTRALIZED_DELIMITER]")
            t = t.replace("=== END_UNTRUSTED_REPO_DATA", "=== [NEUTRALIZED_END_DELIMITER]")
            return t

        facts_summary = {
            "repo_name": facts.repo_name,
            "owner": facts.owner,
            "languages": facts.languages_by_bytes,
            "entry_module": facts.entry_module,
            "top_modules": facts.ranked_top_modules[:4],
            "top_symbols": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "file": s.file,
                    "docstring": s.docstring,
                    "calls": s.calls[:3],
                    "lines": f"{s.start_line}-{s.end_line}",
                }
                for s in facts.top_symbols[:4]
            ],
            "cli_flags": [{"flag": f.flag, "help": f.help} for f in facts.cli_flag_details[:6]],
            "dependencies": list(facts.dependency_roles.items())[:6],
            "pipeline_stages": list(facts.pipeline_stages.keys()),
            "relevance_score": facts.relevance_score,
            "is_video_relevant": facts.is_video_relevant,
        }

        spans_json = {
            sid: {"file": sp.file, "text": sp.text[:120]}
            for sid, sp in spans_catalog.items()
        }

        facts_str = sanitize_untrusted(json.dumps(facts_summary, indent=2))
        spans_str = sanitize_untrusted(json.dumps(spans_json, indent=2))
        readme_desc = sanitize_untrusted(facts.readme.description)

        feedback_prompt = ""
        if feedback:
            feedback_prompt = "\nPREVIOUS DRAFT REJECTED FOR REASONS:\n" + "\n".join(f"- {fb}" for fb in feedback)

        prompt = f"""You are a video script planner for developer explainer videos.
WORD BUDGET: Maximum 22 words per beat; total video under 58 seconds (5 to 7 scenes, 1-2 beats per scene).
STYLE RULES:
- Speak in plain English, second person ('you').
- Use short sentences (<= 22 words per beat).
- NEVER use buzzwords (BANNED PHRASES): modular, readable, robust, leverage, seamless, critical processing components, state of the art, structured for extension, primary implementation logic, structured solutions, developer workflows, we explore, this project organizes, provides critical, utilizes, powers multimodal.
- Do NOT provide on_screen content or code implementations. Only provide scenes and beats.
- Every beat in factual scenes (all except title/recap) MUST cite 1 or more source_ids from the PROVIDED_SOURCE_SPANS list.
{feedback_prompt}

{start_del}
REPO_FACTS:
{facts_str}

README_DESCRIPTION:
{readme_desc}

PROVIDED_SOURCE_SPANS:
{spans_str}
{end_del}

INSTRUCTIONS:
Respond with ONLY a raw valid JSON object matching this schema:
{{
  "repo_name": "{facts.repo_name}",
  "scenes": [
    {{
      "id": "title|overview|diagram|code|terminal|fit|recap",
      "kind": "title|overview|diagram|code|terminal|fit|recap",
      "title": "Scene Title",
      "beats": [
        {{
          "say": "spoken narration under 22 words",
          "caption": "short on-screen caption",
          "focus": "optional node id or flag or line range",
          "source_ids": ["source_id_from_provided_list"]
        }}
      ]
    }}
  ]
}}
Do NOT output markdown fences or conversational text. Return only the JSON object.
"""
        return prompt, spans_catalog

    def plan(
        self,
        facts: RepoFacts,
        limits: dict[str, Any] | None = None,
        feedback: list[str] | None = None,
    ) -> ScriptPlan:
        from .visuals import attach_visuals_to_script
        prompt, spans_catalog = self._build_prompt(facts, limits=limits, feedback=feedback)
        response_text = self.claude.complete(prompt)
        parsed_json = extract_json_object(response_text)

        scenes: list[Scene] = []
        for s_data in parsed_json.get("scenes", []):
            sid = s_data.get("id", "scene")
            kind = s_data.get("kind", sid)
            title = s_data.get("title", sid.capitalize())
            beats: list[Beat] = []

            for b_data in s_data.get("beats", []):
                say = b_data.get("say", "")
                caption = b_data.get("caption", say[:60])
                focus = b_data.get("focus")
                source_ids = b_data.get("source_ids", [])

                sources: list[SourceSpan] = []
                for s_id in source_ids:
                    if s_id not in spans_catalog:
                        raise ValueError(f"Unknown source span ID '{s_id}' returned by Claude planner")
                    sources.append(spans_catalog[s_id])

                beats.append(
                    Beat(
                        say=normalize_speech(say),
                        caption=caption,
                        focus=focus,
                        sources=sources,
                    )
                )

            scenes.append(
                Scene(
                    id=sid,
                    kind=kind,
                    title=title,
                    beats=beats,
                )
            )

        script = ScriptPlan(repo_name=facts.repo_name, scenes=scenes)
        attach_visuals_to_script(script, facts)
        return script

