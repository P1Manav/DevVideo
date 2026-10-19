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
        if len(plan.scenes) > 6:
            plan.scenes = plan.scenes[:6]
        return plan.model_dump_json()

    def plan(
        self,
        facts: RepoFacts,
        limits: dict[str, Any] | None = None,
        feedback: list[str] | None = None,
    ) -> ScriptPlan:
        from .narrate import write_explainer_script
        return write_explainer_script(facts)


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
- NEVER use buzzwords (BANNED PHRASES): modular, readable, robust, leverage, seamless, critical processing components, state of the art, structured for extension, generic implementation boilerplate, structured solutions, developer workflows, we explore, this project organizes, provides critical, utilizes, powers multimodal.
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

