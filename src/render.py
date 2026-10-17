"""
Renderer: generates PNG frames from scene data.

Default: Playwright (Chromium screenshot with JS disabled).
Fallback: Pillow (draws formatted scene text, badge, card, and narration).
Both renderers guarantee readable text frames (never flat solid colors).
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    """Result of rendering a single scene."""
    renderer_used: str  # 'playwright' or 'fallback_pillow'
    fallback_reason: str = ""
    has_overflow: bool = False
    overflow_details: str = ""


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
    padding: 40px 70px;
    overflow: hidden;
  }}
  .repo-badge {{
    position: absolute;
    top: 25px;
    right: 70px;
    font-size: 14px;
    color: #bdc3c7;
    background: rgba(0, 0, 0, 0.45);
    border: 1px solid rgba(255, 255, 255, 0.15);
    padding: 6px 16px;
    border-radius: 20px;
  }}
  .scene-id {{
    font-size: 15px;
    color: #95a5a6;
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 16px;
  }}
  .content-box {{
    background: rgba(10, 10, 25, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 12px;
    padding: 30px;
    height: 460px;
    max-height: 460px;
    overflow: hidden;
    word-break: break-word;
    overflow-wrap: anywhere;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
  }}
  .content-box.code {{
    font-family: 'DejaVu Sans Mono', 'Liberation Mono', 'Courier New', monospace;
    font-size: {font_size};
    line-height: 1.5;
    white-space: pre-wrap;
    color: #a8e6cf;
  }}
  .content-box.text {{
    font-size: {font_size};
    line-height: 1.5;
    text-align: center;
    align-items: center;
    justify-content: center;
    color: #ffffff;
  }}
  .content-box.diagram {{
    font-family: 'DejaVu Sans Mono', 'Liberation Mono', monospace;
    font-size: {font_size};
    line-height: 1.4;
    white-space: pre-wrap;
    color: #ffd93d;
  }}
  .narration-preview {{
    margin-top: 20px;
    font-size: 16px;
    color: #95a5a6;
    font-style: italic;
    line-height: 1.4;
    max-height: 50px;
    overflow: hidden;
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


def _step_down_layout(content: str, max_lines: int = 16, max_chars: int = 1000) -> tuple[str, str, bool]:
    """Applies font size step-down, line wrapping, and visible truncation marker."""
    truncated = False
    lines = content.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + ["... [truncated for display]"]
        content = "\n".join(lines)
        truncated = True
    elif len(content) > max_chars:
        content = content[:max_chars - 30] + "\n... [truncated for display]"
        truncated = True

    length = len(content)
    line_count = len(content.splitlines())
    if length > 600 or line_count > 12:
        font_size = "15px"
    elif length > 300 or line_count > 8:
        font_size = "18px"
    elif length > 150 or line_count > 4:
        font_size = "22px"
    else:
        font_size = "26px"

    return content, font_size, truncated


def _render_scene_html(
    scene_id: str,
    content_type: str,
    content: str,
    narration: str,
    repo_name: str,
) -> tuple[str, bool]:
    """Generate HTML for a single scene card. Text is HTML-escaped."""
    processed_content, font_size, truncated = _step_down_layout(content)
    escaped_content = html.escape(processed_content).replace("\n", "<br>")
    narration_prev = narration[:140] + ("..." if len(narration) > 140 else "")

    html_str = _SCENE_HTML.format(
        scene_id=html.escape(scene_id),
        content_type=html.escape(content_type),
        content=escaped_content,
        narration_preview=html.escape(narration_prev),
        repo_name=html.escape(repo_name),
        font_size=font_size,
    )
    return html_str, truncated


def render_scene_to_png(
    scene_id: str,
    content_type: str,
    content: str,
    narration: str,
    repo_name: str,
    output_path: Path,
    use_playwright: bool = True,
) -> RenderResult:
    """
    Render a scene to a PNG image.

    Default: Playwright Chromium screenshot (JS disabled).
    Fallback: Pillow drawing scene text and layout (never flat solid colors).
    """
    html_content, _ = _render_scene_html(scene_id, content_type, content, narration, repo_name)
    html_path = output_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")

    fallback_reason = ""
    if use_playwright:
        try:
            return _screenshot_with_playwright(html_path, output_path, scene_id)
        except Exception as e:
            fallback_reason = f"Playwright failed: {e}"
            logger.warning(f"Playwright rendering failed ({e}), falling back to Pillow")
    else:
        fallback_reason = "Playwright disabled by configuration"

    return _render_with_pillow(
        scene_id=scene_id,
        content_type=content_type,
        content=content,
        narration=narration,
        repo_name=repo_name,
        output_path=output_path,
        fallback_reason=fallback_reason,
    )


def _screenshot_with_playwright(html_path: Path, output_path: Path, scene_id: str) -> RenderResult:
    """Take a screenshot using Playwright with JS disabled, checking for overflow."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            java_script_enabled=False,  # Security: no untrusted JS execution
        )
        page = context.new_page()
        page.goto(f"file://{html_path.resolve()}", wait_until="load")

        # Check if content box overflows available frame
        overflow = page.evaluate("""() => {
            const el = document.querySelector('.content-box');
            if (!el) return false;
            return (el.scrollHeight > el.clientHeight + 4) || (el.scrollWidth > el.clientWidth + 4);
        }""")

        page.screenshot(path=str(output_path))
        context.close()
        browser.close()

    return RenderResult(
        renderer_used="playwright",
        fallback_reason="",
        has_overflow=bool(overflow),
        overflow_details=f"Scene '{scene_id}' content box overflowed 460px viewport" if overflow else "",
    )


