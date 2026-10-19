"""
Diagram scene HTML and SVG architecture map generation.
"""

from __future__ import annotations

import html
from typing import Any


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

    visible_set = set(disp_nodes[:n_visible])
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        if src in coords and tgt in coords and src in visible_set and tgt in visible_set:
            x1, y1 = coords[src]
            x2, y2 = coords[tgt]
            elements.append(
                f'<path d="M {x1+box_w//2} {y1+box_h} Q {(x1+x2)//2} {(y1+y2)//2 + 20} {x2+box_w//2} {y2}" '
                f'stroke="#818cf8" stroke-width="2" fill="none" marker-end="url(#arrow)" stroke-dasharray="4" />'
            )

    for i, node in enumerate(disp_nodes):
        x, y = coords[node]
        is_visible = i < n_visible
        is_active = (node == active_focus) or (i == n_visible - 1)

        if not is_visible:
            continue

        stroke_color = "#38bdf8" if is_active else "#475569"
        fill_color = "rgba(14, 165, 233, 0.25)" if is_active else "rgba(30, 41, 59, 0.85)"
        text_color = "#38bdf8" if is_active else "#cbd5e1"
        glow_filter = 'filter="url(#glow)"' if is_active else ""
        font_weight = "700" if is_active else "500"

        clean_name = html.escape(node)
        elements.append(f"""
      <g {glow_filter}>
        <rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="8"
              fill="{fill_color}" stroke="{stroke_color}" stroke-width="{2 if is_active else 1}" />
        <text x="{x + box_w//2}" y="{y + box_h//2 + 5}" fill="{text_color}" font-family="JetBrains Mono, monospace"
              font-size="13" font-weight="{font_weight}" text-anchor="middle">{clean_name}</text>
      </g>
    """)

    if overflow_count > 0:
        elements.append(f"""
      <text x="960" y="320" fill="#94a3b8" font-family="Inter, sans-serif" font-size="12" text-anchor="end">
        + {overflow_count} more module{'s' if overflow_count > 1 else ''} omitted
      </text>
    """)

    return f'<svg width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}" xmlns="http://www.w3.org/2000/svg">{"".join(elements)}</svg>'


def render_diagram_html(
    sdata: dict[str, Any],
    meta: dict[str, Any],
    active_focus: str | None,
) -> str:
    """Render diagram container."""
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
    return f"""
    <div class="diagram-container">
      <div class="card-header">Module Call Flow & Architecture</div>
      {svg_diagram}
    </div>
    """
