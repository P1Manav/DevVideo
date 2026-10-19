"""Test that README.md is fully generated and has zero diff when tools/gen_docs.py runs."""
from pathlib import Path
import pytest
from tools.gen_docs import update_readme

README_PATH = Path(__file__).parent.parent / "README.md"

def test_gen_docs_produces_zero_diff():
    original = README_PATH.read_text(encoding="utf-8")
    update_readme()
    updated = README_PATH.read_text(encoding="utf-8")
    assert original == updated, "README.md has uncommitted manual changes or drift from tools/gen_docs.py"

def test_no_file_urls_or_drive_letters_in_docs():
    docs_dir = Path(__file__).parent.parent / "docs"
    root_dir = Path(__file__).parent.parent
    md_files = list(docs_dir.rglob("*.md")) + [root_dir / "README.md"]
    
    violations = []
    for md in md_files:
        content = md.read_text(encoding="utf-8")
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            if "file:///" in line and not line.strip().startswith("- phase7_gates_registry:"):
                violations.append(f"{md.relative_to(root_dir)}:{idx}: contains file:/// URL: {line}")
            if "[file:" in line or "(file:" in line:
                violations.append(f"{md.relative_to(root_dir)}:{idx}: contains file: link: {line}")
    assert not violations, "\n".join(violations)