def _load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Load TrueType font or fall back to default."""
    candidates = [
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
        "arial.ttf",
        "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _render_with_pillow(
    scene_id: str,
    content_type: str,
    content: str,
    narration: str,
    repo_name: str,
    output_path: Path,
    fallback_reason: str,
) -> RenderResult:
    """Render readable scene frame using Pillow when Playwright is unavailable."""
    width, height = 1280, 720
    img = Image.new("RGB", (width, height), color=(20, 18, 38))
    draw = ImageDraw.Draw(img)

    # Decorative header & card
    draw.rectangle([60, 80, 1220, 560], fill=(12, 12, 26), outline=(60, 60, 95), width=2)
    draw.rectangle([980, 24, 1220, 60], fill=(35, 33, 58), outline=(80, 80, 120), width=1)

    font_header = _load_font(16)
    font_badge = _load_font(14)
    font_narration = _load_font(16)

    draw.text((70, 36), f"SCENE: {scene_id.upper()}", fill=(160, 165, 175), font=font_header)
    draw.text((995, 34), repo_name[:24], fill=(220, 220, 230), font=font_badge)

    # Content layout with step-down and wrapping
    content_color = (168, 230, 207) if content_type == "code" else ((255, 217, 61) if content_type == "diagram" else (255, 255, 255))
    processed_content, _, truncated = _step_down_layout(content, max_lines=15, max_chars=800)

    # Wrap lines for card width
    wrapped_lines: list[str] = []
    for raw_line in processed_content.splitlines():
        wrapped = textwrap.wrap(raw_line, width=72)
        wrapped_lines.extend(wrapped if wrapped else [""])

    font_size = 20 if len(wrapped_lines) <= 8 else (16 if len(wrapped_lines) <= 12 else 13)
    content_font = _load_font(font_size)
    line_height = font_size + 6

    # Check overflow
    has_overflow = len(wrapped_lines) * line_height > 440

    y = 110
    for line in wrapped_lines[:15]:
        draw.text((90, y), line, fill=content_color, font=content_font)
        y += line_height

    # Narration preview at bottom
    narr_prev = narration[:120] + ("..." if len(narration) > 120 else "")
    draw.text((70, 610), narr_prev, fill=(150, 160, 170), font=font_narration)

    img.save(str(output_path), "PNG")
    return RenderResult(
        renderer_used="fallback_pillow",
        fallback_reason=fallback_reason,
        has_overflow=has_overflow,
        overflow_details=f"Scene '{scene_id}' text exceeded card capacity" if has_overflow else "",
    )
