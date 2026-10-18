"""
Renderer module: generates 1280x720 PNG frames from scene beats.

Features:
- Single browser instance reused across all frames (Playwright Chromium)
- JavaScript disabled for security (static HTML + inline SVG)
- Pygments syntax-highlighted code with exact indentation preservation (P5 fix)
- Pillow fallback with text metrics, diagram boxes, and strict overflow flagging (R7 fix)
- Dynamic chapter ribbon, caption bar, and progress bar on every frame
"""

from __future__ import annotations

import logging
import os
import shutil
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .render_html import FONTS_DIR, build_frame_html
from .schema import Beat, Scene

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    """Result of rendering a single video frame."""
    renderer_used: str  # 'playwright' or 'fallback_pillow'
    fallback_reason: str = ""
    has_overflow: bool = False
    overflow_details: str = ""


def _step_down_layout(content: str, max_lines: int = 15, max_chars: int = 800) -> tuple[str, str, bool]:
    """Step down font size and truncate excessive lines for display."""
    lines = content.strip().splitlines()
    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + ["... [truncated for display]"]
        truncated = True
    font_size = "18px" if len(lines) <= 8 else "15px"
    return "\n".join(lines), font_size, truncated


class PlaywrightRenderer:
    """Manages a single Playwright Chromium browser lifecycle for the entire run."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def start(self) -> None:
        """Launch Chromium browser with JavaScript disabled."""
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        # In container or Linux, --no-sandbox might be needed; on Windows standard flags apply
        args = ["--disable-gpu"]
        if os.environ.get("DEVVIDEO_CONTAINER") == "1" or not os.name == "nt":
            args.append("--no-sandbox")

        self._browser = self._playwright.chromium.launch(headless=True, args=args)
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            java_script_enabled=False,
        )
        self._page = self._context.new_page()

    def render_frame(self, html_content: str, output_path: Path) -> RenderResult:
        """Render frame from HTML string and save screenshot as PNG."""
        if self._page is None:
            self.start()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._page.set_content(html_content, wait_until="load")

        # DOM measurement for overflow detection (Gate 8)
        has_overflow = False
        overflow_details = ""
        try:
            center_loc = self._page.locator(".center-stage")
            box = center_loc.bounding_box()
            if box and box.get("height", 0) > 540:
                has_overflow = True
                overflow_details = f"Center stage height {box.get('height')}px exceeds viewport limit"
        except Exception:
            pass

        self._page.screenshot(path=str(output_path), type="png")
        return RenderResult(
            renderer_used="playwright",
            fallback_reason="",
            has_overflow=has_overflow,
            overflow_details=overflow_details,
        )

    def close(self) -> None:
        """Close browser resources cleanly."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None


