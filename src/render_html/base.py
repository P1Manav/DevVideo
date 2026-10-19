"""
Base HTML rendering: fonts, global stylesheet, and page shell wrapper.
"""

from __future__ import annotations

import html
from pathlib import Path

FONTS_DIR = Path(__file__).parent.parent.parent / "assets" / "fonts"
STYLE_CSS_PATH = Path(__file__).parent / "style.css"


def get_font_css() -> str:
    """Generate CSS for vendored Inter and JetBrains Mono fonts."""
    inter_path = (FONTS_DIR / "Inter-Regular.ttf").resolve().as_posix()
    mono_path = (FONTS_DIR / "JetBrainsMono-Regular.ttf").resolve().as_posix()

    return f"""
    @font-face {{
      font-family: 'Inter';
      src: url('file:///{inter_path}') format('truetype');
      font-weight: 400 700;
      font-style: normal;
    }}
    @font-face {{
      font-family: 'JetBrains Mono';
      src: url('file:///{mono_path}') format('truetype');
      font-weight: 400 600 700;
      font-style: normal;
    }}
    """


GLOBAL_CSS = STYLE_CSS_PATH.read_text(encoding="utf-8") if STYLE_CSS_PATH.exists() else ""


def wrap_html_shell(
    inner_content: str,
    repo_name: str,
    ribbon_html: str,
    caption: str,
    progress_pct: float,
) -> str:
    """Wrap scene center-stage content in complete 1280x720 video frame HTML."""
    font_css = get_font_css()
    caption_clean = html.escape(caption[:140])
    pct_val = min(100.0, max(0.0, progress_pct))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  {font_css}
  {GLOBAL_CSS}
  .progress-fill {{
    height: 100%;
    width: {pct_val:.1f}%;
    background: linear-gradient(90deg, #4f46e5, #38bdf8);
  }}
</style>
</head>
<body>
  <div class="top-header">
    <div class="chapter-ribbon">{ribbon_html}</div>
    <div class="repo-badge">{html.escape(repo_name)}</div>
  </div>
  <div class="center-stage">
    {inner_content}
  </div>
  <div class="bottom-bar">
    <div class="caption-box">{caption_clean}</div>
    <div class="progress-rail">
      <div class="progress-fill"></div>
    </div>
  </div>
</body>
</html>
"""
