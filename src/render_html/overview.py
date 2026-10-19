"""
Overview scene HTML rendering with progressive bullet points.
"""

from __future__ import annotations

import html
from typing import Any


def render_overview_html(
    sdata: dict[str, Any],
    meta: dict[str, Any],
    content: str,
    scene_title: str,
) -> str:
    """Render overview card center-stage."""
    points = sdata.get("points") or meta.get("points") or [content[:120]]
    rev_count = sdata.get("revealed_count", len(points))
    sub_phase = sdata.get("sub_phase", 0)

    items_html = []
    for i, p in enumerate(points[:3]):
        if i < rev_count:
            is_active = (i == rev_count - 1)
            cls = "overview-point active" if is_active else "overview-point"
            pulse_color = "#38bdf8" if sub_phase % 2 == 0 else "#a855f7"
            items_html.append(
                f'<div class="{cls}"><span class="point-bullet" style="color: {pulse_color};">✦</span>{html.escape(p)}</div>'
            )

    ov_bgs = [
        "rgba(15, 23, 42, 0.9)",
        "rgba(18, 38, 70, 0.95)",
        "rgba(40, 22, 70, 0.95)",
        "rgba(14, 45, 52, 0.95)",
    ]
    ov_bg = ov_bgs[sub_phase % len(ov_bgs)]
    border_c = "#38bdf8" if sub_phase % 2 == 0 else "#6366f1"
    return f"""
    <div class="overview-card phase-{sub_phase}" style="background: {ov_bg}; border: 1px solid {border_c}; box-shadow: 0 0 25px {border_c}40;">
      <h2 class="card-title">{html.escape(scene_title or "Overview")}</h2>
      <div class="points-container">{''.join(items_html)}</div>
    </div>
    """
