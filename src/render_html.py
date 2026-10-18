"""
HTML template generation for 1280x720 explainer video frames.

Includes:
- Vendored font imports (Inter and JetBrains Mono)
- Modern dark gradient background (#0b0f19 to #111827)
- Top chapter ribbon with active scene pill
- Top-right repo identity badge
- Inline SVG architecture diagram (<= 8 nodes, call order reveal, active node glowing)
- Pygments syntax-highlighted code with token colors, line numbers, chunk highlighting, and callout
- Terminal shell quickstart card with typed command animation and cursor states
- Bottom glassmorphic caption card (<= 22 words)
- Bottom animated progress bar (0.0% to 100.0%)
- Zero placeholder defaults anywhere in render code
"""

from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer, JavascriptLexer, BashLexer, TextLexer

FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"


def _get_font_css() -> str:
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


def generate_svg_diagram(
    nodes: list[str],
    edges: list[dict[str, str]],
    active_focus: str | None = None,
    visible_count: int | None = None,
    overflow_count: int = 0,
) -> str:
    """
    Generate inline SVG architecture map.
    Nodes are revealed in call order up to visible_count.
    The active focus node is highlighted with glowing cyan border and halo.
    Previously visited nodes remain lit.
    Edges draw between revealed nodes.
    """
    svg_w, svg_h = 1000, 340
    box_w, box_h = 210, 48

    disp_nodes = nodes[:8]
    n_visible = visible_count if visible_count is not None else len(disp_nodes)
    n_visible = max(1, min(len(disp_nodes), n_visible))

    cols = min(4, max(1, len(disp_nodes)))
    spacing_x = svg_w // max(1, cols)
    start_x = 20

    coords: dict[str, tuple[int, int]] = {}
    for i, node in enumerate(disp_nodes):
        row = i // cols
        col = i % cols
        x = start_x + col * spacing_x
        y = 50 + row * 110
        coords[node] = (x, y)

    elements = [
        """
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#818cf8" />
        </marker>
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="#38bdf8" flood-opacity="0.8"/>
        </filter>
      </defs>
    """
    ]

    # Draw edges between visible nodes
    visible_set = set(disp_nodes[:n_visible])
    for e in edges:
        src = e.get("source") or e.get("from", "")
        dst = e.get("target") or e.get("to", "")
        if src in coords and dst in coords and src in visible_set and dst in visible_set:
            x1, y1 = coords[src]
            x2, y2 = coords[dst]
            c_x1, c_y1 = x1 + box_w // 2, y1 + box_h
            c_x2, c_y2 = x2 + box_w // 2, y2
            elements.append(
                f'<path d="M {c_x1} {c_y1} C {c_x1} {(c_y1+c_y2)//2}, {c_x2} {(c_y1+c_y2)//2}, {c_x2} {c_y2}" '
                f'stroke="#6366f1" stroke-width="2.5" fill="none" marker-end="url(#arrow)" />'
            )

    # Draw node boxes
    for idx, node in enumerate(disp_nodes):
        if idx >= n_visible:
            continue
        x, y = coords[node]
        is_active = (active_focus and (active_focus == node or active_focus in node or node in active_focus)) or (idx == n_visible - 1)
        border_color = "#38bdf8" if is_active else "#64748b"
        fill_color = "rgba(14, 165, 233, 0.22)" if is_active else "rgba(30, 41, 59, 0.85)"
        filter_str = 'filter="url(#glow)"' if is_active else ""
        short_name = os.path.basename(node)

        elements.append(
            f'<g {filter_str}>'
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="8" fill="{fill_color}" stroke="{border_color}" stroke-width="{3 if is_active else 1.5}"/>'
            f'<text x="{x + box_w//2}" y="{y + box_h//2 + 5}" text-anchor="middle" fill="#f8fafc" font-size="13" font-weight="{600 if is_active else 400}" font-family="JetBrains Mono, monospace">{html.escape(short_name)}</text>'
            f'</g>'
        )

    # Overflow indicator if > 8 nodes
    if overflow_count > 0:
        ox, oy = start_x + (cols - 1) * spacing_x, 50 + 110
        elements.append(
            f'<g>'
            f'<rect x="{ox + box_w - 70}" y="{oy + box_h + 10}" width="70" height="24" rx="12" fill="#334155" stroke="#94a3b8" stroke-width="1"/>'
            f'<text x="{ox + box_w - 35}" y="{oy + box_h + 26}" text-anchor="middle" fill="#e2e8f0" font-size="11" font-family="Inter, sans-serif">+{overflow_count} more</text>'
            f'</g>'
        )

    return f'<svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg">{"".join(elements)}</svg>'


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
    lexer = PythonLexer() if ext == ".py" else (JavascriptLexer() if ext in (".js", ".ts") else BashLexer() if ext in (".sh", ".bash") else TextLexer())

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

            # Clean split for row 0
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

            # Continuation rows
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
    font_css = _get_font_css()

    # Chapter ribbon items
    ribbon_items = []
    for i, title in enumerate(all_scene_titles):
        cls = "ribbon-item active" if i == current_scene_idx else "ribbon-item"
        ribbon_items.append(f'<span class="{cls}">{html.escape(title)}</span>')
    ribbon_html = " ".join(ribbon_items)

    # -------------------------------------------------------------------
    # Render Center Stage by Scene Kind & Animation State
    # -------------------------------------------------------------------
    if scene_kind == "title":
        title_text = html.escape(sdata.get("title") or meta.get("title") or meta.get("repo") or repo_name)
        owner_val = sdata.get("owner") or meta.get("owner")
        owner_html = ""
        if owner_val:
            owner_html = f'<div class="hero-subtitle">Developed by <span class="accent">{html.escape(str(owner_val))}</span></div>'
        lang_text = sdata.get("chip") or meta.get("language") or ""
        lang_chip_html = f'<div class="lang-chip">{html.escape(lang_text)}</div>' if lang_text else ""
        tagline_val = sdata.get("tagline") or meta.get("tagline") or ""
        tagline_html = f'<div class="summary-badge">{html.escape(tagline_val)}</div>' if tagline_val else ""

        # Progressive reveal:
        # title_chip: chip only
        # title_header: chip + title
        # title_full: chip + title + owner + tagline
        if state_kind == "title_chip":
            inner_content = f"""
            <div class="title-card">
              {lang_chip_html}
            </div>
            """
        elif state_kind == "title_header":
            inner_content = f"""
            <div class="title-card">
              {lang_chip_html}
              <h1 class="hero-title">{title_text}</h1>
            </div>
            """
        else:
            sub_phase = sdata.get("sub_phase", 0)
            phase_borders = ["#38bdf8", "#a855f7", "#10b981", "#f59e0b"]
            title_bgs = [
                "rgba(15, 23, 42, 0.9)",
                "rgba(19, 39, 72, 0.95)",
                "rgba(42, 25, 72, 0.95)",
                "rgba(14, 46, 54, 0.95)",
            ]
            border_c = phase_borders[sub_phase % len(phase_borders)]
            t_bg = title_bgs[sub_phase % len(title_bgs)]
            glows = [
                "0 0 25px rgba(56, 189, 248, 0.4)",
                "0 0 40px rgba(168, 85, 247, 0.45)",
                "0 0 35px rgba(16, 185, 129, 0.45)",
                "0 0 35px rgba(245, 158, 11, 0.45)",
            ]
            glow = glows[sub_phase % len(glows)]
            inner_content = f"""
            <div class="title-card phase-{sub_phase}" style="background: {t_bg}; border: 1px solid {border_c}; border-radius: 16px; padding: 32px 40px; box-shadow: {glow};">
              {lang_chip_html}
              <h1 class="hero-title">{title_text}</h1>
              {owner_html}
              {tagline_html}
            </div>
            """

    elif scene_kind == "diagram":
        nodes = sdata.get("nodes") or meta.get("nodes") or []
        edges = sdata.get("edges") or meta.get("edges") or []
        vis_count = sdata.get("visible_nodes_count")
        active_node = sdata.get("active_node") or active_focus
        overflow_count = sdata.get("overflow_count", 0)

        svg_diagram = generate_svg_diagram(
            nodes=nodes,
            edges=edges,
            active_focus=active_node,
            visible_count=vis_count,
            overflow_count=overflow_count,
        )
        inner_content = f"""
        <div class="diagram-container">
          <div class="card-header">Module Call Flow & Architecture</div>
          {svg_diagram}
        </div>
        """

    elif scene_kind == "code":
        code_file = sdata.get("file") or meta.get("file") or ""
        code_body_text = sdata.get("code") or content
        focus_range = sdata.get("focus_range")
        caption_callout = sdata.get("caption_callout") or (active_focus if active_focus and not active_focus.startswith("-") else None)

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
            "focus": "#0c1524",
        }
        c_win_bg = type_bg_map.get(c_type, code_bgs[sub_phase % len(code_bgs)])
        is_small = any(len(l) > 170 for l in code_body_text.strip().splitlines()[:14])
        small_cls = " small-code" if is_small else ""
        code_cls = f"code-window phase-{c_type} subphase-{sub_phase}{small_cls}"
        inner_content = f"""
        <div class="{code_cls}" style="background: {c_win_bg}; border: 2px solid {border_c}; box-shadow: 0 0 35px {glow_c};">
          <div class="window-titlebar">
            <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
            <span class="filepath">{file_header}</span>
          </div>
          {callout_banner}
          <pre class="code-pre"><code>{code_body}</code></pre>
        </div>
        """

    elif scene_kind == "terminal":
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

        phase_idx = (typing_step % 6) if is_typing else (0 if state_kind == "terminal_cursor" else 3)
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
        inner_content = f"""
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

    elif scene_kind == "fit":
        stages = sdata.get("stages") or list(meta.get("pipeline_stages", {}).keys())
        active_stage = sdata.get("active_stage")
        evidence_line = sdata.get("evidence_line") or ""
        mode = sdata.get("mode", "pipeline")

        if stages and mode != "announcement" and mode != "artifacts":
            stage_cards = []
            for st in stages:
                is_active = (st == active_stage)
                cls = "stage-box active" if is_active else "stage-box"
                stage_cards.append(f'<div class="{cls}"><span class="stage-name">{html.escape(st.upper())}</span></div>')

            ev_html = ""
            if evidence_line:
                ev_html = f'<div class="evidence-box"><span class="ev-badge">EVIDENCE</span> {html.escape(evidence_line[:120])}</div>'

            active_banner_html = ""
            if active_stage:
                stage_gradients = {
                    "decode": "linear-gradient(135deg, rgba(6, 182, 212, 0.45) 0%, rgba(59, 130, 246, 0.45) 100%)",
                    "embed": "linear-gradient(135deg, rgba(168, 85, 247, 0.45) 0%, rgba(99, 102, 241, 0.45) 100%)",
                    "index": "linear-gradient(135deg, rgba(16, 185, 129, 0.45) 0%, rgba(20, 184, 166, 0.45) 100%)",
                    "query": "linear-gradient(135deg, rgba(245, 158, 11, 0.45) 0%, rgba(244, 63, 94, 0.45) 100%)",
                    "serve": "linear-gradient(135deg, rgba(139, 92, 246, 0.45) 0%, rgba(217, 70, 239, 0.45) 100%)",
                }
                st_bg = stage_gradients.get(active_stage.lower(), "linear-gradient(135deg, rgba(14, 165, 233, 0.35) 0%, rgba(99, 102, 241, 0.45) 100%)")
                active_banner_html = f"""
                <div class="active-stage-banner" style="background: {st_bg};">
                  <span class="active-stage-tag">ACTIVE STAGE</span>
                  <span class="active-stage-title">{html.escape(active_stage.upper())}</span>
                </div>
                """

            stage_cls = f"stage-{html.escape(active_stage.lower())}" if active_stage else "stage-default"
            inner_content = f"""
            <div class="fit-card {stage_cls}">
              <h2 class="card-title">Multimodal Pipeline Grounding</h2>
              <div class="stages-track">{'<span class="stage-arrow">→</span>'.join(stage_cards)}</div>
              {active_banner_html}
              {ev_html}
            </div>
            """
        elif mode == "announcement":
            sub_phase = sdata.get("sub_phase", 0)
            phase_styles = [
                ("border: 2px solid #38bdf8; box-shadow: 0 0 35px rgba(56, 189, 248, 0.55); background: rgba(14, 38, 68, 0.95);", "rgba(56, 189, 248, 0.25)", "#38bdf8", "SCOPE: GENERAL PACKAGE"),
                ("border: 2px solid #a855f7; box-shadow: 0 0 35px rgba(168, 85, 247, 0.55); background: rgba(38, 18, 62, 0.95);", "rgba(168, 85, 247, 0.25)", "#a855f7", "STANDARD RUNTIME UTILITY"),
                ("border: 2px solid #10b981; box-shadow: 0 0 35px rgba(16, 185, 129, 0.55); background: rgba(12, 44, 40, 0.95);", "rgba(16, 185, 129, 0.25)", "#10b981", "DOWNSTREAM PIPELINE READY"),
            ]
            st_card, st_bg, st_color, st_tag = phase_styles[sub_phase % len(phase_styles)]
            inner_content = f"""
            <div class="fit-card phase-{sub_phase}" style="{st_card}">
              <h2 class="card-title">Domain Scope & Applicability</h2>
              <div class="general-scope-banner" style="background: {st_bg}; border-left: 5px solid {st_color};">
                <span class="scope-tag" style="background: {st_color}; color: #0f172a; font-weight: 800;">{st_tag}</span>
                <p class="fit-desc" style="margin-top: 10px;">Repository does not specialize in video understanding; standard software package.</p>
              </div>
            </div>
            """
        else:
            files = sdata.get("files") or ["transcript.vtt", "chapters.json", "index.jsonl"]
            sub_phase = sdata.get("sub_phase", 0)
            rev_n = min(len(files), sub_phase + 1)
            files_html = "".join(
                f'<div class="artifact-pill {"active" if idx < rev_n else "pending"}" style="border-color: {"#38bdf8" if idx < rev_n else "#475569"}; background: {"rgba(14, 165, 233, 0.35)" if idx < rev_n else "rgba(30, 41, 59, 0.4)"}; color: {"#38bdf8" if idx < rev_n else "#64748b"}; font-weight: {"700" if idx < rev_n else "400"};">📄 {html.escape(f)}</div>'
                for idx, f in enumerate(files)
            )
            fit_bgs = ["rgba(15, 23, 42, 0.9)", "rgba(16, 38, 70, 0.95)", "rgba(40, 20, 65, 0.95)"]
            fit_bg = fit_bgs[sub_phase % len(fit_bgs)]
            border_c = "#38bdf8" if sub_phase % 2 == 0 else "#a855f7"
            inner_content = f"""
            <div class="fit-card phase-{sub_phase}" style="background: {fit_bg}; border: 2px solid {border_c}; box-shadow: 0 0 35px {border_c}55;">
              <h2 class="card-title">Structured Retrieval Package</h2>
              <p class="fit-desc">Generated assets for downstream search and multimodal indexing:</p>
              <div class="artifacts-row">{files_html}</div>
            </div>
            """

    elif scene_kind == "recap":
        takeaways = sdata.get("takeaways") or meta.get("takeaways") or content.splitlines()
        rev_count = sdata.get("revealed_count", len(takeaways))
        start_file = sdata.get("start_file") or meta.get("start_file") or ""
        highlight_start = sdata.get("highlight_start", False)
        sub_phase = sdata.get("sub_phase", 0)

        items_html = []
        for i, t in enumerate(takeaways[:3]):
            if i < rev_count:
                items_html.append(
                    f'<li class="takeaway-item active"><span class="item-badge">{i+1}</span>{html.escape(t.lstrip("123456789. "))}</li>'
                )

        start_card_html = ""
        if start_file and highlight_start:
            start_card_html = f'<div class="start-file-card"><span class="start-label">Start Here:</span> <code class="start-code">{html.escape(start_file)}</code></div>'

        recap_bgs = [
            "rgba(15, 23, 42, 0.9)",
            "rgba(18, 38, 70, 0.95)",
            "rgba(40, 22, 70, 0.95)",
            "rgba(14, 45, 52, 0.95)",
        ]
        r_bg = recap_bgs[sub_phase % len(recap_bgs)]
        border_c = "#38bdf8" if sub_phase % 2 == 0 else "#a855f7"
        inner_content = f"""
        <div class="recap-card phase-{sub_phase}" style="background: {r_bg}; border: 1px solid {border_c}; box-shadow: 0 0 25px {border_c}40;">
          <h2 class="card-title">Key Takeaways</h2>
          <ul class="takeaway-list">{''.join(items_html)}</ul>
          {start_card_html}
        </div>
        """

    else:  # overview or general
        points = sdata.get("points") or meta.get("points") or [content[:120]]
        rev_count = sdata.get("revealed_count", len(points))
        sub_phase = sdata.get("sub_phase", 0)
        items_html = []
        for i, p in enumerate(points[:3]):
            if i < rev_count:
                is_active = (i == rev_count - 1)
                cls = "overview-point active" if is_active else "overview-point"
                pulse_color = "#38bdf8" if sub_phase % 2 == 0 else "#a855f7"
                items_html.append(f'<div class="{cls}"><span class="point-bullet" style="color: {pulse_color};">✦</span>{html.escape(p)}</div>')

        ov_bgs = [
            "rgba(15, 23, 42, 0.9)",
            "rgba(18, 38, 70, 0.95)",
            "rgba(40, 22, 70, 0.95)",
            "rgba(14, 45, 52, 0.95)",
        ]
        ov_bg = ov_bgs[sub_phase % len(ov_bgs)]
        border_c = "#38bdf8" if sub_phase % 2 == 0 else "#6366f1"
        inner_content = f"""
        <div class="overview-card phase-{sub_phase}" style="background: {ov_bg}; border: 1px solid {border_c}; box-shadow: 0 0 25px {border_c}40;">
          <h2 class="card-title">{html.escape(scene_title or "Overview")}</h2>
          <div class="points-container">{''.join(items_html)}</div>
        </div>
        """

    caption_clean = html.escape(caption[:140])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  {font_css}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1280px;
    height: 720px;
    background: radial-gradient(circle at 50% 20%, #1e1b4b 0%, #0f172a 60%, #020617 100%);
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    color: #f8fafc;
    overflow: hidden;
    position: relative;
    padding: 24px 48px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}
  .top-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 38px;
  }}
  .chapter-ribbon {{
    display: flex;
    gap: 8px;
    background: rgba(15, 23, 42, 0.65);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 20px;
    padding: 4px 12px;
  }}
  .ribbon-item {{
    font-size: 12px;
    font-weight: 500;
    color: #94a3b8;
    padding: 2px 8px;
    border-radius: 12px;
  }}
  .ribbon-item.active {{
    background: #4f46e5;
    color: #ffffff;
    font-weight: 600;
  }}
  .repo-badge {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    background: rgba(30, 41, 59, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.15);
    padding: 6px 14px;
    border-radius: 16px;
    color: #e2e8f0;
  }}
  .center-stage {{
    height: 520px;
    max-height: 520px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }}
  .title-card {{
    text-align: center;
  }}
  .lang-chip {{
    display: inline-block;
    background: #0ea5e9;
    color: #030712;
    font-weight: 700;
    font-size: 12px;
    padding: 4px 12px;
    border-radius: 12px;
    margin-bottom: 16px;
    text-transform: uppercase;
    letter-spacing: 1px;
  }}
  .hero-title {{
    font-size: 54px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -1px;
    margin-bottom: 12px;
  }}
  .hero-subtitle {{
    font-size: 20px;
    color: #94a3b8;
    margin-bottom: 24px;
  }}
  .accent {{ color: #38bdf8; font-weight: 600; }}
  .summary-badge {{
    display: inline-block;
    border: 1px solid rgba(148, 163, 184, 0.3);
    padding: 8px 18px;
    border-radius: 20px;
    color: #cbd5e1;
    font-size: 14px;
  }}
  .code-window, .terminal-window {{
    width: 1060px;
    background: #090d16;
    border: 1px solid #1e293b;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6);
  }}
  .code-window.phase-setup {{
    border: 2px solid #0ea5e9;
    box-shadow: 0 0 35px rgba(14, 165, 233, 0.45);
  }}
  .code-window.phase-flow {{
    border: 2px solid #a855f7;
    box-shadow: 0 0 35px rgba(168, 85, 247, 0.45);
  }}
  .code-window.phase-focus {{
    border: 2px solid #10b981;
    box-shadow: 0 0 35px rgba(16, 185, 129, 0.45);
  }}
  .terminal-window.phase-0 {{
    border: 2px solid #38bdf8;
    box-shadow: 0 0 35px rgba(56, 189, 248, 0.45);
  }}
  .terminal-window.phase-1 {{
    border: 2px solid #10b981;
    box-shadow: 0 0 35px rgba(16, 185, 129, 0.45);
  }}
  .terminal-window.phase-2 {{
    border: 2px solid #818cf8;
    box-shadow: 0 0 35px rgba(129, 140, 248, 0.45);
  }}
  .terminal-window.phase-3 {{
    border: 2px solid #f59e0b;
    box-shadow: 0 0 35px rgba(245, 158, 11, 0.45);
  }}
  .window-titlebar {{
    background: #111827;
    height: 32px;
    display: flex;
    align-items: center;
    padding: 0 14px;
    gap: 8px;
    border-bottom: 1px solid #1f2937;
  }}
  .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .dot.red {{ background: #ef4444; }}
  .dot.yellow {{ background: #f59e0b; }}
  .dot.green {{ background: #10b981; }}
  .filepath {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: #94a3b8;
    margin-left: 8px;
  }}
  .code-pre {{
    padding: 16px 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    line-height: 1.25;
    color: #e2e8f0;
    overflow: hidden;
  }}
  .code-window.small-code .code-pre {{
    font-size: 13px;
    line-height: 1.2;
  }}
  .code-line {{ display: flex; gap: 14px; transition: opacity 0.2s; }}
  .code-line.active {{ background: rgba(56, 189, 248, 0.14); border-radius: 4px; padding-left: 4px; }}
  .code-line.active .line-no {{ color: #94a3b8; font-weight: 600; }}
  .code-line.dimmed {{ opacity: 0.38; }}
  .code-line.dimmed .line-no {{ color: #475569; }}
  .line-no {{ color: #475569; user-select: none; width: 24px; text-align: right; flex-shrink: 0; }}
  .code-text {{ white-space: pre; font-family: 'JetBrains Mono', monospace; }}
  .cont-marker {{ color: #38bdf8; font-weight: 700; }}
  .code-callout {{
    margin: 12px 20px 16px;
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(56, 189, 248, 0.3);
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 13px;
    color: #38bdf8;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .code-callout-banner {{
    margin: 10px 20px 14px;
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.35) 0%, rgba(99, 102, 241, 0.45) 100%);
    border: 1px solid #38bdf8;
    border-radius: 8px;
    padding: 10px 18px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 0 15px rgba(56, 189, 248, 0.25);
  }}
  .callout-badge {{
    background: #0284c7;
    color: #fff;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
  }}
  .callout-text {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    color: #ffffff;
    font-weight: 600;
  }}
  .terminal-status-banner {{
    margin-top: 20px;
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 8px;
    padding: 10px 18px;
    display: flex;
    align-items: center;
    gap: 14px;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
  }}
  .terminal-status-banner.typing {{
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.25) 0%, rgba(99, 102, 241, 0.25) 100%);
    border-color: #38bdf8;
  }}
  .terminal-status-banner.ready {{
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.25) 0%, rgba(20, 184, 166, 0.25) 100%);
    border-color: #10b981;
  }}
  .status-pulse-dot {{ color: #38bdf8; font-size: 16px; font-weight: 700; }}
  .status-pulse-dot.static {{ color: #10b981; }}
  .status-title {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    font-weight: 700;
    color: #e2e8f0;
    min-width: 230px;
    letter-spacing: 0.5px;
  }}
  .status-track {{
    flex: 1;
    height: 10px;
    background: rgba(30, 41, 59, 0.7);
    border-radius: 5px;
    overflow: hidden;
    border: 1px solid rgba(255, 255, 255, 0.1);
  }}
  .status-fill {{
    height: 100%;
    background: linear-gradient(90deg, #10b981, #38bdf8);
    border-radius: 5px;
    box-shadow: 0 0 10px rgba(56, 189, 248, 0.5);
  }}
  .terminal-callout-banner {{
    margin-top: 18px;
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.3) 0%, rgba(6, 182, 212, 0.4) 100%);
    border: 1px solid #10b981;
    border-radius: 8px;
    padding: 10px 18px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 0 15px rgba(16, 185, 129, 0.2);
  }}
  .term-badge {{
    background: #059669;
    color: #fff;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
  }}
  .term-desc {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    color: #ffffff;
  }}
  /* Pygments syntax token styling */
  .c, .c1, .ch {{ color: #64748b; font-style: italic; }}
  .k, .kn, .kd {{ color: #f43f5e; font-weight: 600; }}
  .s, .s1, .s2 {{ color: #10b981; }}
  .nf {{ color: #38bdf8; font-weight: 600; }}
  .nc {{ color: #a855f7; font-weight: 600; }}
  .nb {{ color: #06b6d4; }}
  .nn {{ color: #cbd5e1; }}
  .o, .ow {{ color: #94a3b8; }}
  .mi, .mf {{ color: #fbbf24; }}
  .terminal-body {{
    padding: 24px 30px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 17px;
    color: #f1f5f9;
  }}
  .user-prompt {{ color: #10b981; font-weight: 600; margin-right: 8px; }}
  .cursor {{ color: #38bdf8; font-weight: 700; }}
  .cursor-hidden {{ visibility: hidden; }}
  .flag-callout {{
    margin-top: 20px;
    background: rgba(30, 41, 59, 0.7);
    border: 1px solid rgba(56, 189, 248, 0.25);
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .flag-badge {{ background: #4f46e5; color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
  .flag-desc {{ color: #cbd5e1; }}
  .overview-card, .recap-card, .diagram-container, .fit-card {{
    width: 1060px;
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 32px 40px;
  }}
  .card-title, .card-header {{
    font-size: 26px;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 20px;
  }}
  .overview-point {{
    font-size: 18px;
    line-height: 1.6;
    color: #cbd5e1;
    margin-bottom: 14px;
    display: flex;
    gap: 12px;
    border-radius: 8px;
    padding: 8px 12px;
  }}
  .overview-point.active {{
    background: rgba(56, 189, 248, 0.12);
    border-left: 3px solid #38bdf8;
    color: #ffffff;
  }}
  .point-bullet {{ color: #6366f1; font-weight: 700; }}
  .stages-track {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 24px 0;
  }}
  .stage-box {{
    background: rgba(30, 41, 59, 0.7);
    border: 1px solid #475569;
    border-radius: 8px;
    padding: 12px 18px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    color: #94a3b8;
  }}
  .stage-box.active {{
    border-color: #38bdf8;
    background: rgba(14, 165, 233, 0.25);
    color: #38bdf8;
    box-shadow: 0 0 15px rgba(56, 189, 248, 0.4);
    font-weight: 700;
  }}
  .stage-arrow {{ color: #64748b; font-size: 18px; }}
  .evidence-box {{
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    padding: 10px 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: #cbd5e1;
  }}
  .active-stage-banner {{
    margin: 16px 0;
    padding: 14px 20px;
    background: linear-gradient(135deg, rgba(14, 165, 233, 0.25) 0%, rgba(99, 102, 241, 0.35) 100%);
    border: 1px solid #38bdf8;
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 14px;
    box-shadow: 0 0 20px rgba(56, 189, 248, 0.2);
  }}
  .active-stage-tag {{
    background: #0284c7;
    color: #fff;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
  }}
  .active-stage-title {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 20px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 1px;
  }}
  .general-scope-banner {{
    margin: 16px 0;
    padding: 16px 20px;
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 8px;
  }}
  .scope-tag {{
    background: #475569;
    color: #f1f5f9;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.5px;
  }}
  .fit-card.stage-decode {{
    background: radial-gradient(circle at 50% 40%, rgba(6, 182, 212, 0.4) 0%, rgba(12, 74, 110, 0.95) 75%);
    border-color: #38bdf8;
  }}
  .fit-card.stage-embed {{
    background: radial-gradient(circle at 50% 40%, rgba(168, 85, 247, 0.4) 0%, rgba(59, 7, 100, 0.95) 75%);
    border-color: #c084fc;
  }}
  .fit-card.stage-index {{
    background: radial-gradient(circle at 50% 40%, rgba(16, 185, 129, 0.4) 0%, rgba(2, 44, 34, 0.95) 75%);
    border-color: #34d399;
  }}
  .fit-card.stage-query {{
    background: radial-gradient(circle at 50% 40%, rgba(245, 158, 11, 0.4) 0%, rgba(69, 26, 3, 0.95) 75%);
    border-color: #fbbf24;
  }}
  .fit-card.stage-serve {{
    background: radial-gradient(circle at 50% 40%, rgba(244, 63, 94, 0.4) 0%, rgba(76, 5, 25, 0.95) 75%);
    border-color: #f43f5e;
  }}
  .ev-badge {{ background: #059669; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 11px; margin-right: 8px; }}
  .fit-desc {{ font-size: 16px; color: #94a3b8; margin-bottom: 20px; }}
  .artifacts-row {{ display: flex; gap: 14px; }}
  .artifact-pill {{ background: rgba(30, 41, 59, 0.8); border: 1px solid #475569; padding: 10px 18px; border-radius: 8px; font-family: 'JetBrains Mono', monospace; font-size: 14px; color: #38bdf8; }}
  .takeaway-list {{ list-style: none; display: flex; flex-direction: column; gap: 14px; }}
  .takeaway-item {{
    font-size: 17px;
    color: #e2e8f0;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 6px 12px;
    border-radius: 6px;
  }}
  .takeaway-item.active {{
    background: rgba(56, 189, 248, 0.08);
  }}
  .item-badge {{
    background: #4f46e5;
    color: #ffffff;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
  }}
  .start-file-card {{
    margin-top: 24px;
    background: rgba(30, 41, 59, 0.8);
    border: 1px solid #38bdf8;
    border-radius: 8px;
    padding: 12px 18px;
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .start-label {{ font-size: 14px; font-weight: 600; color: #94a3b8; text-transform: uppercase; }}
  .start-code {{ font-family: 'JetBrains Mono', monospace; font-size: 16px; color: #38bdf8; font-weight: 700; }}
  .bottom-bar {{
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .caption-box {{
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 10px;
    padding: 10px 24px;
    font-size: 15px;
    font-weight: 500;
    color: #f1f5f9;
    text-align: center;
    backdrop-filter: blur(8px);
  }}
  .progress-rail {{
    width: 100%;
    height: 4px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 2px;
    overflow: hidden;
  }}
  .progress-fill {{
    height: 100%;
    width: {min(100.0, max(0.0, progress_pct)):.1f}%;
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
