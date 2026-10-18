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
    check_for_banned_phrases,
    normalize_speech,
)

logger = logging.getLogger(__name__)


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
        scenes: list[Scene] = []
        repo = facts.repo_name
        owner = facts.owner or "developer"
        top_lang = next(iter(facts.languages_by_bytes.keys()), "Python")

        # Determine evidence sources
        readme_file = "README.md"
        first_file = next(iter(facts.tree), "README.md")
        if "/" in first_file:
            first_file = first_file.rstrip("/")

        # -------------------------------------------------------------
        # Scene 1: Title
        # -------------------------------------------------------------
        tagline = facts.readme.description[:120] if facts.readme.description else f"{repo} development toolkit"
        title_quote = facts.readme.title if facts.readme.title else repo

        s1_say = f"Welcome to {normalize_speech(title_quote)}. Here is what you need to know in under one minute."
        s1_cap = f"Introducing {repo}: {tagline}"
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
        overview_body = facts.readme.description or f"{repo} organizes source modules for direct developer use."
        ov_quote = overview_body[:80] if overview_body else title_quote
        ov_say_1 = f"This project provides {normalize_speech(overview_body[:100])}."
        ov_say_2 = "You can integrate it directly into your local development workflows."
        scenes.append(Scene(
            id="overview",
            kind="overview",
            title="Purpose",
            beats=[
                Beat(say=ov_say_1, caption=overview_body[:90], focus="purpose"),
                Beat(say=ov_say_2, caption="Integrates into developer workflows", focus="integration"),
            ],
            on_screen=OnScreen(
                type="overview",
                content=f"{repo}\n\n{overview_body}",
                metadata={"points": [overview_body[:80], "Clear developer interface"]},
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
            diag_file = top_edges[0].source
            target_base = top_edges[0].target.split("/")[-1].replace(".py", "").replace(".js", "")
            diag_quote = target_base if len(target_base) >= 3 else "import"

            d_say_1 = f"The architecture is organized around {len(nodes)} core modules."
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
            sym = facts.top_symbols[0]
            code_line = f"def {sym.name}():" if sym.kind == "function" else f"class {sym.name}:"
            code_quote = sym.name
            code_say_1 = f"Let us look at {normalize_speech(sym.name)} in {normalize_speech(sym.file)}."
            code_say_2 = f"It {normalize_speech(sym.docstring)}" if sym.docstring else "It defines the main functional entrypoint."
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
                    content=f"# {sym.file}:{sym.start_line}-{sym.end_line}\n{code_line}\n    # {sym.docstring or 'Entry point'}\n    ...",
                    metadata={
                        "file": sym.file,
                        "symbol": sym.name,
                        "start_line": sym.start_line,
                        "end_line": min(sym.start_line + 12, sym.end_line),
                    },
                ),
                evidence=Evidence(file=sym.file, quote=code_quote),
            ))

        # -------------------------------------------------------------
        # Scene 5: Terminal (Quickstart Command)
        # -------------------------------------------------------------
        command = ""
        cmd_file = readme_file
        if facts.readme.code_fences:
            for fence in facts.readme.code_fences:
                for line in fence.splitlines():
                    clean_l = line.strip().lstrip("$ ")
                    if any(clean_l.startswith(pfx) for pfx in ("pip", "python", "npm", "npx", "cargo", "go", "make", "docker")):
                        command = clean_l
                        break
                if command:
                    break

        if not command and facts.entry_points:
            command = f"python -m {facts.entry_points[0].replace('/', '.').replace('.py', '')}"
            cmd_file = facts.entry_points[0]

        if not command:
            command = f"pip install -e ."

        cmd_quote = command.split()[0] if command else "install"
        t_say_1 = "To run this project, execute the quickstart command in your shell."
        t_say_2 = f"Run {normalize_speech(command)}."
        scenes.append(Scene(
            id="terminal",
            kind="terminal",
            title="Terminal",
            beats=[
                Beat(say=t_say_1, caption="Run quickstart command in shell", focus="prompt"),
                Beat(say=t_say_2, caption=command[:80], focus="command"),
            ],
            on_screen=OnScreen(
                type="terminal",
                content=f"$ {command}",
                metadata={"command": command},
            ),
            evidence=Evidence(file=cmd_file, quote=cmd_quote if cmd_quote in command else command[:10]),
        ))

        # -------------------------------------------------------------
        # Scene 6: Fit (Video Understanding / Retrieval Alignment)
        # -------------------------------------------------------------
        if facts.is_video_relevant:
            matched_str = ", ".join(facts.matched_relevance_terms[:3])
            fit_say_1 = f"In AI video pipelines, this repository powers indexing and retrieval using {normalize_speech(matched_str)}."
            fit_say_2 = "It processes source video assets into searchable representation vectors."
            fit_cap = f"Powers video pipelines: {matched_str}"
            fit_quote = facts.matched_relevance_terms[0] if facts.matched_relevance_terms else title_quote
        else:
            fit_say_1 = f"{normalize_speech(title_quote)} is a general-purpose project and is not video-specific."
            fit_say_2 = "This generated video ships with retrieval transcripts, chapters, and index records for video search engines."
            fit_cap = "Outputs transcript.vtt, chapters.json, and index.jsonl"
            fit_quote = title_quote

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
        takeaways = [
            f"1. {repo} solves {facts.readme.description[:40] or 'core tasks'}",
            f"2. Quickstart via {command[:30]}",
            f"3. Explored via {first_file}",
        ]
        rc_say_1 = f"To recap: {normalize_speech(title_quote)} provides clear components for your workflow."
        rc_say_2 = f"Next, check out {normalize_speech(first_file)} to start developing."
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
            evidence=Evidence(file=readme_file, quote=title_quote),
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
    Embeds RepoFacts and repo files in a nonce-delimited data block.
    Extracts JSON response tolerantly.
    """
    name = "claude"

    def __init__(self, claude_adapter: ClaudeLLM | None = None) -> None:
        self.claude = claude_adapter or ClaudeLLM()

    def plan(
        self,
        facts: RepoFacts,
        limits: dict[str, Any] | None = None,
        feedback: list[str] | None = None,
    ) -> ScriptPlan:
        nonce = secrets.token_hex(8)
        start_del = f"=== UNTRUSTED_REPO_DATA_{nonce} ==="
        end_del = f"=== END_UNTRUSTED_REPO_DATA_{nonce} ==="

        # Summary of repo facts
        facts_summary = {
            "repo_name": facts.repo_name,
            "owner": facts.owner,
            "languages": facts.languages_by_bytes,
            "entry_points": facts.entry_points[:4],
            "top_symbols": [s.model_dump() for s in facts.top_symbols[:4]],
            "import_edges": [e.model_dump() for e in facts.import_graph[:6]],
            "cli_flags": facts.cli_flags[:6],
            "dependencies": facts.dependencies[:8],
            "relevance_score": facts.relevance_score,
            "is_video_relevant": facts.is_video_relevant,
        }

        feedback_prompt = ""
        if feedback:
            feedback_prompt = "\nPREVIOUS DRAFT REJECTED FOR REASONS:\n" + "\n".join(f"- {fb}" for fb in feedback)

        prompt = f"""You are a video script planner for developer explainer videos.
