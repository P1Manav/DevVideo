"""
Title scene HTML rendering with progressive reveal animation states.
"""

from __future__ import annotations

import html
from typing import Any


def render_title_html(
    sdata: dict[str, Any],
    meta: dict[str, Any],
    repo_name: str,
    state_kind: str,
) -> str:
    """Render title scene center-stage card."""
    title_text = html.escape(sdata.get("title") or meta.get("title") or meta.get("repo") or repo_name)
    owner_val = sdata.get("owner") or meta.get("owner")
    owner_html = ""
    if owner_val:
        owner_html = f'<div class="hero-subtitle">Developed by <span class="accent">{html.escape(str(owner_val))}</span></div>'
    lang_text = sdata.get("chip") or meta.get("language") or ""
    lang_chip_html = f'<div class="lang-chip">{html.escape(lang_text)}</div>' if lang_text else ""
    tagline_val = sdata.get("tagline") or meta.get("tagline") or ""
    tagline_html = f'<div class="summary-badge">{html.escape(tagline_val)}</div>' if tagline_val else ""

    if state_kind == "title_chip":
        return f"""
        <div class="title-card">
          {lang_chip_html}
        </div>
        """
    if state_kind == "title_header":
        return f"""
        <div class="title-card">
          {lang_chip_html}
          <h1 class="hero-title">{title_text}</h1>
        </div>
        """

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
    return f"""
    <div class="title-card phase-{sub_phase}" style="background: {t_bg}; border: 1px solid {border_c}; border-radius: 16px; padding: 32px 40px; box-shadow: {glow};">
      {lang_chip_html}
      <h1 class="hero-title">{title_text}</h1>
      {owner_html}
      {tagline_html}
    </div>
    """