class PillowRenderer:
    """Fallback software renderer using PIL/Pillow with strict layout metrics."""

    def __init__(self) -> None:
        self.font_title = self._load_font(28)
        self.font_body = self._load_font(18)
        self.font_caption = self._load_font(15)
        self.font_mono = self._load_font(15, mono=True)

    def _load_font(self, size: int, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        font_file = "JetBrainsMono-Regular.ttf" if mono else "Inter-Regular.ttf"
        vendored = FONTS_DIR / font_file
        if vendored.exists():
            try:
                return ImageFont.truetype(str(vendored), size)
            except Exception:
                pass

        # OS font fallbacks
        candidates = [
            "arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]
        for c in candidates:
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def render_frame(
        self,
        scene_id: str,
        scene_kind: str,
        scene_title: str,
        content: str,
        caption: str,
        repo_name: str,
        progress_pct: float,
        output_path: Path,
        fallback_reason: str = "Playwright disabled or unavailable",
        state_kind: str = "default",
        state_data: dict[str, Any] | None = None,
    ) -> RenderResult:
        """Draw complete frame with chapter ribbon, content card, caption bar, and progress."""
        sdata = state_data or {}
        width, height = 1280, 720
        img = Image.new("RGB", (width, height), color=(11, 15, 25))
        draw = ImageDraw.Draw(img)

        # 1. Top Ribbon & Badge
        draw.rectangle([48, 24, 300, 56], fill=(30, 41, 59), outline=(71, 85, 105), width=1)
        draw.text((64, 30), f"SCENE: {scene_title.upper() or scene_id.upper()}", fill=(241, 245, 249), font=self.font_caption)
        draw.text((1060, 30), repo_name[:22], fill=(148, 163, 184), font=self.font_caption)

        # 2. Main Content Card
        draw.rectangle([48, 80, 1232, 590], fill=(15, 23, 42), outline=(51, 65, 85), width=2)

        # Draw content
        lines = content.strip().splitlines()
        has_overflow = False
        overflow_details = ""

        # R7 fix: Flag overflow for lines dropped past 15
        if len(lines) > 15:
            has_overflow = True
            overflow_details = f"Scene '{scene_id}' dropped {len(lines) - 15} lines past 15 in Pillow fallback"

        y = 110
        font_to_use = self.font_mono if scene_kind in ("code", "terminal", "diagram") else self.font_body
        text_color = (56, 189, 248) if scene_kind == "code" else ((16, 185, 129) if scene_kind == "terminal" else (248, 250, 252))

        focus_range = sdata.get("focus_range")
        cmd_display = sdata.get("command_display")

        if scene_kind == "terminal" and cmd_display:
            draw.text((70, y), f"$ {cmd_display}_", fill=(16, 185, 129), font=self.font_mono)
            y += 30
        else:
            for idx, line in enumerate(lines[:15], start=1):
                if scene_kind == "code":
                    is_foc = (focus_range is None) or (focus_range[0] <= idx <= focus_range[1])
                    line_col = (56, 189, 248) if is_foc else (100, 116, 139)
                    draw.text((70, y), f"{idx:2d}  {line}", fill=line_col, font=font_to_use)
                elif scene_kind == "terminal":
                    draw.text((70, y), f"$ {line.lstrip('$ ')}", fill=text_color, font=font_to_use)
                else:
                    wrapped = textwrap.wrap(line, width=76)
                    for w in wrapped:
                        draw.text((70, y), w, fill=text_color, font=font_to_use)
                        y += 24
                y += 26

        if y > 570:
            has_overflow = True
            overflow_details = f"Scene '{scene_id}' text bounding height ({y}px) exceeded 570px card limit"

        # 3. Caption Box
        draw.rectangle([48, 610, 1232, 670], fill=(2, 6, 23), outline=(51, 65, 85), width=1)
        draw.text((70, 626), caption[:120], fill=(226, 232, 240), font=self.font_caption)

        # 4. Progress Rail
        draw.rectangle([48, 684, 1232, 688], fill=(30, 41, 59))
        fill_w = int(1184 * (min(100.0, max(0.0, progress_pct)) / 100.0))
        if fill_w > 0:
            draw.rectangle([48, 684, 48 + fill_w, 688], fill=(79, 70, 229))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "PNG")

        return RenderResult(
            renderer_used="fallback_pillow",
            fallback_reason=fallback_reason,
            has_overflow=has_overflow,
            overflow_details=overflow_details,
        )


def render_scene_to_png(
    scene_id: str,
    content_type: str,
    content: str,
    narration: str,
    repo_name: str,
    output_path: Path,
    use_playwright: bool = True,
    playwright_renderer: PlaywrightRenderer | None = None,
    all_scene_titles: list[str] | None = None,
    current_scene_idx: int = 0,
    progress_pct: float = 0.0,
    metadata: dict[str, Any] | None = None,
    active_focus: str | None = None,
    state_kind: str = "default",
    state_data: dict[str, Any] | None = None,
) -> RenderResult:
    """
    Render a single scene or beat frame to PNG using Playwright with Pillow fallback.
    Maintains compatibility with pipeline and test callers.
    """
    titles = all_scene_titles or [scene_id]

    if use_playwright:
        try:
            renderer = playwright_renderer or PlaywrightRenderer()
            html_content = build_frame_html(
                repo_name=repo_name,
                scene_id=scene_id,
                scene_kind=content_type,
                scene_title=scene_id.capitalize(),
                content=content,
                caption=narration,
                all_scene_titles=titles,
                current_scene_idx=current_scene_idx,
                progress_pct=progress_pct,
                metadata=metadata,
                active_focus=active_focus,
                state_kind=state_kind,
                state_data=state_data,
            )
            res = renderer.render_frame(html_content, output_path)
            # If standalone renderer created locally, close it
            if playwright_renderer is None:
                renderer.close()
            return res
        except Exception as e:
            logger.warning(f"Playwright render failed ({e}), falling back to Pillow")
            pillow = PillowRenderer()
            return pillow.render_frame(
                scene_id=scene_id,
                scene_kind=content_type,
                scene_title=scene_id,
                content=content,
                caption=narration,
                repo_name=repo_name,
                progress_pct=progress_pct,
                output_path=output_path,
                fallback_reason=str(e),
                state_kind=state_kind,
                state_data=state_data,
            )
    else:
        pillow = PillowRenderer()
        return pillow.render_frame(
            scene_id=scene_id,
            scene_kind=content_type,
            scene_title=scene_id,
            content=content,
            caption=narration,
            repo_name=repo_name,
            progress_pct=progress_pct,
            output_path=output_path,
            fallback_reason="Playwright disabled by user",
            state_kind=state_kind,
            state_data=state_data,
        )
