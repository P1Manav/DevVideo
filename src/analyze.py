"""
Analyzer module: deep semantic analysis of repository facts.

Extracts structured RepoFacts (pydantic):
- Languages by byte count
- 2-level directory tree
- Entry module & ranked top modules by centrality in import graph
- Entry points (__main__, cli.py, main.py, package.json bin/main, pyproject scripts)
- Python internal import graph (via AST) with call sequences
- JS/TS internal import graph (via require/import regex)
- Top functions and classes with docstrings, line ranges, and call sequences
- Module docstrings with line spans
- CLI flags with their help= strings (argparse/click/typer via AST)
- Dependencies with mapped roles (faiss->vector index, ffmpeg->video decoding, etc.)
- Pipeline stages mapped to concrete evidence lines
- Cleaned README: tagline, description sentences with line spans, features, sections
- Word-boundary domain relevance score (>= 0.35 threshold)
- Safe fallback for non-Python/JS repos and README-less repos (never crashes)
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
from .schema import SourceSpan

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

DEPENDENCY_ROLES = {
    "faiss": "vector index",
    "faiss-cpu": "vector index",
    "faiss-gpu": "vector index",
    "ffmpeg": "video decoding",
    "ffmpeg-python": "video decoding",
    "opencv-python": "frame processing",
    "opencv": "frame processing",
    "cv2": "frame processing",
    "torch": "neural network",
    "torchvision": "computer vision",
    "torchaudio": "audio processing",
    "transformers": "embeddings",
    "clip": "embeddings",
    "whisper": "speech transcription",
    "openai-whisper": "speech transcription",
    "numpy": "array math",
    "scipy": "scientific computing",
    "flask": "web API",
    "fastapi": "web API",
    "pytest": "tests",
    "pillow": "image processing",
    "pil": "image processing",
    "tqdm": "progress bars",
    "playwright": "browser automation",
    "pydantic": "data validation",
}

STAGE_KEYWORDS = {
    "decode": ["ffmpeg", "frame", "frames", "clip", "clips", "decode", "opencv", "cv2"],
    "embed": ["embed", "embedding", "embeddings", "clip", "torch", "vector", "vectors", "representation"],
    "index": ["faiss", "index", "indexing"],
    "query": ["query", "search", "retrieval", "retrieve"],
    "transcribe": ["whisper", "transcript", "transcription", "speech"],
    "serve": ["fastapi", "flask", "serve", "api", "cli"],
}


class ReadmeSentence(BaseModel):
    """Cleaned sentence from README with source line span."""
    text: str
    start_line: int
    end_line: int


class CleanedReadme(BaseModel):
    """Sanitized and structured README data."""
    title: str = ""
    tagline: str = ""
    description: str = ""
    description_sentences: list[ReadmeSentence] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    sections: dict[str, str] = Field(default_factory=dict)
    code_fences: list[str] = Field(default_factory=list)
    raw_lines: list[str] = Field(default_factory=list)


class CliFlag(BaseModel):
    """CLI flag with its help documentation."""
    flag: str
    help: str = ""


class TopSymbol(BaseModel):
    """Function or class symbol extracted from source code."""
    name: str
    kind: str  # "function" | "class"
    file: str  # relative POSIX path
    docstring: str = ""
    docstring_span: SourceSpan | None = None
    start_line: int
    end_line: int
    def_line: str = ""
    code_excerpt: str = ""
    calls: list[str] = Field(default_factory=list)


class ModuleDocstring(BaseModel):
    """Top-level module docstring with source span."""
    file: str
    docstring: str
    span: SourceSpan


class ImportEdge(BaseModel):
    """Directed dependency edge between internal modules."""
    source: str
    target: str
    raw_line: str = ""


class RepoFacts(BaseModel):
    """Comprehensive semantic facts about a repository."""
    repo_name: str
    owner: str | None = None
    commit_sha: str = ""
    languages_by_bytes: dict[str, int] = Field(default_factory=dict)
    tree: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    entry_module: str = ""
    ranked_top_modules: list[str] = Field(default_factory=list)
    import_graph: list[ImportEdge] = Field(default_factory=list)
    top_symbols: list[TopSymbol] = Field(default_factory=list)
    module_docstrings: list[ModuleDocstring] = Field(default_factory=list)
    cli_flags: list[str] = Field(default_factory=list)
    cli_flag_details: list[CliFlag] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    dependency_roles: dict[str, str] = Field(default_factory=dict)
    pipeline_stages: dict[str, str] = Field(default_factory=dict)
    readme: CleanedReadme = Field(default_factory=CleanedReadme)
    readme_file: str = ""
    relevance_score: float = 0.0
    matched_relevance_terms: list[str] = Field(default_factory=list)
    is_video_relevant: bool = False


# --- README cleaning ---

def is_prose_line(line: str) -> bool:
    """
    Check if a line is genuine prose according to the rules:
    - Skip: badges, link-only rows, HTML, images, headings, tables, code fences.
    - Must have >= 8 words and >= 60% non-link text.
    """
    s = line.strip()
    if not s:
        return False
    if s.startswith("#") or s.startswith("```") or s.startswith("|") or s.startswith("<") or s.startswith("!["):
        return False
    if re.search(r"\[!\[.*?\]\(.*?\)\]", s):  # badge
        return False

    # Check non-link ratio
    non_link = re.sub(r"\[([^\]]+)\]\([^)]+\)", "", s)
    if len(s) == 0:
        return False
    ratio = len(non_link.strip()) / float(len(s))
    if ratio < 0.60:
        return False

    # Words check
    words = s.split()
    return len(words) >= 8


def clean_readme(raw_text: str | None) -> CleanedReadme:
    """
    Clean raw README content by removing HTML tags, badges, images, and link syntax.
    Extracts title, tagline, description_sentences with spans, features, sections, and code fences.
    Handles None or empty README gracefully without crashing.
    """
    if not raw_text or not raw_text.strip():
        return CleanedReadme(
            title="",
            tagline="",
            description="",
            description_sentences=[],
            features=[],
            sections={},
            code_fences=[],
            raw_lines=[],
        )

    # 1. Extract code fences before stripping tags
    fence_pattern = re.compile(r"```(?:[a-zA-Z0-9_-]*\n)?(.*?)```", re.DOTALL)
    fences = [m.group(1).strip() for m in fence_pattern.finditer(raw_text) if m.group(1).strip()]

    raw_lines = raw_text.splitlines()

    # 2. Extract title: check <h1> tag, single # heading, or first non-empty line
    title = ""
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw_text, re.IGNORECASE | re.DOTALL)
    if h1_match:
        title = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()

    if not title:
        for line in raw_lines:
            s = line.strip()
            if s.startswith("#") and not s.startswith("##"):
                title = s.lstrip("#").strip()
                break

    if not title:
        for line in raw_lines:
            s = line.strip()
            if s and not s.startswith("<") and not s.startswith("[!["):
                title = s.lstrip("#").strip()
                break

    # 3. Extract sections & bullet features & prose description sentences
    sections: dict[str, str] = {}
    current_sec = "intro"
    sec_lines: list[str] = []
    features: list[str] = []
    description_sentences: list[ReadmeSentence] = []
    tagline = ""

    for line_idx, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        # Section header
        if line.startswith("##"):
            sections[current_sec] = "\n".join(sec_lines).strip()
            current_sec = line.lstrip("#").strip()
            sec_lines = []
            continue

        # Strip HTML and badges for section storage
        line_no_html = re.sub(r"<[^>]+>", "", line).strip()
        line_no_badges = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", line_no_html).strip()
        if line_no_badges:
            sec_lines.append(line_no_badges)

        # Bullet features
        bullet_m = re.match(r"^[-*+]\s+(.*)", line) or re.match(r"^\d+\.\s+(.*)", line)
        if bullet_m:
            item = bullet_m.group(1).strip()
            item_clean = re.sub(r"<[^>]+>", "", item)
            item_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", item_clean)
            item_clean = re.sub(r"[`*]", "", item_clean).strip()
            if len(item_clean.split()) >= 3 and not item_clean.startswith("http"):
                features.append(item_clean)

        # Check for prose line according to prose picker rules
        if is_prose_line(line):
            prose_clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
            prose_clean = re.sub(r"<[^>]+>", "", prose_clean)
            prose_clean = re.sub(r"[`*]", "", prose_clean).strip()

            raw_sents = re.split(r"(?<=[.!?])\s+", prose_clean)
            for sent in raw_sents:
                sent_clean = sent.strip()
                if len(sent_clean.split()) >= 6:
                    rs = ReadmeSentence(text=sent_clean, start_line=line_idx, end_line=line_idx)
                    description_sentences.append(rs)
                    if not tagline:
                        tagline = sent_clean

    sections[current_sec] = "\n".join(sec_lines).strip()

    # Description is tagline or first prose sentence or clean intro line
    description = tagline
    if not description and description_sentences:
        description = description_sentences[0].text
    if not description:
        intro_text = sections.get("intro", "")
        intro_lines = [
            l.strip() for l in intro_text.splitlines()
            if l.strip() and l.strip() != title and not l.strip().startswith("#") and not l.strip().startswith("<")
        ]
        if intro_lines:
            description = intro_lines[0]



    valid_raw_lines = [
        l.strip() for l in raw_lines
        if l.strip() and not l.strip().startswith("<") and not l.strip().startswith("[![") and not l.strip().startswith("```")
    ]

    return CleanedReadme(
        title=title,
        tagline=tagline,
        description=description,
        description_sentences=description_sentences,
        features=features,
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
    score = min(1.0, round(len(unique_matched) / 10.0, 2))
    return score, unique_matched


# --- Python AST extraction ---

class FunctionCallVisitor(ast.NodeVisitor):
    """Collects names of functions called inside a function in order."""
    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self.calls.append(node.func.attr)
        self.generic_visit(node)


def extract_python_facts(
    rel_path: str,
    code: str,
    all_py_files: set[str],
) -> tuple[list[ImportEdge], list[TopSymbol], list[str], list[CliFlag], ModuleDocstring | None]:
    """
    Safely parse Python code with AST.
    Returns (edges, symbols, flag_strings, cli_flag_details, module_docstring).
    """
    edges: list[ImportEdge] = []
    symbols: list[TopSymbol] = []
    flags: list[str] = []
    cli_flags_details: list[CliFlag] = []
    module_doc: ModuleDocstring | None = None

    try:
        tree = ast.parse(code, filename=rel_path)
    except (SyntaxError, RecursionError, MemoryError, Exception) as e:
        logger.debug(f"AST parsing skipped for {rel_path}: {e}")
        return edges, symbols, flags, cli_flags_details, module_doc

    code_lines = code.splitlines()

    # Module docstring
    raw_mod_doc = ast.get_docstring(tree) or ""
    if raw_mod_doc:
        first_s = raw_mod_doc.splitlines()[0].strip()
        module_doc = ModuleDocstring(
            file=rel_path,
            docstring=first_s,
            span=SourceSpan(file=rel_path, start_line=1, end_line=min(5, len(code_lines)), text=first_s),
        )

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
                e_idx = min(s_idx + 14, end_lineno)
                excerpt = "\n".join(code_lines[s_idx:e_idx])
                def_l = code_lines[s_idx].strip() if s_idx < len(code_lines) else ""

                # Function calls in order
                c_vis = FunctionCallVisitor()
                c_vis.visit(node)

                doc_span = None
                if first_line_doc:
                    doc_span = SourceSpan(
                        file=rel_path,
                        start_line=node.lineno,
                        end_line=min(node.lineno + 4, end_lineno),
                        text=first_line_doc,
                    )

                symbols.append(TopSymbol(
                    name=name,
                    kind="function",
                    file=rel_path,
                    docstring=first_line_doc,
                    docstring_span=doc_span,
                    start_line=node.lineno,
                    end_line=end_lineno,
                    def_line=def_l,
                    code_excerpt=excerpt,
                    calls=c_vis.calls,
                ))
        elif isinstance(node, ast.ClassDef):
            name = node.name
            if not name.startswith("_"):
                doc = ast.get_docstring(node) or ""
                first_line_doc = doc.splitlines()[0].strip() if doc else ""
                end_lineno = getattr(node, "end_lineno", node.lineno)
                s_idx = max(0, node.lineno - 1)
                e_idx = min(s_idx + 14, end_lineno)
                excerpt = "\n".join(code_lines[s_idx:e_idx])
                def_l = code_lines[s_idx].strip() if s_idx < len(code_lines) else ""

                doc_span = None
                if first_line_doc:
                    doc_span = SourceSpan(
                        file=rel_path,
                        start_line=node.lineno,
                        end_line=min(node.lineno + 4, end_lineno),
                        text=first_line_doc,
                    )

                symbols.append(TopSymbol(
                    name=name,
                    kind="class",
                    file=rel_path,
                    docstring=first_line_doc,
                    docstring_span=doc_span,
                    start_line=node.lineno,
                    end_line=end_lineno,
                    def_line=def_l,
                    code_excerpt=excerpt,
                    calls=[],
                ))

    # 3. CLI flags with help strings
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # argparse: .add_argument('-q', '--query', ..., help="...")
            if isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
                flag_names = []
                help_text = ""
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if arg.value.startswith("-"):
                            flag_names.append(arg.value)
                for kw in node.keywords:
                    if kw.arg == "help" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        help_text = kw.value.value
                for fn in flag_names:
                    flags.append(fn)
                    cli_flags_details.append(CliFlag(flag=fn, help=help_text))

    return edges, symbols, flags, cli_flags_details, module_doc


# --- JS / TS dependency extraction ---

def extract_js_facts(
    rel_path: str,
    code: str,
    all_js_files: set[str],
) -> list[ImportEdge]:
    """Extract internal import edges from JS/TS code using regex."""
    edges: list[ImportEdge] = []
    patterns = [
        re.compile(r"""(?:import|require)\s*\(?['"](\.[^'"]+)['"]\s*\)?"""),
    ]
    dir_name = os.path.dirname(rel_path)

    for pat in patterns:
        for m in pat.finditer(code):
            target_rel = m.group(1)
            norm = os.path.normpath(os.path.join(dir_name, target_rel)).replace("\\", "/")
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
    raw_owner = content.owner
    commit_sha = content.commit_sha

    # Owner is None for local paths
    owner = None if raw_owner in ("local", "None", "", None) else raw_owner

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

    # Entry module selection
    entry_module = ""
    for ep in entry_points:
        if ep.endswith("__main__.py") or ep.endswith("cli.py") or ep == "main.py":
            entry_module = ep
            break
    if not entry_module and entry_points:
        entry_module = entry_points[0]

    # 5. Internal dependencies & AST extraction
    py_files = {p for p in files if p.endswith(".py")}
    js_files = {p for p in files if p.endswith((".js", ".ts", ".jsx", ".tsx"))}

    all_edges: list[ImportEdge] = []
    all_symbols: list[TopSymbol] = []
    all_flags: list[str] = []
    cli_flags_details: list[CliFlag] = []
    module_docs: list[ModuleDocstring] = []

    for py_file in sorted(py_files):
        edges, symbols, flags, flag_details, m_doc = extract_python_facts(py_file, files[py_file], py_files)
        all_edges.extend(edges)
        all_symbols.extend(symbols)
        all_flags.extend(flags)
        cli_flags_details.extend(flag_details)
        if m_doc:
            module_docs.append(m_doc)

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

    unique_flags = sorted(set(all_flags))

    # Graph centrality ranking for top modules
    degrees: dict[str, int] = {}
    for e in unique_edges:
        degrees[e.source] = degrees.get(e.source, 0) + 1
        degrees[e.target] = degrees.get(e.target, 0) + 1

    sorted_by_degree = [mod for mod, _ in sorted(degrees.items(), key=lambda kv: kv[1], reverse=True)]

    # Make sure entry_module is first if present
    ranked_top_modules: list[str] = []
    if entry_module:
        ranked_top_modules.append(entry_module)
    for m in sorted_by_degree:
        if m not in ranked_top_modules:
            ranked_top_modules.append(m)

    # If still empty, add any py_files
    if not ranked_top_modules:
        ranked_top_modules = sorted(py_files)[:8]
    else:
        ranked_top_modules = ranked_top_modules[:8]

    # 6. Extract dependencies & mapped roles
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

    unique_deps = sorted(set(deps))
    dependency_roles: dict[str, str] = {}
    for d in unique_deps:
        d_clean = re.split(r"[><=~;]", d)[0].strip().lower()
        if d_clean in DEPENDENCY_ROLES:
            dependency_roles[d] = DEPENDENCY_ROLES[d_clean]

    # 7. Map pipeline stages with concrete evidence lines
    pipeline_stages: dict[str, str] = {}
    all_searchable_lines = list(cleaned_readme.raw_lines)
    for fpath in sorted(py_files):
        all_searchable_lines.extend(files[fpath].splitlines()[:50])

    for stage, keywords in STAGE_KEYWORDS.items():
        for line in all_searchable_lines:
            s_line = line.strip()
            if not s_line or s_line.startswith("#") or s_line.startswith("```"):
                continue
            # Check if any keyword appears as word
            if any(re.search(rf"\b{kw}\b", s_line, re.IGNORECASE) for kw in keywords):
                pipeline_stages[stage] = s_line[:120]
                break

    # 8. Relevance calculation over README + docstrings + dependency names
    corpus_parts = [
        cleaned_readme.title,
        cleaned_readme.tagline,
        cleaned_readme.description,
        " ".join(cleaned_readme.sections.values()),
        " ".join(s.docstring for s in all_symbols),
        " ".join(unique_deps),
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
        entry_module=entry_module,
        ranked_top_modules=ranked_top_modules,
        import_graph=unique_edges,
        top_symbols=all_symbols,
        module_docstrings=module_docs,
        cli_flags=unique_flags,
        cli_flag_details=cli_flags_details,
        dependencies=unique_deps,
        dependency_roles=dependency_roles,
        pipeline_stages=pipeline_stages,
        readme=cleaned_readme,
        readme_file=readme_file,
        relevance_score=rel_score,
        matched_relevance_terms=matched_terms,
        is_video_relevant=(rel_score >= 0.35),
    )


analyze_repository = analyze_repo
