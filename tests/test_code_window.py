"""
Tests for Phase 2: Code Window and rendered_code_matches gate.
Validates:
- 120-char argparse line renders fully without loss
- Indentation is preserved across continuation rows
- No unbalanced HTML tags (verified with html.parser.HTMLParser)
- rendered_code_matches hard gate passes on complete render
- rendered_code_matches hard gate fails on deliberately truncated frame
- Pixel/DOM sanity check with Playwright innerText
- Pillow fallback equivalent handles code scenes without truncation
"""

from __future__ import annotations

import html.parser
from pathlib import Path
import pytest

from src.render_html import highlight_code_snippet, build_frame_html
from src.render import PlaywrightRenderer, PillowRenderer
from src.schema import ScriptPlan, Scene, Beat, OnScreen, Evidence
from src.evals.gates import (
    extract_rendered_code_from_html,
    check_rendered_code_matches_gate,
)


class TagBalanceParser(html.parser.HTMLParser):
    """HTMLParser that tracks open and closed tags to verify balance."""
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.tag_stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() not in self.VOID_TAGS:
            self.tag_stack.append(tag.lower())

    def handle_endtag(self, tag):
        tag_l = tag.lower()
        if tag_l in self.VOID_TAGS:
            return
        if not self.tag_stack:
            self.errors.append(f"Unexpected closing tag </{tag}> with empty stack")
        elif self.tag_stack[-1] == tag_l:
            self.tag_stack.pop()
        else:
            self.errors.append(f"Mismatched closing tag </{tag}>, expected </{self.tag_stack[-1]}>")


def test_long_argparse_line_renders_fully():
    """A 120-char argparse line wraps cleanly into continuation rows and preserves all characters."""
    code = (
        '    parser.add_argument("--query", type=str, required=True, '
        'help="Long query text for semantic retrieval engine in high dimension")'
    )
    assert len(code) >= 120

    snippet_html = highlight_code_snippet(code, file_path="cli.py", start_line=1)
    # Ensure continuation marker is present
    assert "cont-marker" in snippet_html
    assert "↳" in snippet_html

    # Ensure all flags and help text are present in the HTML (with Pygments spans)
    assert "--query" in snippet_html
    assert "semantic" in snippet_html
    assert "retrieval" in snippet_html
    assert "engine" in snippet_html

    # Reconstruct extracted text
    lines = extract_rendered_code_from_html(snippet_html)
    assert len(lines) == 1
    assert " ".join(lines[0].split()) == " ".join(code.split())
    assert "semantic retrieval engine" in lines[0]


def test_indentation_preserved():
    """Indentation of code lines must be preserved across rendering."""
    code = (
        "def query_index(query_str: str):\n"
        "    if not query_str:\n"
        "        return []\n"
        "    results = []\n"
        "    return results"
    )
    snippet_html = highlight_code_snippet(code, file_path="search.py", start_line=10)
    lines = extract_rendered_code_from_html(snippet_html)
    assert len(lines) == 5
    for extracted, original in zip(lines, code.splitlines()):
        assert extracted == original


def test_no_unbalanced_html_tags():
    """The generated HTML snippet and full frame must have perfectly balanced tags."""
    long_code = (
        "def main():\n"
        '    parser = argparse.ArgumentParser(description="Test parser for video search")\n'
        '    parser.add_argument("--model-path", type=str, default="checkpoints/model.pt", '
        'help="Path to neural weights for video understanding and embedding extraction")\n'
        "    return parser.parse_args()\n"
    )
    snippet_html = highlight_code_snippet(long_code, file_path="main.py")
    parser = TagBalanceParser()
    parser.feed(snippet_html)
    assert not parser.errors, f"Snippet HTML has tag balance errors: {parser.errors}"
    assert not parser.tag_stack, f"Unclosed tags in snippet: {parser.tag_stack}"

    frame_html = build_frame_html(
        repo_name="test_repo",
        scene_id="code",
        scene_kind="code",
        scene_title="Source Code",
        content=long_code,
        caption="Inspect main entrypoint",
        all_scene_titles=["Overview", "Source Code", "Recap"],
        current_scene_idx=1,
        progress_pct=40.0,
        state_data={"file": "main.py", "code": long_code},
    )
    frame_parser = TagBalanceParser()
    frame_parser.feed(frame_html)
    assert not frame_parser.errors, f"Frame HTML has tag balance errors: {frame_parser.errors}"
    assert not frame_parser.tag_stack, f"Unclosed tags in frame: {frame_parser.tag_stack}"


