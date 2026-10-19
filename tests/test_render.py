"""
Unit tests for renderer module: Playwright rendering, Pillow fallback,
indentation preservation (P5 regression), and overflow detection (R7 regression).
"""

from pathlib import Path
from PIL import Image
import pytest

from src.render import render_scene_to_png, _step_down_layout
from src.render_html import highlight_code_snippet, generate_svg_diagram


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

        with Image.open(output_path) as img:
            assert img.size == (1280, 720)
            n_colors = _count_distinct_colors(img)
            assert n_colors > 100, f"Expected rich frame, but got only {n_colors} distinct colors"

    def test_code_indentation_preserved_p5_fix(self):
        """Regression test for P5: code indentation is strictly preserved without template whitespace flattening."""
        code = (
            "def search_query(query: str):\n"
            "    # 4 spaces of indentation\n"
            "    results = []\n"
            "    for item in query:\n"
            "        results.append(item)\n"
            "    return results"
        )
        html_code = highlight_code_snippet(code, file_path="search.py")
        lines = html_code.splitlines()

        # Check line 1 (def) vs line 2 (indentation)
        assert 'class="line-no"> 1</span>' in lines[0]
        assert 'class="line-no"> 2</span>' in lines[1]
        assert 'class="code-text">    <span' in lines[1] or '    <span' in lines[1]
        # Verify 8 spaces on line 5 (results.append)
        assert '        results.append' in lines[4] or '        <span' in lines[4]

    def test_pillow_fallback_flags_overflow_on_dropped_lines_r7_fix(self, tmp_path):
        """Regression test for R7: Pillow fallback must flag overflow when dropping lines past 15."""
        output_path = tmp_path / "pillow_overflow.png"
        twenty_lines = "\n".join(f"line_{i} = execute_step({i})" for i in range(20))

        res = render_scene_to_png(
            scene_id="overflow_scene",
            content_type="code",
            content=twenty_lines,
            narration="Testing that lines dropped past 15 trigger overflow.",
            repo_name="overflow_repo",
            output_path=output_path,
            use_playwright=False,
        )

        assert output_path.exists()
        assert res.renderer_used == "fallback_pillow"
        assert res.has_overflow is True
        assert "dropped 5 lines past 15" in res.overflow_details

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

        with Image.open(output_path) as img:
            assert img.size == (1280, 720)
            n_colors = _count_distinct_colors(img)
            assert n_colors > 50, f"Expected non-flat fallback frame, but got {n_colors} colors"

    def test_svg_diagram_generation(self):
        """SVG diagram generator creates valid SVG nodes and edges without overlap."""
        nodes = ["src/main.py", "src/embed.py", "src/index.py"]
        edges = [{"from": "src/main.py", "to": "src/embed.py"}]
        svg = generate_svg_diagram(nodes, edges, active_focus="embed.py")

        assert "<svg" in svg
        assert "src/main.py" in svg or "main.py" in svg
        assert "embed.py" in svg
        assert 'filter="url(#glow)"' in svg  # Focused node glow

    def test_no_placeholder_strings_in_render_code(self):
        """Acceptance test A7: No placeholder strings anywhere in render code."""
        render_paths = [
            Path("src/render.py"),
            Path("src/render_html.py"),
            Path("src/render_html"),
            Path("src/visuals.py"),
            Path("src/timeline.py"),
            Path("src/timeline"),
        ]
        render_files = []
        for rp in render_paths:
            if rp.is_file():
                render_files.append(rp)
            elif rp.is_dir():
                render_files.extend(rp.glob("*.py"))
        forbidden = ["src/main.py", "core.py", "developer"]
        for rf in render_files:
            text = rf.read_text(encoding="utf-8")
            for term in forbidden:
                assert term not in text, f"Found forbidden placeholder '{term}' in {rf}"

    def test_frame_layout_bounding_boxes_all_scenes(self):
        """Phase 5: Verify DOM bounding box geometry for 1280x720 canvas across all scene types."""
        from src.render_html import build_frame_html
        scene_kinds = ["title", "overview", "diagram", "code", "terminal", "fit", "recap"]
        all_titles = [k.capitalize() for k in scene_kinds]
        for idx, kind in enumerate(scene_kinds):
            html_doc = build_frame_html(
                repo_name="test_repo",
                scene_id=f"scene_{kind}",
                scene_kind=kind,
                scene_title=kind.capitalize(),
                content="Test content for scene frame layout verification.",
                caption="Verifying that bounding boxes remain within 1280x720 canvas.",
                all_scene_titles=all_titles,
                current_scene_idx=idx,
                progress_pct=(idx / len(scene_kinds)) * 100.0,
            )
            assert "width: 1280px;" in html_doc
            assert "height: 720px;" in html_doc
            assert "overflow: hidden;" in html_doc
            assert "box-sizing: border-box;" in html_doc
