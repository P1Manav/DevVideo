"""
Python AST inspection routines.
Implements Rule T5 (meaningful call filtering) and Rule T6 (skips trivial wrappers, key code selection).
"""
from __future__ import annotations

import ast
import logging
from ..schema import SourceSpan
from .models import CliFlag, ImportEdge, ModuleDocstring, TopSymbol

logger = logging.getLogger(__name__)

STDLIB_OR_TRIVIAL_CALLS = {
    "open", "print", "len", "str", "list", "dict", "set", "tuple", "int", "float",
    "range", "keys", "values", "items", "append", "extend", "get", "strip", "split",
    "replace", "join", "format", "startswith", "endswith", "lower", "upper",
    "dirname", "basename", "abspath", "realpath", "exists", "isdir", "isfile",
    "mkdir", "remove", "unlink", "chmod", "close", "read", "write", "loads", "dumps",
    "load", "dump", "any", "all", "min", "max", "sum", "zip", "enumerate",
    "isinstance", "issubclass", "hasattr", "getattr", "setattr", "type",
    "expanduser", "is_available", "cuda", "cpu", "device", "super",
}


def is_meaningful_call(call_name: str) -> bool:
    """T5: Filter calls to project functions or meaningful libraries; skip stdlib and is_* predicates."""
    c = call_name.strip()
    if not c or c.startswith("_"):
        return False
    if c.startswith("is_") or c.startswith("has_") or c.startswith("to_"):
        return False
    if c.lower() in STDLIB_OR_TRIVIAL_CALLS:
        return False
    return True


class FunctionCallVisitor(ast.NodeVisitor):
    """Collects names of meaningful calls inside a function in order."""
    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        call_name = ""
        if isinstance(node.func, ast.Name):
            call_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            call_name = node.func.attr

        if call_name and is_meaningful_call(call_name):
            if call_name not in self.calls:
                self.calls.append(call_name)

        self.generic_visit(node)


def is_trivial_wrapper(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    T6: Detect trivial wrappers (<= 3 statements and no branching/loops/exceptions).
    e.g. `def available_models(): return list(_MODELS.keys())`
    """
    body = [n for n in node.body if not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Constant)]
    if len(body) > 3:
        return False

    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.IfExp, ast.For, ast.While, ast.Try, ast.Match)):
            return False

    return True


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
    except Exception as e:
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
    else:
        for l_idx, l_str in enumerate(code_lines, start=1):
            s_str = l_str.strip()
            if s_str and not s_str.startswith("#"):
                module_doc = ModuleDocstring(
                    file=rel_path,
                    docstring="",
                    span=SourceSpan(file=rel_path, start_line=l_idx, end_line=l_idx, text=s_str),
                )
                break

    # 1. Imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_name = alias.name.replace(".", "/")
                raw_l = code_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(code_lines) else ""
                for f in sorted(all_py_files):
                    if (f.startswith(mod_name) or mod_name in f) and f != rel_path:
                        edges.append(ImportEdge(source=rel_path, target=f, raw_line=raw_l, line_number=node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod_name = node.module.replace(".", "/")
                raw_l = code_lines[node.lineno - 1].strip() if 0 <= node.lineno - 1 < len(code_lines) else ""
                for f in sorted(all_py_files):
                    if (f.startswith(mod_name) or mod_name in f) and f != rel_path:
                        edges.append(ImportEdge(source=rel_path, target=f, raw_line=raw_l, line_number=node.lineno))

    # 2. Top-level functions & classes
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if not name.startswith("_") or name == "__main__":
                doc = ast.get_docstring(node) or ""
                first_line_doc = doc.splitlines()[0].strip() if doc else ""
                end_lineno = getattr(node, "end_lineno", node.lineno)
                s_idx = max(0, node.lineno - 1)
                # Skip docstring in excerpt to show function body logic
                doc_node = (
                    node.body[0]
                    if (node.body and isinstance(node.body[0], ast.Expr) and isinstance(getattr(node.body[0], "value", None), (ast.Constant, ast.Str)))
                    else None
                )
                doc_end_line = getattr(doc_node, "end_lineno", doc_node.lineno) if doc_node else 0

                if doc_node and len(node.body) > 1 and doc_end_line >= node.lineno:
                    sig_lines = code_lines[s_idx : doc_node.lineno - 1]
                    if len(sig_lines) > 3:
                        sig_lines = sig_lines[:2] + ["    ..."]
                    body_lines = code_lines[doc_end_line : min(end_lineno, doc_end_line + 11)]
                    excerpt_lines = sig_lines + ["    # docstring omitted"] + body_lines
                    excerpt = "\n".join(excerpt_lines[:14])
                else:
                    e_idx = min(s_idx + 14, end_lineno)
                    excerpt = "\n".join(code_lines[s_idx:e_idx])

                def_l = code_lines[s_idx].strip() if s_idx < len(code_lines) else ""

                c_vis = FunctionCallVisitor()
                c_vis.visit(node)
                meaningful_calls = c_vis.calls[:10]

                # Extract parameters and returns
                params = [arg.arg for arg in node.args.args if arg.arg != "self"]
                has_ret = any(isinstance(n, ast.Return) for n in ast.walk(node))

                doc_span = None
                if first_line_doc:
                    doc_span = SourceSpan(
                        file=rel_path,
                        start_line=node.lineno,
                        end_line=min(node.lineno + 4, end_lineno),
                        text=first_line_doc,
                    )

                # T6: Mark trivial wrappers to deprioritize them
                trivial = is_trivial_wrapper(node)

                sym = TopSymbol(
                    name=name,
                    kind="function",
                    file=rel_path,
                    docstring=first_line_doc,
                    docstring_span=doc_span,
                    start_line=node.lineno,
                    end_line=end_lineno,
                    def_line=def_l,
                    code_excerpt=excerpt,
                    calls=meaningful_calls,
                    parameters=params,
                    has_return=has_ret,
                )
                if trivial:
                    symbols.append(sym)
                else:
                    # Non-trivial functions inserted first
                    symbols.insert(0, sym)

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

    # 3. CLI flags
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
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
