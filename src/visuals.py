"""
Visual asset builder: constructs deterministic OnScreen specifications directly
from RepoFacts so that planners/LLMs cannot hallucinate or author visual content.
"""

from __future__ import annotations

import logging
from typing import Any
from .schema import OnScreen, Scene, ScriptPlan

logger = logging.getLogger(__name__)

DANGLING_STOPWORDS = {
    "a", "an", "the", "of", "on", "in", "to", "for", "with", "by", "from",
    "and", "or", "but", "that", "which", "is", "are", "was", "be", "as",
    "at", "than", "then", "if", "most", "more", "its", "into", "their", "our", "your",
}


def clean_takeaway_line(text: str, max_words: int = 8) -> str:
    """Format a takeaway line cleanly without mid-word cuts or dangling stopwords."""
    words = text.split()[:max_words]
    while words and words[-1].lower().rstrip(".,;:!?") in DANGLING_STOPWORDS:
        words.pop()
    return " ".join(words).rstrip(".,;:!?")


def select_primary_code_symbol(facts: Any) -> Any:
    """T6: Select key code symbol: public function, non-trivial, referenced in README usage/CLI, 6-25 lines."""
    from .analyze import is_auxiliary_or_test_path
    import re

    if not hasattr(facts, "top_symbols") or not facts.top_symbols:
        return None

    readme_usage = ""
    if hasattr(facts, "readme"):
        readme_usage = " ".join(getattr(facts.readme, "usage_commands", [])) + " " + " ".join(getattr(facts.readme, "code_fences", []))

    preferred_names = {"main", "run", "load", "search", "query", "encode", "transcode", "process"}

    def _sym_score(s: Any) -> tuple[int, int, int, int, int]:
        is_core_path = 1 if not is_auxiliary_or_test_path(s.file) else 0
        is_pub = 1 if not s.name.startswith("_") else 0
        is_func = 2 if getattr(s, "kind", "") == "function" else 1
        is_pref = 2 if s.name.lower() in preferred_names else 0
        non_trivial = 0 if getattr(s, "is_trivial", False) else 1
        in_usage = 2 if (s.name and re.search(rf"\b{re.escape(s.name)}\b", readme_usage)) else 0
        lines_cnt = s.end_line - s.start_line + 1
        good_len = 1 if 5 <= lines_cnt <= 30 else 0
        return (is_core_path, is_pub, non_trivial, is_func + is_pref + in_usage, good_len)

    ranked = sorted(facts.top_symbols, key=_sym_score, reverse=True)
    return ranked[0]


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
        sym = select_primary_code_symbol(facts)
        entry_mod = getattr(facts, "entry_module", "")
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
            cleaned = clean_takeaway_line(txt, max_words=8)
            takeaways.append(f"1. {cleaned}")
        elif getattr(facts.readme, "tagline", None):
            cleaned = clean_takeaway_line(facts.readme.tagline, max_words=8)
            takeaways.append(f"1. {cleaned}")
        else:
            takeaways.append(f"1. {facts.repo_name} project overview")

        entry_mod = getattr(facts, "entry_module", "")
        if entry_mod:
            takeaways.append(f"2. Entry point {entry_mod}")
        elif hasattr(facts, "ranked_top_modules") and facts.ranked_top_modules:
            takeaways.append(f"2. Primary module {facts.ranked_top_modules[0]}")
        elif hasattr(facts, "top_symbols") and facts.top_symbols:
            takeaways.append(f"2. Defines {facts.top_symbols[0].name}")
        else:
            takeaways.append(f"2. Implements {facts.repo_name}")

        fences = getattr(facts.readme, "install_commands", []) or getattr(facts.readme, "usage_commands", []) if hasattr(facts, "readme") else []
        if fences:
            cleaned = clean_takeaway_line(fences[0], max_words=6)
            takeaways.append(f"3. Run {cleaned}")
        elif hasattr(facts, "readme") and getattr(facts.readme, "features", None):
            cleaned = clean_takeaway_line(facts.readme.features[0], max_words=8)
            takeaways.append(f"3. {cleaned}")
        elif getattr(facts, "cli_flags", None):
            takeaways.append(f"3. Options {', '.join(facts.cli_flags[:2])}")
        else:
            takeaways.append(f"3. Explore {facts.repo_name}")

        # Start with entry_module, top module, top symbol, or readme
        next_file = entry_mod
        if not next_file and hasattr(facts, "ranked_top_modules") and facts.ranked_top_modules:
            next_file = facts.ranked_top_modules[0]
        if not next_file and hasattr(facts, "top_symbols") and facts.top_symbols:
            next_file = facts.top_symbols[0].file
        if not next_file:
            next_file = getattr(facts, "readme_file", "README.md") or "README.md"

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
    from .schema import Evidence
    for scene in script.scenes:
        scene.on_screen = build_scene_visuals(scene.kind, facts)
        if scene.kind == "code" and scene.on_screen and scene.on_screen.metadata:
            target_f = scene.on_screen.metadata.get("file")
            if target_f:
                first_line = scene.on_screen.content.strip().splitlines()[0] if scene.on_screen.content else ""
                scene.evidence = Evidence(file=target_f, quote=first_line)
    return script
