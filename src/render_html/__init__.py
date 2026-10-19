"""
HTML frame rendering package for 1280x720 video frames.
Dispatches scene kinds to specialized renderers and wraps in the global frame shell.
"""

from __future__ import annotations

import html
from typing import Any

from .base import FONTS_DIR, get_font_css, wrap_html_shell
from .code import highlight_code_snippet, render_code_html
from .diagram import generate_svg_diagram, render_diagram_html
from .fit import render_fit_html
from .overview import render_overview_html
from .recap import render_recap_html
from .terminal import render_terminal_html
from .title import render_title_html

__all__ = [
    "FONTS_DIR",
    "get_font_css",
    "wrap_html_shell",
    "highlight_code_snippet",
    "generate_svg_diagram",
    "build_frame_html",
]


def build_frame_html(
    repo_name: str,
    scene_id: str,
    scene_kind: str,
    scene_title: str,
    content: str,
    caption: str,
    all_scene_titles: list[str],
    current_scene_idx: int,
    progress_pct: float,
    metadata: dict[str, Any] | None = None,
    active_focus: str | None = None,
    state_kind: str = "default",
    state_data: dict[str, Any] | None = None,
) -> str:
    """
    Construct complete, standalone HTML document for one video frame state.
    1280x720, zero client-side JavaScript required.
    All animations are state-driven server-side HTML.
    """
    meta = metadata or {}
    sdata = state_data or {}

    # Chapter ribbon items
    ribbon_items = []
    for i, title in enumerate(all_scene_titles):
        cls = "ribbon-item active" if i == current_scene_idx else "ribbon-item"
        ribbon_items.append(f'<span class="{cls}">{html.escape(title)}</span>')
    ribbon_html = " ".join(ribbon_items)

    # Render Center Stage
    if scene_kind == "title":
        inner_content = render_title_html(sdata, meta, repo_name, state_kind)
    elif scene_kind == "diagram":
        inner_content = render_diagram_html(sdata, meta, active_focus)
    elif scene_kind == "code":
        inner_content = render_code_html(sdata, meta, content, active_focus)
    elif scene_kind == "terminal":
        inner_content = render_terminal_html(sdata, meta, content, state_kind)
    elif scene_kind == "fit":
        inner_content = render_fit_html(sdata, meta)
    elif scene_kind == "recap":
        inner_content = render_recap_html(sdata, meta, content)
    else:
        inner_content = render_overview_html(sdata, meta, content, scene_title)

    return wrap_html_shell(
        inner_content=inner_content,
        repo_name=repo_name,
        ribbon_html=ribbon_html,
        caption=caption,
        progress_pct=progress_pct,
    )
