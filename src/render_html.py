"""
HTML template generation for 1280x720 explainer video frames.

Includes:
- Vendored font imports (Inter and JetBrains Mono)
- Modern dark gradient background (#0b0f19 to #111827)
- Top chapter ribbon with active scene pill
- Top-right repo identity badge
- Inline SVG architecture diagram (<= 8 nodes, beat-focused node glowing)
- Pygments syntax-highlighted code block with line numbers and exact indentation
- Terminal shell quickstart card with typed command animation
- Bottom glassmorphic caption card (<= 22 words)
- Bottom animated progress bar
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
      font-weight: 400;
      font-style: normal;
    }}
    """


def generate_svg_diagram(nodes: list[str], edges: list[dict[str, str]], active_focus: str | None = None) -> str:
    """
    Generate inline SVG architecture map.
    Nodes are rendered in a clean grid with connectors.
    The active focus node is highlighted with glowing border.
    """
    svg_w, svg_h = 1100, 340
    box_w, box_h = 200, 48

    # Layout nodes across 2 rows of up to 4 columns
    coords: dict[str, tuple[int, int]] = {}
    cols = min(4, max(1, len(nodes)))
    spacing_x = 1000 // max(1, cols)
    start_x = 80

    for i, node in enumerate(nodes[:8]):
        row = i // cols
        col = i % cols
        x = start_x + col * spacing_x
        y = 40 + row * 110
        coords[node] = (x, y)

    elements = []
    # Arrow marker definition
    elements.append("""
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#6366f1" />
        </marker>
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="0" stdDeviation="4" flood-color="#38bdf8" flood-opacity="0.6"/>
        </filter>
      </defs>
    """)

    # Draw edges
    for e in edges:
        src = e.get("from", "")
        dst = e.get("to", "")
        if src in coords and dst in coords:
            x1, y1 = coords[src]
            x2, y2 = coords[dst]
            # Center of edges
            c_x1, c_y1 = x1 + box_w // 2, y1 + box_h
            c_x2, c_y2 = x2 + box_w // 2, y2
            elements.append(
                f'<path d="M {c_x1} {c_y1} C {c_x1} {(c_y1+c_y2)//2}, {c_x2} {(c_y1+c_y2)//2}, {c_x2} {c_y2}" '
                f'stroke="#4f46e5" stroke-width="2.5" fill="none" marker-end="url(#arrow)" />'
            )

    # Draw node boxes
    for node, (x, y) in coords.items():
        is_active = (active_focus and active_focus in node) or (not active_focus and node == nodes[0])
        border_color = "#38bdf8" if is_active else "#334155"
        fill_color = "rgba(14, 165, 233, 0.15)" if is_active else "rgba(30, 41, 59, 0.7)"
        filter_str = 'filter="url(#glow)"' if is_active else ""
        short_name = os.path.basename(node)

        elements.append(
            f'<g {filter_str}>'
            f'<rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="8" fill="{fill_color}" stroke="{border_color}" stroke-width="2"/>'
            f'<text x="{x + box_w//2}" y="{y + box_h//2 + 5}" text-anchor="middle" fill="#f8fafc" font-size="14" font-family="JetBrains Mono, monospace">{html.escape(short_name)}</text>'
            f'</g>'
        )

    return f'<svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg">{"".join(elements)}</svg>'