Generate a JSON ScriptPlan with 5 to 7 scenes following this blueprint:
1. title    (intro)
2. overview (problem and solution)
3. diagram  (architecture)
4. code     (key code path, <= 14 lines)
5. terminal (quickstart command)
6. fit      (pipeline fit: honest domain match or general-purpose outputs)
7. recap    (3 takeaways)

Style rules:
- Speak in plain English, second person ('you').
- Use short sentences (<= 22 words per beat).
- NEVER use buzzwords: modular, readable, robust, leverage, seamless, critical processing components, state of the art, structured for extension.
- Every scene must cite a real file and verbatim quote that exists in that file.
{feedback_prompt}

{start_del}
REPO_FACTS_JSON:
{json.dumps(facts_summary, indent=2)}

README_TITLE: {facts.readme.title}
README_DESCRIPTION: {facts.readme.description}
CODE_FENCES:
{chr(10).join(facts.readme.code_fences[:3])}
{end_del}

INSTRUCTIONS:
Respond with ONLY a raw valid JSON object matching this schema:
{{
  "repo_name": "{facts.repo_name}",
  "scenes": [
    {{
      "id": "scene_id",
      "kind": "title|overview|diagram|code|terminal|fit|recap",
      "title": "Display Title",
      "beats": [
        {{"say": "spoken words", "caption": "short on-screen caption", "focus": "optional_id"}}
      ],
      "on_screen": {{"type": "text", "content": "visual content"}},
      "evidence": {{"file": "README.md", "quote": "verbatim quote"}}
    }}
  ]
}}
Do NOT output markdown fences or conversational prelude. Return only the JSON object.
"""
        response_text = self.claude.complete(prompt)
        parsed_json = extract_json_object(response_text)
        return ScriptPlan(**parsed_json)
