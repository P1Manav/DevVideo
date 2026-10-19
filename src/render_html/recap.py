"""
Recap scene HTML rendering with progressive takeaways and entry point highlight.
"""

from __future__ import annotations

import html
from typing import Any


def render_recap_html(
    sdata: dict[str, Any],
    meta: dict[str, Any],
    content: str,
) -> str:
    """Render recap card center-stage."""
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
    return f"""
    <div class="recap-card phase-{sub_phase}" style="background: {r_bg}; border: 1px solid {border_c}; box-shadow: 0 0 25px {border_c}40;">
      <h2 class="card-title">Key Takeaways</h2>
      <ul class="takeaway-list">{''.join(items_html)}</ul>
      {start_card_html}
    </div>
    """