def highlight_code_snippet(code: str, file_path: str = "main.py", focus_line: int | None = None) -> str:
    """
    Format source code with pygments syntax highlighting, line numbers, and active beat focus.
    Guarantees exact indentation preservation (P5 fix).
    """
    ext = os.path.splitext(file_path)[1].lower()
    lexer = PythonLexer() if ext == ".py" else (JavascriptLexer() if ext in (".js", ".ts") else BashLexer() if ext in (".sh", ".bash") else TextLexer())

    formatter = HtmlFormatter(nowrap=True)
    raw_lines = code.strip().splitlines()[:14]  # Maximum 14 lines

    lines_html = []
    for idx, raw_line in enumerate(raw_lines, start=1):
        # Syntax highlight single line
        hl_line = highlight(raw_line, lexer, formatter).rstrip("\n")
        is_focused = (focus_line is not None and focus_line == idx)
        line_cls = "code-line active" if is_focused else "code-line"

        # Explicit line number and highlighted token span, zero template indentation
        lines_html.append(
            f'<div class="{line_cls}"><span class="line-no">{idx:2d}</span><span class="code-text">{hl_line}</span></div>'
        )

    return "\n".join(lines_html)


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
) -> str:
    """
    Construct complete, standalone HTML document for one video frame.
    1280x720, zero client-side JavaScript required.
    """
    meta = metadata or {}
    font_css = _get_font_css()

    # Chapter ribbon items
    ribbon_items = []
    for i, title in enumerate(all_scene_titles):
        cls = "ribbon-item active" if i == current_scene_idx else "ribbon-item"
        ribbon_items.append(f'<span class="{cls}">{html.escape(title)}</span>')
    ribbon_html = " ".join(ribbon_items)

    # Center visual content based on scene kind
    if scene_kind == "title":
        title_text = html.escape(meta.get("repo", repo_name))
        owner_text = html.escape(meta.get("owner", "developer"))
        lang_text = html.escape(meta.get("language", "Python"))
        inner_content = f"""
        <div class="title-card">
          <div class="lang-chip">{lang_text}</div>
          <h1 class="hero-title">{title_text}</h1>
          <div class="hero-subtitle">Developed by <span class="accent">{owner_text}</span></div>
          <div class="summary-badge">Full Explainer & Code Walkthrough</div>
        </div>
        """
    elif scene_kind == "diagram":
        nodes = meta.get("nodes", ["src/main.py", "src/core.py"])
        edges = meta.get("edges", [])
        svg_diagram = generate_svg_diagram(nodes, edges, active_focus=active_focus)
        inner_content = f"""
        <div class="diagram-container">
          <div class="card-header">Module Dependency Graph</div>
          {svg_diagram}
        </div>
        """
    elif scene_kind == "code":
        code_file = meta.get("file", "main.py")
        code_body = highlight_code_snippet(content, file_path=code_file)
        inner_content = f"""
        <div class="code-window">
          <div class="window-titlebar">
            <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
            <span class="filepath">{html.escape(code_file)}</span>
          </div>
          <pre class="code-pre"><code>{code_body}</code></pre>
        </div>
        """
    elif scene_kind == "terminal":
        cmd_text = html.escape(meta.get("command", content.lstrip("$ ")))
        inner_content = f"""
        <div class="terminal-window">
          <div class="window-titlebar">
            <span class="dot red"></span><span class="dot yellow"></span><span class="dot green"></span>
            <span class="filepath">bash - quickstart</span>
          </div>
          <div class="terminal-body">
            <div class="prompt-line"><span class="user-prompt">dev@workspace:~$</span> <span class="term-cmd">{cmd_text}</span><span class="cursor">_</span></div>
          </div>
        </div>
        """
    elif scene_kind == "recap":
        takeaways = meta.get("takeaways", content.splitlines())
        items_html = "".join(f'<li class="takeaway-item"><span class="item-badge">{i+1}</span>{html.escape(t.lstrip("123456789. "))}</li>' for i, t in enumerate(takeaways[:3]))
        inner_content = f"""
        <div class="recap-card">
          <h2 class="card-title">Key Takeaways</h2>
          <ul class="takeaway-list">{items_html}</ul>
        </div>
        """
    else:  # overview or general text
        points = meta.get("points", [content[:120]])
        points_html = "".join(f'<div class="overview-point"><span class="point-bullet">✦</span>{html.escape(p)}</div>' for p in points[:3])
        inner_content = f"""
        <div class="overview-card">
          <h2 class="card-title">{html.escape(scene_title or "Overview")}</h2>
          <div class="points-container">{points_html}</div>
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
    line-height: 1.6;
    color: #e2e8f0;
    overflow: hidden;
  }}
  .code-line {{ display: flex; gap: 16px; }}
  .code-line.active {{ background: rgba(56, 189, 248, 0.15); border-left: 3px solid #38bdf8; padding-left: 4px; }}
  .line-no {{ color: #475569; user-select: none; width: 20px; text-align: right; }}
  .code-text {{ white-space: pre; }}
  .terminal-body {{
    padding: 24px 30px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 17px;
    color: #f1f5f9;
  }}
  .user-prompt {{ color: #10b981; font-weight: 600; margin-right: 8px; }}
  .cursor {{ color: #38bdf8; font-weight: 700; animation: blink 1s step-end infinite; }}
  .overview-card, .recap-card, .diagram-container {{
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
  }}
  .point-bullet {{ color: #6366f1; font-weight: 700; }}
  .takeaway-list {{ list-style: none; display: flex; flex-direction: column; gap: 14px; }}
  .takeaway-item {{
    font-size: 17px;
    color: #e2e8f0;
    display: flex;
    align-items: center;
    gap: 14px;
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
