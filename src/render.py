"""
Renderer: generates PNG frames from scene data using Playwright.

Each scene becomes an HTML card that is screenshot to PNG.
All repo text is HTML-escaped. Playwright runs with JS disabled.
"""

from __future__ import annotations

import html
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# --- HTML template for scene cards ---

_SCENE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1280px;
    height: 720px;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    font-family: 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif;
    color: #e0e0e0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 60px 80px;
    overflow: hidden;
  }}
  .scene-id {{
    font-size: 14px;
    color: #7f8c8d;
    text-transform: uppercase;
    letter-spacing: 3px;
    margin-bottom: 20px;
  }}
  .content-box {{
    background: rgba(0, 0, 0, 0.4);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 40px;
    max-height: 480px;
    overflow: hidden;
  }}
  .content-box.code {{
    font-family: 'DejaVu Sans Mono', 'Liberation Mono', monospace;
    font-size: 20px;
    line-height: 1.6;
    white-space: pre-wrap;
    color: #a8e6cf;
  }}
  .content-box.text {{
    font-size: 28px;
    line-height: 1.5;
    text-align: center;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
  }}
  .content-box.diagram {{
    font-family: 'DejaVu Sans Mono', 'Liberation Mono', monospace;
    font-size: 18px;
    line-height: 1.4;
    white-space: pre-wrap;
    color: #ffd93d;
    text-align: center;
  }}
  .narration-preview {{
    margin-top: 30px;
    font-size: 16px;
    color: #95a5a6;
    font-style: italic;
    line-height: 1.4;
    max-height: 60px;
    overflow: hidden;
  }}
  .repo-badge {{
    position: absolute;
    top: 20px;
    right: 30px;
    font-size: 12px;
    color: #7f8c8d;
    background: rgba(0, 0, 0, 0.3);
    padding: 6px 14px;
    border-radius: 20px;
  }}
</style>
</head>
<body>
  <div class="repo-badge">{repo_name}</div>
  <div class="scene-id">Scene: {scene_id}</div>
  <div class="content-box {content_type}">
    {content}
  </div>
  <div class="narration-preview">{narration_preview}</div>
</body>
</html>"""


def _render_scene_html(
    scene_id: str,
    content_type: str,
    content: str,
    narration: str,
    repo_name: str,
) -> str:
    """Generate HTML for a single scene card. All text is HTML-escaped."""
    return _SCENE_HTML.format(
        scene_id=html.escape(scene_id),
        content_type=html.escape(content_type),
        content=html.escape(content).replace("\\n", "<br>"),
        narration_preview=html.escape(narration[:120] + ("..." if len(narration) > 120 else "")),
        repo_name=html.escape(repo_name),
    )


def render_scene_to_png(
    scene_id: str,
    content_type: str,
    content: str,
    narration: str,
    repo_name: str,
    output_path: Path,
    use_playwright: bool = True,
) -> None:
    """
    Render a scene to a PNG image.

    If Playwright is available, uses it with JS disabled.
    Otherwise falls back to a simple ffmpeg-based placeholder.
    """
    html_content = _render_scene_html(scene_id, content_type, content, narration, repo_name)
    html_path = output_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")

    if use_playwright:
        try:
            _screenshot_with_playwright(html_path, output_path)
            return
        except Exception as e:
            logger.warning(f"Playwright rendering failed: {e}, falling back to ffmpeg")

    # Fallback: generate a solid-color frame with ffmpeg
    _fallback_frame(output_path)


def _screenshot_with_playwright(html_path: Path, output_path: Path) -> None:
    """Take a screenshot using Playwright with JS disabled."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            java_script_enabled=False,  # Security: no JS execution
        )
        page = context.new_page()
        page.goto(f"file://{html_path.resolve()}")
        page.screenshot(path=str(output_path))
        context.close()
        browser.close()

    logger.debug(f"Rendered {html_path.name} -> {output_path.name}")


def _fallback_frame(output_path: Path, width: int = 1280, height: int = 720) -> None:
    """Generate a solid-color placeholder frame using ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("Neither Playwright nor ffmpeg available for rendering")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={width}x{height}:d=0.04",
            "-frames:v", "1",
            str(output_path),
        ],
        capture_output=True,
        timeout=10,
    )
