"""
Frontend provider for DevVideo Web Application.
Loads the responsive single-page web UI.
"""

from __future__ import annotations

from pathlib import Path

_STATIC_DIR = Path(__file__).parent / "static"
_INDEX_FILE = _STATIC_DIR / "index.html"


def get_index_html() -> str:
    """Return the content of the single-page frontend HTML."""
    if _INDEX_FILE.exists():
        return _INDEX_FILE.read_text(encoding="utf-8")
    return "<html><body><h2>DevVideo Web Interface</h2><p>index.html not found</p></body></html>"
