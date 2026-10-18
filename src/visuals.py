"""
Visual asset builder: constructs deterministic OnScreen specifications directly
from RepoFacts so that planners/LLMs cannot hallucinate or author visual content.
"""

from __future__ import annotations

import logging
from typing import Any
from .schema import OnScreen, Scene, ScriptPlan

logger = logging.getLogger(__name__)


def build_scene_visuals(scene_kind: str, facts: Any) -> OnScreen:
    """Build grounded OnScreen object for a scene based on RepoFacts."""
    # Primary language
    lang = "Python"
    if hasattr(facts, "languages_by_bytes") and facts.languages_by_bytes:
        lang = max(facts.languages_by_bytes.items(), key=lambda kv: kv[1])[0]

    # Owner: None for local or empty
    owner = getattr(facts, "owner", "") or ""
    if owner in ("local", "None", ""):
        owner_val = None
    else:
        owner_val = owner

    if scene_kind == "title":
        tagline = getattr(facts.readme, "tagline", "") if hasattr(facts, "readme") else ""
        content = f"{facts.repo_name}\n{owner_val or ''}\n{lang}"
        metadata = {
            "repo": facts.repo_name,
            "owner": owner_val,
            "language": lang,
            "tagline": tagline,
        }
        return OnScreen(type="title", content=content, metadata=metadata)

    elif scene_kind == "overview":
        points = []
        if hasattr(facts, "readme"):
            if getattr(facts.readme, "features", None):
                points = [f.strip() for f in facts.readme.features[:3] if f.strip()]
            if not points and getattr(facts.readme, "description_sentences", None):
                for s in facts.readme.description_sentences[:3]:
                    txt = s.text if hasattr(s, "text") else str(s)
                    if txt.strip():
                        points.append(txt.strip())
            if not points and getattr(facts.readme, "description", None):
                points = [facts.readme.description[:120]]
        if not points:
            points = [f"{facts.repo_name} core codebase"]
        content = "\n".join(points)
        return OnScreen(type="overview", content=content, metadata={"points": points})

    elif scene_kind == "diagram":
        nodes: list[str] = []
        if hasattr(facts, "ranked_top_modules") and facts.ranked_top_modules:
            nodes = list(facts.ranked_top_modules[:8])
        elif hasattr(facts, "import_graph") and facts.import_graph:
            seen: list[str] = []
            for e in facts.import_graph:
                if e.source not in seen:
                    seen.append(e.source)
                if e.target not in seen:
                    seen.append(e.target)
            nodes = seen[:8]
        if not nodes:
            entry_mod = getattr(facts, "entry_module", "")
            if entry_mod:
                nodes = [entry_mod]

        edges: list[dict[str, str]] = []
        if hasattr(facts, "import_graph") and facts.import_graph:
            for e in facts.import_graph:
                if e.source in nodes and e.target in nodes:
                    edges.append({"from": e.source, "to": e.target})

        edge_str = "\n".join(f"{e['from']} -> {e['to']}" for e in edges)
        content = edge_str if edge_str else "\n".join(nodes)
        if not content:
            content = facts.repo_name
        return OnScreen(type="diagram", content=content, metadata={"nodes": nodes, "edges": edges})

    elif scene_kind == "code":
        sym = None
        entry_mod = getattr(facts, "entry_module", "")
        if hasattr(facts, "top_symbols") and facts.top_symbols:
            # First try entry_module function
            if entry_mod:
                for s in facts.top_symbols:
                    if s.file == entry_mod and s.kind == "function":
                        sym = s
                        break
            if not sym:
                # Any function
                for s in facts.top_symbols:
                    if s.kind == "function":
                        sym = s
                        break
            if not sym:
                sym = facts.top_symbols[0]

        if sym:
            content = sym.code_excerpt or sym.def_line or f"def {sym.name}(): pass"
            code_file = sym.file
            metadata = {
                "file": code_file,
                "symbol": sym.name,
                "start_line": sym.start_line,
                "end_line": sym.end_line,
            }
        else:
            code_file = entry_mod or "main.py"
            content = "def main():\n    pass"
            metadata = {
                "file": code_file,
                "symbol": "main",
                "start_line": 1,
                "end_line": 2,
            }
        return OnScreen(type="code", content=content, metadata=metadata)

    elif scene_kind == "terminal":
        cmd = ""
        fences = getattr(facts.readme, "code_fences", []) if hasattr(facts, "readme") else []
        for f in fences:
            for line in f.splitlines():
                s = line.strip().lstrip("$ ")
                if s.startswith("pip install") or s.startswith("python -m") or s.startswith("npm install"):
                    cmd = s
                    break
            if cmd:
                break
        if not cmd and fences:
            first_line = fences[0].strip().splitlines()[0].strip().lstrip("$ ")
            if first_line:
                cmd = first_line
        if not cmd:
            cmd = f"pip install {facts.repo_name}"
        return OnScreen(type="terminal", content=f"$ {cmd}", metadata={"command": cmd})

    elif scene_kind == "fit":
        score = getattr(facts, "relevance_score", 0.0)
        terms = getattr(facts, "matched_relevance_terms", [])
        stages = getattr(facts, "pipeline_stages", {})
        terms_str = ", ".join(terms) if terms else "general development"
        content = f"Video Pipeline Fit\nRelevance Score: {score:.2f}\nRelevant terms: {terms_str}"
        return OnScreen(
            type="fit",
            content=content,
            metadata={
                "relevance_score": score,
                "terms": terms,
                "pipeline_stages": stages,
            },
        )

    elif scene_kind == "recap":
        takeaways = []
        if hasattr(facts, "readme") and getattr(facts.readme, "description_sentences", None):
            first = facts.readme.description_sentences[0]
            txt = first.text if hasattr(first, "text") else str(first)
            takeaways.append(f"1. {txt[:60]}")
        else:
            takeaways.append(f"1. {facts.repo_name} core capabilities")

        entry_mod = getattr(facts, "entry_module", "")
        if entry_mod:
            takeaways.append(f"2. Architecture centered on {entry_mod}")
        else:
            takeaways.append("2. Modular package structure")

        takeaways.append("3. Quickstart and production deployment")

        # Start with entry_module, never LICENSE or README
        next_file = entry_mod
        if not next_file and hasattr(facts, "top_symbols") and facts.top_symbols:
            next_file = facts.top_symbols[0].file
        if not next_file:
            next_file = "main.py"

        content = "\n".join(takeaways)
        return OnScreen(
            type="recap",
            content=content,
            metadata={"takeaways": takeaways, "next_file": next_file},
        )

    else:
        return OnScreen(type="text", content=f"{facts.repo_name} {scene_kind}", metadata={})


def attach_visuals_to_script(script: ScriptPlan, facts: Any) -> ScriptPlan:
    """Populate each scene's on_screen specification strictly from RepoFacts."""
    for scene in script.scenes:
        scene.on_screen = build_scene_visuals(scene.kind, facts)
    return script
