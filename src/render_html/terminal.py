"""
Terminal scene HTML rendering with progressive typing animation and flag callouts.
"""

from __future__ import annotations

import html
from typing import Any


def render_terminal_html(
    sdata: dict[str, Any],
    meta: dict[str, Any],
    content: str,
    state_kind: str,
) -> str:
    """Render terminal window center-stage."""
    cmd_typed = sdata.get("command_display") or meta.get("command") or content.lstrip("$ ")
    cursor_vis = sdata.get("cursor_visible", True)
    cursor_html = '<span class="cursor">_</span>' if cursor_vis else '<span class="cursor-hidden">&nbsp;</span>'
    is_typing = sdata.get("is_typing", False)
    typing_pct = sdata.get("typing_pct", 0)
    typing_step = sdata.get("step", 0)
    flag_info = sdata.get("flag_callout")

    typing_status_html = ""
    if is_typing:
        typing_bgs = [
            "linear-gradient(135deg, rgba(14, 165, 233, 0.5) 0%, rgba(99, 102, 241, 0.5) 100%)",
            "linear-gradient(135deg, rgba(168, 85, 247, 0.5) 0%, rgba(236, 72, 153, 0.5) 100%)",
        ]
        b_bg = typing_bgs[typing_step % len(typing_bgs)]
        typing_status_html = f"""
        <div class="terminal-status-banner typing" style="background: {b_bg};">
          <span class="status-pulse-dot">●</span>
          <span class="status-title">SYNTHESIZING COMMAND ({typing_pct}%)</span>
          <div class="status-track"><div class="status-fill" style="width: {typing_pct}%;"></div></div>
        </div>
        """
    elif state_kind == "terminal_cursor":
        typing_status_html = """
        <div class="terminal-status-banner ready">
          <span class="status-pulse-dot static">✔</span>
          <span class="status-title">COMMAND READY</span>
          <div class="status-track"><div class="status-fill" style="width: 100%;"></div></div>
        </div>
        """

    flag_callout_html = ""
    if flag_info and isinstance(flag_info, dict):
        fl_name = html.escape(flag_info.get("flag", "RUN"))
        fl_help = html.escape(flag_info.get("help", ""))
        flag_callout_html = f"""
        <div class="terminal-callout-banner">
          <span class="term-badge">{fl_name}</span>
          <span class="term-desc">{fl_help}</span>
        </div>
        """

    sub_phase = sdata.get("sub_phase", 0)
    phase_idx = (
        (typing_step % 6)
        if is_typing
        else (sub_phase if state_kind == "terminal_callout" else (0 if state_kind == "terminal_cursor" else 3))
    )
    term_bgs = [
        "#0a101d",
        "#1c3454",
        "#0c1524",
        "#1f385a",
        "#0b1220",
        "#223e64",
    ]
    term_borders = [
        "#38bdf8",
        "#10b981",
        "#a855f7",
        "#06b6d4",
        "#f59e0b",
        "#ec4899",
    ]
    t_bg = term_bgs[phase_idx % len(term_bgs)]
    t_border = term_borders[phase_idx % len(term_borders)]
    term_cls = f"terminal-window phase-{phase_idx}"
    return f"""
    <div class="{term_cls}" style="background: {t_bg}; border: 2px solid {t_border}; box-shadow: 0 0 35px {t_border}55;">
      <div class="window-titlebar">
        <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
        <span class="filepath">bash - quickstart</span>
      </div>
      <div class="terminal-body">
        <div class="prompt-line"><span class="user-prompt">dev@workspace:~$</span> <span class="term-cmd">{html.escape(cmd_typed)}</span>{cursor_html}</div>
        {typing_status_html}
        {flag_callout_html}
      </div>
    </div>
    """
