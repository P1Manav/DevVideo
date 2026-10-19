"""Enforce that no python file in src/ exceeds the 400-line budget."""
from pathlib import Path
import pytest

SRC_DIR = Path(__file__).parent.parent / "src"

def test_no_src_file_exceeds_400_lines():
    py_files = list(SRC_DIR.rglob("*.py"))
    assert py_files, "No python files found in src/"
    
    oversized = []
    for f in py_files:
        lines = len(f.read_text(encoding="utf-8").splitlines())
        if lines > 400:
            oversized.append(f"{f.relative_to(SRC_DIR.parent)}: {lines} lines (budget: 400)")
            
    assert not oversized, f"Files exceeding 400 lines:\n" + "\n".join(oversized)
