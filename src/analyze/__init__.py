"""
Analyzer package: semantic fact extraction for developer video explainer generation.
Re-exports all models and functions for backward compatibility.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re

from ..ingest import RepoContent
from .languages import compute_languages_by_bytes, is_vendored_or_generated_path
from .models import (
    DEPENDENCY_ROLES,
    EXTENSION_LANGUAGE_MAP,
    RELEVANCE_KEYWORDS,
    STAGE_KEYWORDS,
    CleanedReadme,
    CliFlag,
    ImportEdge,
    ModuleDocstring,
    ReadmeSentence,
    RepoFacts,
    TopSymbol,
)
from .python_ast import FunctionCallVisitor, extract_python_facts
from .js_graph import extract_js_facts
from .readme import clean_readme, find_exact_line_range, is_prose_line, is_valid_shell_command
from .relevance import compute_domain_relevance, extract_pipeline_stages

logger = logging.getLogger(__name__)


def is_auxiliary_or_test_path(path: str) -> bool:
    """R5: Exclude tests/, test_*.py, examples/, docs/, setup.py, conftest.py, benchmarks/, scripts/."""
    p = path.lower().replace("\\", "/")
    parts = p.split("/")
    filename = parts[-1]
    aux_dirs = {"tests", "test", "examples", "example", "docs", "doc", "benchmarks", "benchmark", "scripts", "script"}
    if any(part in aux_dirs for part in parts[:-1]):
        return True
    if filename.startswith("test_") or filename.endswith("_test.py") or filename in ("setup.py", "conftest.py", "__init__.py", "__main__.py"):
        return True
    return False


def analyze_repo(content: RepoContent) -> RepoFacts:
    """
    Produce comprehensive RepoFacts from ingested repository content.
    Never crashes on missing or unconventional files.
    """
    files = content.files
    repo_name = content.repo_name
    raw_owner = content.owner
    commit_sha = content.commit_sha

    owner = None if raw_owner in ("local", "None", "", None) else raw_owner

    # 1. Languages by bytes (T2: first-party code only)
    lang_bytes = compute_languages_by_bytes(files)

    # 2. 2-level directory tree
    tree_set: set[str] = set()
    for path in sorted(files.keys()):
        parts = path.split("/")
        if len(parts) == 1:
            tree_set.add(parts[0])
        elif len(parts) == 2:
            tree_set.add(f"{parts[0]}/")
            tree_set.add(path)
        else:
            tree_set.add(f"{parts[0]}/")
            tree_set.add(f"{parts[0]}/{parts[1]}/")
    tree = sorted(tree_set)

    # 3. Clean README
    readme_content = ""
    readme_file = ""
    for name in ("README.md", "readme.md", "README.rst", "README.txt"):
        if name in files:
            readme_content = files[name]
            readme_file = name
            break
    cleaned_readme = clean_readme(readme_content)

    # 4. AST and code symbol analysis
    all_py = {f for f in files.keys() if f.endswith(".py")}
    all_js = {f for f in files.keys() if f.endswith((".js", ".jsx", ".ts", ".tsx"))}

    import_graph: list[ImportEdge] = []
    top_symbols: list[TopSymbol] = []
    cli_flags: list[str] = []
    cli_flag_details: list[CliFlag] = []
    module_docstrings: list[ModuleDocstring] = []

    for fpath in sorted(all_py):
        code = files[fpath]
        edges, syms, flags, fl_details, m_doc = extract_python_facts(fpath, code, all_py)
        import_graph.extend(edges)
        top_symbols.extend(syms)
        cli_flags.extend(flags)
        cli_flag_details.extend(fl_details)
        if m_doc:
            module_docstrings.append(m_doc)

    for fpath in sorted(all_js):
        code = files[fpath]
        edges, syms = extract_js_facts(fpath, code, all_js)
        import_graph.extend(edges)
        top_symbols.extend(syms)

    # Centrality ranking of modules
    in_degrees: dict[str, int] = {}
    for edge in import_graph:
        in_degrees[edge.target] = in_degrees.get(edge.target, 0) + 1
    ranked_modules = [mod for mod, _ in sorted(in_degrees.items(), key=lambda kv: (-kv[1], kv[0]))]

    # Fallback to non-test code files if graph is sparse
    if not ranked_modules:
        core_code = [f for f in files.keys() if f.endswith((".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp")) and not is_auxiliary_or_test_path(f)]
        ranked_modules = sorted(core_code)

    # 5. Entry point detection (T8: packages/cli/main first, never examples/tests)
    entry_points: list[str] = []
    for path, code in files.items():
        if path.endswith("__main__.py") or path.endswith("/cli.py") or path in ("cli.py", "main.py"):
            entry_points.append(path)
        elif 'if __name__ == "__main__":' in code or "if __name__ == '__main__':" in code:
            if path not in entry_points:
                entry_points.append(path)

    if "package.json" in files:
        try:
            pkg = json.loads(files["package.json"])
            if "bin" in pkg:
                if isinstance(pkg["bin"], str):
                    entry_points.append(pkg["bin"].replace("./", ""))
                elif isinstance(pkg["bin"], dict):
                    for b in pkg["bin"].values():
                        entry_points.append(str(b).replace("./", ""))
            if "main" in pkg:
                entry_points.append(str(pkg["main"]).replace("./", ""))
        except Exception:
            pass

    for se in ("src/index.js", "src/App.js", "src/main.js", "src/main.py", "bin/main.js"):
        if se in files and se not in entry_points:
            entry_points.append(se)

    entry_module = ""
    # T8: Entry module must never be from examples/ or tests/ if core package code exists
    valid_eps = [ep for ep in entry_points if not is_auxiliary_or_test_path(ep)]
    search_eps = valid_eps if valid_eps else entry_points

    for ep in search_eps:
        if ep.endswith("__main__.py") or ep.endswith("cli.py") or ep == "main.py":
            entry_module = ep
            break
    if not entry_module and search_eps:
        entry_module = search_eps[0]

    if not entry_module and ranked_modules:
        core_ranked = [m for m in ranked_modules if not is_auxiliary_or_test_path(m)]
        entry_module = core_ranked[0] if core_ranked else ranked_modules[0]

    ranked_top_modules: list[str] = []
    if entry_module and not is_auxiliary_or_test_path(entry_module):
        ranked_top_modules.append(entry_module)
    for m in ranked_modules:
        if m not in ranked_top_modules:
            ranked_top_modules.append(m)

    # 6. Dependencies & Roles
    deps: list[str] = []
    dep_roles: dict[str, str] = {}
    if "requirements.txt" in files:
        for line in files["requirements.txt"].splitlines():
            line = line.strip().split("#")[0].split(";")[0].strip()
            if line and not line.startswith("-"):
                name = re.split(r"[=<>~]", line)[0].strip().lower()
                if name:
                    deps.append(name)
    if "package.json" in files:
        try:
            pj = json.loads(files["package.json"])
            deps.extend([k.lower() for k in pj.get("dependencies", {}).keys()])
        except Exception:
            pass

    for d in deps:
        if d in DEPENDENCY_ROLES:
            dep_roles[d] = DEPENDENCY_ROLES[d]

    # 7. Pipeline stages (Phase 2 & 6)
    pipeline_stages, pipeline_stage_spans = extract_pipeline_stages(
        cleaned_readme, top_symbols, module_docstrings, readme_file
    )

    # 8. Domain relevance score
    corpus_parts = [
        repo_name,
        cleaned_readme.title,
        cleaned_readme.tagline,
        cleaned_readme.description,
        " ".join(cleaned_readme.sections.values()),
        " ".join(s.docstring for s in top_symbols),
        " ".join(deps),
    ]
    combined_text = " ".join(corpus_parts)
    rel_score, rel_terms = compute_domain_relevance(combined_text)
    is_video_relevant = rel_score >= 0.30

    return RepoFacts(
        repo_name=repo_name,
        owner=owner,
        commit_sha=commit_sha,
        languages_by_bytes=lang_bytes,
        tree=tree,
        entry_points=entry_points,
        entry_module=entry_module,
        ranked_top_modules=ranked_top_modules,
        import_graph=import_graph,
        top_symbols=top_symbols,
        module_docstrings=module_docstrings,
        cli_flags=cli_flags,
        cli_flag_details=cli_flag_details,
        dependencies=deps,
        dependency_roles=dep_roles,
        pipeline_stages=pipeline_stages,
        pipeline_stage_spans=pipeline_stage_spans,
        readme=cleaned_readme,
        readme_file=readme_file,
        relevance_score=rel_score,
        matched_relevance_terms=rel_terms,
        is_video_relevant=is_video_relevant,
    )


analyze_repository = analyze_repo
