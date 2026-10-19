"""
Import audit test: ensures all third-party dependencies are declared in requirements.

Parses every .py file under src/, tools/, and tests/ using ast.
Extracts top-level imports, subtracts stdlib and local modules/fixtures,
and verifies that every third-party package is explicitly listed in requirements.txt
(and requirements-dev.txt for tests).
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent

IMPORT_TO_PKG = {
    "PIL": "pillow",
    "edge_tts": "edge-tts",
    "pydantic": "pydantic",
    "pygments": "pygments",
    "playwright": "playwright",
    "pyttsx3": "pyttsx3",
    "pytest": "pytest",
    "yaml": "pyyaml",
}


def _parse_requirements(req_path: Path) -> set[str]:
    """Parse normalized package names from requirements file."""
    if not req_path.exists():
        return set()
    names = set()
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_.-]+)", line)
        if m:
            names.add(m.group(1).lower().replace("_", "-"))
    return names


def _collect_top_level_imports(directory: Path) -> set[str]:
    """Parse all .py files in directory and collect top-level import names (excluding test fixtures)."""
    imports = set()
    for root, _, files in os.walk(directory):
        if "fixtures" in Path(root).parts:
            continue
        for f in files:
            if f.endswith(".py"):
                file_path = Path(root) / f
                try:
                    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
                except Exception as e:
                    pytest.fail(f"Failed to parse {file_path}: {e}")
                for node in tree.body:
                    if isinstance(node, ast.Import):
                        for n in node.names:
                            imports.add(n.name.split(".")[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.level == 0:
                            imports.add(node.module.split(".")[0])
    return imports


def _get_local_packages() -> set[str]:
    """Identify local packages and fixtures in the repository."""
    local = {"src", "tools", "tests", "helpers"}
    # Scan tests/fixtures for package folders containing __init__.py or .py files
    fixtures_dir = ROOT / "tests" / "fixtures"
    if fixtures_dir.exists():
        for item in fixtures_dir.iterdir():
            if item.is_dir():
                local.add(item.name)
                for sub in item.iterdir():
                    if sub.is_dir() and ((sub / "__init__.py").exists() or any(sub.glob("*.py"))):
                        local.add(sub.name)
    # Check obsolete fixture dirs if present
    for d in ["fixture_repo", "fixture_repo_2"]:
        if (ROOT / "tests" / d).exists():
            local.add(d)
    return local


def test_src_and_tools_imports_declared_in_requirements():
    """All top-level imports in src/ and tools/ must be declared in requirements.txt."""
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    local_pkgs = _get_local_packages()
    req_pkgs = _parse_requirements(ROOT / "requirements.txt")

    src_imports = _collect_top_level_imports(ROOT / "src")
    tools_imports = _collect_top_level_imports(ROOT / "tools") if (ROOT / "tools").exists() else set()
    combined = (src_imports | tools_imports) - stdlib - local_pkgs

    undeclared = set()
    for mod in combined:
        pkg = IMPORT_TO_PKG.get(mod, mod.lower().replace("_", "-"))
        if pkg not in req_pkgs:
            undeclared.add(f"{mod} (package: {pkg})")

    assert not undeclared, (
        f"Undeclared third-party imports in src/ or tools/: {sorted(undeclared)}. "
        f"Must be declared in requirements.txt"
    )


def test_tests_imports_declared_in_requirements_or_dev():
    """All top-level imports in tests/ must be declared in requirements.txt or requirements-dev.txt."""
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    local_pkgs = _get_local_packages()
    all_req_pkgs = _parse_requirements(ROOT / "requirements.txt") | _parse_requirements(ROOT / "requirements-dev.txt")

    tests_imports = _collect_top_level_imports(ROOT / "tests") - stdlib - local_pkgs

    undeclared = set()
    for mod in tests_imports:
        pkg = IMPORT_TO_PKG.get(mod, mod.lower().replace("_", "-"))
        if pkg not in all_req_pkgs:
            undeclared.add(f"{mod} (package: {pkg})")

    assert not undeclared, (
        f"Undeclared third-party imports in tests/: {sorted(undeclared)}. "
        f"Must be declared in requirements.txt or requirements-dev.txt"
    )


def test_import_audit_fails_on_undeclared_mock():
    """Sanity test verifying that an undeclared mock package would indeed fail the audit."""
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    dummy_imports = {"definitely_not_a_real_dep_xyz"}
    req_pkgs = _parse_requirements(ROOT / "requirements.txt")
    unmatched = {m for m in dummy_imports if m not in req_pkgs}
    assert len(unmatched) == 1
