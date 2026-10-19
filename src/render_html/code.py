"""
Code scene HTML rendering and Pygments syntax highlighting.
"""

from __future__ import annotations

import html
import os
from typing import Any

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import BashLexer, JavascriptLexer, PythonLexer, TextLexer


def highlight_code_snippet(
    code: str,
    file_path: str = "",
    focus_range: tuple[int, int] | None = None,
    caption_callout: str | None = None,
    start_line: int = 1,
) -> str:
    """
    Format source code with Pygments syntax highlighting, real token colors,
    line numbers, and focus highlighting for the active chunk.
    Long lines are wrapped at the RAW text character level into continuation rows
    with a hanging indent and '↳' marker, then highlighted with Pygments.
    No HTML tags are ever sliced or left unclosed.
    """
    ext = os.path.splitext(file_path)[1].lower() if file_path else ""
    lexer = (
        PythonLexer()
        if ext == ".py"
        else (JavascriptLexer() if ext in (".js", ".ts") else BashLexer() if ext in (".sh", ".bash") else TextLexer())
    )

    formatter = HtmlFormatter(nowrap=True)
    raw_lines = code.strip().splitlines()[:14]
    max_line_len = max((len(l) for l in raw_lines), default=0)
    need_small_font = max_line_len > 170
    max_cols = 100 if need_small_font else 85

    lines_html = []
    for idx, raw_line in enumerate(raw_lines, start=start_line):
        is_focused = True
        if focus_range is not None and focus_range[0] <= focus_range[1]:
            is_focused = (focus_range[0] <= idx <= focus_range[1])

        line_cls = "code-line active" if is_focused else "code-line dimmed"

        if len(raw_line) <= max_cols:
            hl_line = highlight(raw_line, lexer, formatter).rstrip("\n")
            lines_html.append(
                f'<div class="{line_cls}"><span class="line-no">{idx:2d}</span><span class="code-text">{hl_line}</span></div>'
            )
        else:
            indent_len = len(raw_line) - len(raw_line.lstrip(" "))
            base_indent = raw_line[:indent_len]
            hanging_indent = base_indent + "    "

            split_0 = -1
            for sep in [" ", ",", "(", "["]:
                idx_s = raw_line.rfind(sep, max(30, max_cols - 25), max_cols)
                if idx_s > split_0:
                    split_0 = idx_s + 1
            if split_0 <= 0:
                split_0 = max_cols

            chunk0 = raw_line[:split_0]
            hl0 = highlight(chunk0, lexer, formatter).rstrip("\n")
            lines_html.append(
                f'<div class="{line_cls}"><span class="line-no">{idx:2d}</span><span class="code-text">{hl0}</span></div>'
            )

            rem = raw_line[split_0:]
            avail = max(30, max_cols - len(hanging_indent) - 4)
            while rem:
                if len(rem) <= avail:
                    hl_chunk = highlight(rem, lexer, formatter).rstrip("\n")
                    lines_html.append(
                        f'<div class="{line_cls} cont-row"><span class="line-no">  </span><span class="code-text">{hanging_indent}<span class="cont-marker">↳ </span>{hl_chunk}</span></div>'
                    )
                    break
                split_c = -1
                for sep in [" ", ",", "(", "["]:
                    idx_s = rem.rfind(sep, max(15, avail - 20), avail)
                    if idx_s > split_c:
                        split_c = idx_s + 1
                if split_c <= 0:
                    split_c = avail
                chunk = rem[:split_c]
                rem = rem[split_c:]
                hl_chunk = highlight(chunk, lexer, formatter).rstrip("\n")
                lines_html.append(
                    f'<div class="{line_cls} cont-row"><span class="line-no">  </span><span class="code-text">{hanging_indent}<span class="cont-marker">↳ </span>{hl_chunk}</span></div>'
                )

    callout_html = ""
    if caption_callout:
        callout_html = f'<div class="code-callout"><span class="callout-icon">💡</span>{html.escape(caption_callout)}</div>'

    return "\n".join(lines_html) + callout_html


def render_code_html(
    sdata: dict[str, Any],
    meta: dict[str, Any],
    content: str,
    active_focus: str | None,
) -> str:
    """Render code window center-stage."""
    code_file = sdata.get("file") or meta.get("file") or ""
    code_body_text = sdata.get("code") or content
    focus_range = sdata.get("focus_range")
    caption_callout = sdata.get("caption_callout") or (
        active_focus if active_focus and not active_focus.startswith("-") else None
    )

    start_line = sdata.get("start_line", 1)
    sub_phase = sdata.get("sub_phase", 0)
    c_type = sdata.get("callout_type", "focus")
    phase_colors = {
        "setup": ("#0ea5e9", "rgba(14, 165, 233, 0.45)"),
        "flow": ("#a855f7", "rgba(168, 85, 247, 0.45)"),
        "focus": ("#10b981", "rgba(16, 185, 129, 0.45)"),
    }
    border_c, glow_c = phase_colors.get(c_type, ("#10b981", "rgba(16, 185, 129, 0.45)"))
    if sub_phase % 2 == 1:
        border_c, glow_c = ("#38bdf8", "rgba(56, 189, 248, 0.55)")

    code_body = highlight_code_snippet(
        code=code_body_text,
        file_path=code_file,
        focus_range=focus_range,
        caption_callout=caption_callout,
        start_line=start_line,
    )
    file_header = html.escape(code_file) if code_file else "Source Code"
    callout_banner = ""
    if caption_callout:
        c_badge = "AST SETUP" if c_type == "setup" else ("AST FLOW" if c_type == "flow" else "AST FOCUS")
        c_gradients = {
            "setup": "linear-gradient(135deg, rgba(6, 182, 212, 0.4) 0%, rgba(59, 130, 246, 0.5) 100%)",
            "flow": "linear-gradient(135deg, rgba(168, 85, 247, 0.4) 0%, rgba(99, 102, 241, 0.5) 100%)",
            "focus": "linear-gradient(135deg, rgba(16, 185, 129, 0.4) 0%, rgba(20, 184, 166, 0.5) 100%)",
        }
        c_bg = c_gradients.get(c_type, c_gradients["focus"])
        callout_banner = f"""
        <div class="code-callout-banner" style="background: {c_bg};">
          <span class="callout-badge">{c_badge}</span>
          <span class="callout-text">{html.escape(caption_callout)}</span>
        </div>
        """
    code_bgs = [
        "#090d16",
        "#14243b",
        "#23183d",
        "#0e2b33",
        "#281a38",
    ]
    type_bg_map = {
        "setup": "#09101f",
        "flow": "#1e375c",
        "focus": "#162842",
    }
    c_win_bg = "#1e375c" if sub_phase % 2 == 1 else type_bg_map.get(c_type, code_bgs[sub_phase % len(code_bgs)])
    is_small = any(len(l) > 170 for l in code_body_text.strip().splitlines()[:14])
    small_cls = " small-code" if is_small else ""
    code_cls = f"code-window phase-{c_type} subphase-{sub_phase}{small_cls}"
    return f"""
    <div class="{code_cls}" style="background: {c_win_bg}; border: 2px solid {border_c}; box-shadow: 0 0 35px {glow_c};">
      <div class="window-titlebar">
        <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
        <span class="filepath">{file_header}</span>
      </div>
      {callout_banner}
      <pre class="code-pre"><code>{code_body}</code></pre>
    </div>
    """
