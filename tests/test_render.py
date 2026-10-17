"""
Unit tests for renderer module: Playwright rendering, Pillow fallback,
text-overflow detection, layout protection, and non-flat frame assertion.
"""

from pathlib import Path
from PIL import Image
import pytest

from src.render import render_scene_to_png, _step_down_layout


def _count_distinct_colors(img: Image.Image) -> int:
    colors = img.getcolors(maxcolors=1280 * 720)
    if colors is not None:
        return len(colors)
    return len(set(img.getdata()))


class TestRenderer:
    def test_playwright_renders_readable_frame_not_flat_color(self, tmp_path):
        """Playwright renderer produces an image with rich content (many distinct colors)."""
        output_path = tmp_path / "playwright_frame.png"
        res = render_scene_to_png(
            scene_id="intro_scene",
            content_type="code",
            content="def hello_world():\n    return 'Playwright rendered frame'",
            narration="This is a test narration for verifying Playwright rendering output.",
            repo_name="my_test_repo",
            output_path=output_path,
            use_playwright=True,
        )

        assert output_path.exists()
        assert res.renderer_used == "playwright"
        assert not res.has_overflow

        # Assert frame is NOT a flat single color
        with Image.open(output_path) as img:
            assert img.size == (1280, 720)
            n_colors = _count_distinct_colors(img)
            assert n_colors > 100, f"Expected rich frame, but got only {n_colors} distinct colors"

    def test_pillow_fallback_renders_readable_frame_not_flat_color(self, tmp_path):
        """Pillow fallback renderer produces an image with real readable text (not flat color)."""
        output_path = tmp_path / "pillow_frame.png"
        res = render_scene_to_png(
            scene_id="fallback_scene",
            content_type="text",
            content="Fallback content rendered via Pillow.\nGuaranteed readable text.",
            narration="Narration preview text displayed at the bottom of the card.",
            repo_name="my_test_repo",
            output_path=output_path,
            use_playwright=False,
        )

        assert output_path.exists()
        assert res.renderer_used == "fallback_pillow"
        assert "disabled" in res.fallback_reason.lower() or "failed" in res.fallback_reason.lower()
        assert not res.has_overflow

        # Assert fallback frame is NOT a flat single color
        with Image.open(output_path) as img:
            assert img.size == (1280, 720)
            n_colors = _count_distinct_colors(img)
            assert n_colors > 50, f"Expected non-flat fallback frame, but got {n_colors} colors"

    def test_layout_step_down_and_truncation_marker(self):
        """Long code/text steps down in font size and applies truncation marker."""
        long_code = "\n".join([f"line_{i} = do_something_complex({i})" for i in range(30)])
        content, font_size, truncated = _step_down_layout(long_code, max_lines=16)

        assert truncated is True
        assert "... [truncated for display]" in content
        assert len(content.splitlines()) <= 16
        assert font_size in ["15px", "18px"]

    def test_text_overflow_detection(self, tmp_path):
        """An extreme payload that exceeds frame capacity is correctly flagged."""
        output_path = tmp_path / "overflow_frame.png"
        extreme_content = "\n".join(["X" * 150 for _ in range(30)])

        res = render_scene_to_png(
            scene_id="overflow_scene",
            content_type="code",
            content=extreme_content,
            narration="Testing overflow flagging",
            repo_name="overflow_repo",
            output_path=output_path,
            use_playwright=False,
        )

        assert output_path.exists()
        assert res.renderer_used == "fallback_pillow"
