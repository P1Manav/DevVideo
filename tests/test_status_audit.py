"""Audit test for docs/verification/STATUS.md ensuring all linked logs exist and are valid."""
from pathlib import Path
import re
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = REPO_ROOT / "docs" / "verification" / "STATUS.md"
VERIFICATION_DIR = REPO_ROOT / "docs" / "verification"

def test_status_md_links_exist():
    assert STATUS_PATH.exists(), "STATUS.md does not exist"
    content = STATUS_PATH.read_text(encoding="utf-8")
    
    # Check all markdown links
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content)
    assert links, "No links found in STATUS.md"
    
    missing = []
    for text, link in links:
        if link.startswith("http") or link.startswith("#"):
            continue
        target = (VERIFICATION_DIR / link).resolve()
        if not target.exists():
            missing.append(f"Linked file missing: {link} (from text '{text}')")
            
    assert not missing, "\n".join(missing)

def test_status_md_no_file_urls():
    content = STATUS_PATH.read_text(encoding="utf-8")
    assert "file:///" not in content, "STATUS.md contains file:/// URLs"
    assert not re.search(r"\b[A-Za-z]:[\\/]", content), "STATUS.md contains absolute drive letter paths"