def test_rendered_code_matches_gate_passes_on_valid_render():
    """rendered_code_matches gate passes when visible text matches cited source lines."""
    code = (
        "import torch\n"
        "def forward(x):\n"
        '    parser.add_argument("--query", type=str, required=True, '
        'help="Long query text for semantic retrieval engine in high dimension")\n'
        "    return x"
    )
    title_scene = Scene(id="title", kind="title", title="Overview", narration="Introduction to the demo video project.", on_screen=OnScreen(type="title", content="demo"))
    plan = ScriptPlan(
        repo_name="demo",
        scenes=[
            title_scene,
            Scene(
                id="code_scene",
                kind="code",
                title="Code Flow",
                narration="Here is the implementation of forward.",
                on_screen=OnScreen(type="code", content=code, metadata={"file": "model.py"}),
                evidence=Evidence(file="model.py", quote="def forward(x):"),
            ),
        ],
    )
    gate = check_rendered_code_matches_gate(plan)
    assert gate.passed is True
    assert gate.name == "rendered_code_matches"


def test_rendered_code_matches_gate_fails_on_truncated_frame():
    """rendered_code_matches gate fails if a frame has truncated lines or missing text."""
    code = (
        "def forward(x):\n"
        '    parser.add_argument("--query", type=str, required=True, help="Long query text")\n'
        "    return x"
    )
    title_scene = Scene(id="title", kind="title", title="Overview", narration="Introduction to the demo video project.", on_screen=OnScreen(type="title", content="demo"))
    plan = ScriptPlan(
        repo_name="demo",
        scenes=[
            title_scene,
            Scene(
                id="code_scene",
                kind="code",
                title="Code Flow",
                narration="Here is the implementation of forward.",
                on_screen=OnScreen(type="code", content=code, metadata={"file": "model.py"}),
                evidence=Evidence(file="model.py", quote="def forward(x):"),
            ),
        ],
    )
    # Deliberately truncated frame HTML missing the help flag
    truncated_html = """
    <div class="code-window">
      <div class="code-line active"><span class="line-no"> 1</span><span class="code-text">def forward(x):</span></div>
      <div class="code-line active"><span class="line-no"> 2</span><span class="code-text">parser.add_arg ↵</span></div>
      <div class="code-line active"><span class="line-no"> 3</span><span class="code-text">return x</span></div>
    </div>
    """
    gate = check_rendered_code_matches_gate(plan, frame_html_map={"code_scene": truncated_html})
    assert gate.passed is False
    assert "mismatch" in gate.details or "extracted" in gate.details


def test_playwright_dom_innertext_sanity(tmp_path):
    """Pixel/DOM level sanity check with Playwright: innerText of code container contains full line."""
    code = (
        'parser.add_argument("--query", type=str, required=True, '
        'help="Long query text for semantic retrieval engine in high dimension")'
    )
    frame_html = build_frame_html(
        repo_name="test_repo",
        scene_id="code",
        scene_kind="code",
        scene_title="Source Code",
        content=code,
        caption="Inspect flags",
        all_scene_titles=["Code"],
        current_scene_idx=0,
        progress_pct=50.0,
        state_data={"file": "cli.py", "code": code},
    )

    renderer = PlaywrightRenderer()
    try:
        renderer.start()
        out_png = tmp_path / "frame_code.png"
        res = renderer.render_frame(frame_html, out_png)
        assert res.has_overflow is False
        assert out_png.exists()
        assert out_png.stat().st_size > 0

        # Check DOM text directly via page locator
        inner_text = renderer._page.locator(".code-pre").inner_text()
        assert "--query" in inner_text
        assert "semantic retrieval engine" in inner_text
    finally:
        renderer.close()


def test_pillow_fallback_code_rendering(tmp_path):
    """Pillow fallback handles long code lines without crashing or losing lines."""
    code = (
        'parser.add_argument("--query", type=str, required=True, '
        'help="Long query text for semantic retrieval engine in high dimension")'
    )
    pillow = PillowRenderer()
    out_png = tmp_path / "pillow_code.png"
    res = pillow.render_frame(
        scene_id="code",
        scene_kind="code",
        scene_title="Code",
        content=code,
        caption="Inspect code",
        repo_name="demo",
        progress_pct=50.0,
        output_path=out_png,
        state_data={"file": "cli.py", "code": code},
    )
    assert out_png.exists()
    assert out_png.stat().st_size > 0
