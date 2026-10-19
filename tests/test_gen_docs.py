"""Test that README.md is fully generated, gates match registry, and docs are clean."""
from pathlib import Path
import re
import pytest
from tools.gen_docs import update_readme
from src.evals.registry import GATES_REGISTRY

ROOT_DIR = Path(__file__).parent.parent
README_PATH = ROOT_DIR / "README.md"


def test_gen_docs_produces_zero_diff():
    original = README_PATH.read_text(encoding="utf-8")
    update_readme()
    updated = README_PATH.read_text(encoding="utf-8")
    assert original == updated, "README.md has uncommitted manual changes or drift from tools/gen_docs.py"


def test_readme_contains_no_stale_numbers_or_phrases():
    content = README_PATH.read_text(encoding="utf-8")
    assert "9 hard" not in content, "README contains stale '9 hard' mention"
    assert "all 9" not in content, "README contains stale 'all 9' mention"
    
    # Verify gate count in README matches registry exactly
    expected_gate_count = len(GATES_REGISTRY)
    m = re.search(r"<!-- BEGIN:GENERATED:gate_count -->(\d+)<!-- END:GENERATED:gate_count -->", content)
    assert m is not None, "Missing gate_count generated marker in README"
    assert int(m.group(1)) == expected_gate_count, f"README gate count {m.group(1)} != registry {expected_gate_count}"


def test_no_file_urls_or_drive_letters_in_docs():
    md_files = [p for p in ROOT_DIR.rglob("*.md") if ".pytest_cache" not in str(p)]
    
    violations = []
    for md in md_files:
        content = md.read_text(encoding="utf-8")
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            if "file:///" in line:
                violations.append(f"{md.relative_to(ROOT_DIR)}:{idx}: contains file:/// URL: {line}")
            if "[file:" in line or "(file:" in line:
                violations.append(f"{md.relative_to(ROOT_DIR)}:{idx}: contains file: link: {line}")
            # Check for local drive letters like C:\ or D:/ at start of word
            if re.search(r"(?:^|[\s\"\'\(])[a-zA-Z]:[\\/]", line):
                violations.append(f"{md.relative_to(ROOT_DIR)}:{idx}: contains drive letter: {line}")
    assert not violations, "\n".join(violations)


def test_verification_dir_has_no_stale_evidence():
    verif_dir = ROOT_DIR / "docs" / "verification"
    allowed_names = {
        "run_all.py",
        "simulate_fresh_clone.py",
        "STATUS.md",
        "verify_frames_and_cues.py",
        "verify_matrix.py",
        "logs",
    }
    for item in verif_dir.iterdir():
        assert item.name in allowed_names, f"Stale or unmanaged file found in docs/verification: {item.name}"

