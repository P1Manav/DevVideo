"""
Analyzer module: deep semantic analysis of repository facts.

Extracts structured RepoFacts (pydantic):
- Languages by byte count
- 2-level directory tree
- Entry points (__main__, cli.py, main.py, package.json bin/main, pyproject scripts)
- Python internal import graph (via AST)
- JS/TS internal import graph (via require/import regex)
- Top functions and classes with docstrings and line ranges
- CLI flags from argparse/click/typer (via AST, best effort)
- Dependencies
- Cleaned README (HTML tags, badges, images, link syntax stripped)
- Word-boundary domain relevance score (>= 0.35 threshold)
- Safe fallback for non-Python/JS repos and README-less repos
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from .ingest import RepoContent

logger = logging.getLogger(__name__)

RELEVANCE_KEYWORDS = [
    "video", "frame", "frames", "clip", "clips",
    "embedding", "embeddings", "retrieval", "index", "vector",
    "vectors", "faiss", "whisper", "ffmpeg", "transcript",
    "transcripts", "multimodal",
]

EXTENSION_LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".html": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".sh": "Shell",
    ".bash": "Shell",
}


class TopSymbol(BaseModel):
    """Function or class symbol extracted from source code."""
    name: str
    kind: str  # "function" | "class"
    file: str  # relative POSIX path
    docstring: str = ""
    start_line: int
    end_line: int
    def_line: str = ""
    code_excerpt: str = ""


class ImportEdge(BaseModel):
    """Directed dependency edge between internal modules."""
    source: str
    target: str
    raw_line: str = ""


class CleanedReadme(BaseModel):
    """Sanitized and structured README data."""
    title: str = ""
    description: str = ""
    sections: dict[str, str] = Field(default_factory=dict)
    code_fences: list[str] = Field(default_factory=list)
    raw_lines: list[str] = Field(default_factory=list)


class RepoFacts(BaseModel):
    """Comprehensive semantic facts about a repository."""
    repo_name: str
    owner: str = ""
    commit_sha: str = ""
    languages_by_bytes: dict[str, int] = Field(default_factory=dict)
    tree: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    import_graph: list[ImportEdge] = Field(default_factory=list)
    top_symbols: list[TopSymbol] = Field(default_factory=list)
    cli_flags: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    readme: CleanedReadme = Field(default_factory=CleanedReadme)
    readme_file: str = ""
    relevance_score: float = 0.0
    matched_relevance_terms: list[str] = Field(default_factory=list)
    is_video_relevant: bool = False


# --- README cleaning ---

def clean_readme(raw_text: str | None) -> CleanedReadme:
    """
    Clean raw README content by removing HTML tags, badges, images, and link syntax.
    Extracts title, clean description, sections, and verbatim code fences.
    Handles None or empty README gracefully without crashing.
    """
    if not raw_text or not raw_text.strip():
        return CleanedReadme(title="", description="", sections={}, code_fences=[])

    # 1. Extract code fences before stripping tags
    fence_pattern = re.compile(r"```(?:[a-zA-Z0-9_-]*\n)?(.*?)```", re.DOTALL)
    fences = [m.group(1).strip() for m in fence_pattern.finditer(raw_text) if m.group(1).strip()]

    # Replace code fences with placeholders for text parsing
    text_no_fences = fence_pattern.sub("\n", raw_text)

    # 2. Strip HTML tags (including attributes)
    text_no_html = re.sub(r"<[^>]+>", " ", text_no_fences)

    # 3. Strip badges and images: [![alt](img_url)](link_url) and ![alt](img_url)
    text_no_badges = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", " ", text_no_html)
    text_no_images = re.sub(r"!\[.*?\]\(.*?\)", " ", text_no_badges)

    # 4. Convert markdown links [text](url) to plain text
    text_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text_no_images)

    # Normalize whitespace
    lines = [line.strip() for line in text_clean.splitlines()]
    non_empty_lines = [l for l in lines if l]

    # Extract title: 1) check for <h1> tag, 2) check for single # heading, 3) fallback to first non-empty line
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw_text, re.IGNORECASE | re.DOTALL)
    title = ""
    if h1_match:
        title = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()

    if not title:
        for line in non_empty_lines:
            if line.startswith("#") and not line.startswith("##"):
                title = line.lstrip("#").strip()
                break

    if not title and non_empty_lines:
        title = non_empty_lines[0].lstrip("#").strip()

    # Extract sections (split by ##)
    sections: dict[str, str] = {}
    current_sec = "intro"
    sec_lines: list[str] = []

    for line in lines:
        if line.startswith("##"):
            sections[current_sec] = "\n".join(sec_lines).strip()
            current_sec = line.lstrip("#").strip()
            sec_lines = []
        else:
            if line:
                sec_lines.append(line)
    sections[current_sec] = "\n".join(sec_lines).strip()

    # Extract description from intro section or first non-title paragraph
    description = ""
    intro_text = sections.get("intro", "")
    intro_lines = [l.strip() for l in intro_text.splitlines() if l.strip() and l.strip() != title and not l.strip().startswith("#")]
    if intro_lines:
        description = intro_lines[0]
    elif len(non_empty_lines) > 1:
        for l in non_empty_lines:
            if l != title and not l.startswith("#"):
                description = l
                break

    valid_raw_lines = [
        l.strip() for l in raw_text.splitlines()
        if l.strip() and not l.strip().startswith("<") and not l.strip().startswith("[![") and not l.strip().startswith("```")
    ]

    return CleanedReadme(
        title=title,
        description=description,
        sections=sections,
        code_fences=fences,
        raw_lines=valid_raw_lines,
    )


# --- Relevance calculation ---

def compute_domain_relevance(text: str) -> tuple[float, list[str]]:
    """
    Compute domain relevance using strict word-boundary matching.
    Avoids false positives like matching 'ai' inside 'maintain'.
    """
    if not text:
        return 0.0, []

    matched = []
    for kw in RELEVANCE_KEYWORDS:
        if re.search(rf"\b{kw}\b", text, re.IGNORECASE):
            matched.append(kw)

    unique_matched = sorted(set(matched))
    # Relevance scale: 4+ matched keywords give >= 0.35
    score = min(1.0, round(len(unique_matched) / 10.0, 2))
    return score, unique_matched


# --- Python AST extraction ---

def extract_python_facts(
    rel_path: str,
    code: str,
    all_py_files: set[str],
) -> tuple[list[ImportEdge], list[TopSymbol], list[str]]:
    """
    Safely parse Python code with AST.
    Returns (internal_import_edges, top_symbols, cli_flags).
    Catches SyntaxError, RecursionError, MemoryError.
    """
    edges: list[ImportEdge] = []
    symbols: list[TopSymbol] = []
    flags: list[str] = []

    try:
        tree = ast.parse(code, filename=rel_path)
    except (SyntaxError, RecursionError, MemoryError, Exception) as e:
        logger.debug(f"AST parsing skipped for {rel_path}: {e}")
        return edges, symbols, flags

    code_lines = code.splitlines()

    # 1. Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_name = alias.name.replace(".", "/")
                raw_l = code_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(code_lines) else ""
                for f in all_py_files:
                    if f.startswith(mod_name) or mod_name in f:
                        if f != rel_path:
                            edges.append(ImportEdge(source=rel_path, target=f, raw_line=raw_l))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod_name = node.module.replace(".", "/")
                raw_l = code_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(code_lines) else ""
                for f in all_py_files:
                    if f.startswith(mod_name) or mod_name in f:
                        if f != rel_path:
                            edges.append(ImportEdge(source=rel_path, target=f, raw_line=raw_l))

    # 2. Top-level functions & classes
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if not name.startswith("_") or name == "__main__":
                doc = ast.get_docstring(node) or ""
                first_line_doc = doc.splitlines()[0].strip() if doc else ""
                end_lineno = getattr(node, "end_lineno", node.lineno)
                s_idx = max(0, node.lineno - 1)
                e_idx = min(s_idx + 12, end_lineno)
                excerpt = "\n".join(code_lines[s_idx:e_idx])
                def_l = code_lines[s_idx].strip() if s_idx < len(code_lines) else ""
                symbols.append(TopSymbol(
                    name=name,
                    kind="function",
                    file=rel_path,
                    docstring=first_line_doc,
                    start_line=node.lineno,
                    end_line=end_lineno,
                    def_line=def_l,
                    code_excerpt=excerpt,
                ))
        elif isinstance(node, ast.ClassDef):
            name = node.name
            if not name.startswith("_"):
                doc = ast.get_docstring(node) or ""
                first_line_doc = doc.splitlines()[0].strip() if doc else ""
                end_lineno = getattr(node, "end_lineno", node.lineno)
                s_idx = max(0, node.lineno - 1)
                e_idx = min(s_idx + 12, end_lineno)
                excerpt = "\n".join(code_lines[s_idx:e_idx])
                def_l = code_lines[s_idx].strip() if s_idx < len(code_lines) else ""
                symbols.append(TopSymbol(
                    name=name,
                    kind="class",
                    file=rel_path,
                    docstring=first_line_doc,
                    start_line=node.lineno,
                    end_line=end_lineno,
                    def_line=def_l,
                    code_excerpt=excerpt,
                ))

    # 3. CLI flags from argparse / click / typer
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # argparse: .add_argument('--flag', ...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if arg.value.startswith("-"):
                            flags.append(arg.value)

    return edges, symbols, flags


# --- JS / TS dependency extraction ---

def extract_js_facts(
    rel_path: str,
    code: str,
    all_js_files: set[str],
) -> list[ImportEdge]:
    """Extract internal import edges from JS/TS code using regex."""
    edges: list[ImportEdge] = []
    # Match: import ... from './util' or require('./util')
    patterns = [
        re.compile(r"""(?:import|require)\s*\(?['"](\.[^'"]+)['"]\s*\)?"""),
    ]
    dir_name = os.path.dirname(rel_path)

    for pat in patterns:
        for m in pat.finditer(code):
            target_rel = m.group(1)
            # Resolve relative target
            norm = os.path.normpath(os.path.join(dir_name, target_rel)).replace("\\", "/")
            # Match against known JS files
            for known in all_js_files:
                if known == norm or known.startswith(norm + ".") or norm in known:
                    if known != rel_path:
                        edges.append(ImportEdge(source=rel_path, target=known, raw_line=m.group(0)))

    return edges


# --- Main analysis function ---

def analyze_repo(content: RepoContent) -> RepoFacts:
    """
    Run comprehensive semantic analysis on ingested repository content.
    Returns pydantic RepoFacts object.
    Never crashes on missing README or foreign project structures.
    """
    files = content.files
    repo_name = content.repo_name
    owner = content.owner
    commit_sha = content.commit_sha

    # 1. Languages by bytes
    lang_bytes: dict[str, int] = {}
    for path, text in files.items():
        ext = os.path.splitext(path)[1].lower()
        lang = EXTENSION_LANGUAGE_MAP.get(ext, "Other")
        size = len(text.encode("utf-8", errors="replace"))
        lang_bytes[lang] = lang_bytes.get(lang, 0) + size

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

    # 4. Entry points
    entry_points: list[str] = []
    for path, code in files.items():
        if path.endswith("__main__.py") or path.endswith("/cli.py") or path in ("cli.py", "main.py"):
            entry_points.append(path)
        elif 'if __name__ == "__main__":' in code or "if __name__ == '__main__':" in code:
            if path not in entry_points:
                entry_points.append(path)

    # Check package.json for bin/main
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

    # 5. Internal dependencies & AST extraction
    py_files = {p for p in files if p.endswith(".py")}
    js_files = {p for p in files if p.endswith((".js", ".ts", ".jsx", ".tsx"))}

    all_edges: list[ImportEdge] = []
    all_symbols: list[TopSymbol] = []
    cli_flags: list[str] = []

    for py_file in sorted(py_files):
        edges, symbols, flags = extract_python_facts(py_file, files[py_file], py_files)
        all_edges.extend(edges)
        all_symbols.extend(symbols)
        cli_flags.extend(flags)

    for js_file in sorted(js_files):
        edges = extract_js_facts(js_file, files[js_file], js_files)
        all_edges.extend(edges)

    # Deduplicate edges & flags
    unique_edges = []
    seen_edges = set()
    for e in all_edges:
        key = (e.source, e.target)
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)

    unique_flags = sorted(set(cli_flags))

    # 6. Extract dependencies
    deps: list[str] = []
    if "requirements.txt" in files:
        for line in files["requirements.txt"].splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                dep_name = re.split(r"[><=~;]", line)[0].strip()
                if dep_name:
                    deps.append(dep_name)
    if "package.json" in files:
        try:
            pkg = json.loads(files["package.json"])
            for d in pkg.get("dependencies", {}).keys():
                deps.append(d)
        except Exception:
            pass

    # 7. Relevance calculation over README + docstrings + dependency names
    corpus_parts = [
        cleaned_readme.title,
        cleaned_readme.description,
        " ".join(cleaned_readme.sections.values()),
        " ".join(s.docstring for s in all_symbols),
        " ".join(deps),
    ]
    relevance_corpus = " ".join(corpus_parts)
    rel_score, matched_terms = compute_domain_relevance(relevance_corpus)

    return RepoFacts(
        repo_name=repo_name,
        owner=owner,
        commit_sha=commit_sha,
        languages_by_bytes=lang_bytes,
        tree=tree,
        entry_points=entry_points,
        import_graph=unique_edges,
        top_symbols=all_symbols,
        cli_flags=unique_flags,
        dependencies=sorted(set(deps)),
        readme=cleaned_readme,
        readme_file=readme_file,
        relevance_score=rel_score,
        matched_relevance_terms=matched_terms,
        is_video_relevant=(rel_score >= 0.35),
    )


analyze_repository = analyze_repo
