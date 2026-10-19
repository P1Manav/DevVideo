"""
JavaScript / TypeScript regex-based import graph and symbol extraction.
"""
from __future__ import annotations

import os
import re
from .models import ImportEdge, TopSymbol


def extract_js_facts(
    rel_path: str,
    code: str,
    all_js_files: set[str],
) -> tuple[list[ImportEdge], list[TopSymbol]]:
    """Extract internal import edges and top-level function/class symbols from JS/TS code using regex."""
    edges: list[ImportEdge] = []
    symbols: list[TopSymbol] = []
    patterns = [
        re.compile(r"""(?:import|require)\s*\(?['"](\.[^'"]+)['"]\s*\)?"""),
    ]
    dir_name = os.path.dirname(rel_path)

    for pat in patterns:
        for m in pat.finditer(code):
            target_rel = m.group(1)
            norm = os.path.normpath(os.path.join(dir_name, target_rel)).replace("\\", "/")
            line_no = code[:m.start()].count("\n") + 1
            for known in all_js_files:
                if (known == norm or known.startswith(norm + ".") or norm in known) and known != rel_path:
                    edges.append(ImportEdge(source=rel_path, target=known, raw_line=m.group(0), line_number=line_no))

    for m in re.finditer(r"(?:function|class|const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)", code):
        name = m.group(1)
        if name not in ("require", "module", "exports", "import"):
            line_no = code[:m.start()].count("\n") + 1
            lines = code.splitlines()
            s_idx = max(0, line_no - 1)
            e_idx = min(s_idx + 10, len(lines))
            excerpt = "\n".join(lines[s_idx:e_idx])
            full_line = lines[line_no - 1].strip() if line_no - 1 < len(lines) else ""
            symbols.append(
                TopSymbol(
                    name=name,
                    kind="function",
                    file=rel_path,
                    start_line=line_no,
                    end_line=min(line_no + 9, len(lines)),
                    def_line=full_line,
                    code_excerpt=excerpt,
                    calls=[],
                )
            )

    return edges, symbols
