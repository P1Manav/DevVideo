"""
Fit scene HTML rendering for multimodal AI pipeline grounding and deliverables.
"""

from __future__ import annotations

import html
from typing import Any


def render_fit_html(sdata: dict[str, Any], meta: dict[str, Any]) -> str:
    """Render domain fit scene center-stage card."""
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
            st_bg = stage_gradients.get(
                active_stage.lower(),
                "linear-gradient(135deg, rgba(14, 165, 233, 0.35) 0%, rgba(99, 102, 241, 0.45) 100%)",
            )
            active_banner_html = f"""
            <div class="active-stage-banner" style="background: {st_bg};">
              <span class="active-stage-tag">ACTIVE STAGE</span>
              <span class="active-stage-title">{html.escape(active_stage.upper())}</span>
            </div>
            """

        stage_cls = f"stage-{html.escape(active_stage.lower())}" if active_stage else "stage-default"
        return f"""
        <div class="fit-card {stage_cls}">
          <h2 class="card-title">Multimodal Pipeline Grounding</h2>
          <div class="stages-track">{'<span class="stage-arrow">→</span>'.join(stage_cards)}</div>
          {active_banner_html}
          {ev_html}
        </div>
        """

    if mode == "announcement":
        sub_phase = sdata.get("sub_phase", 0)
        phase_styles = [
            (
                "border: 2px solid #38bdf8; box-shadow: 0 0 35px rgba(56, 189, 248, 0.55); background: rgba(14, 38, 68, 0.95);",
                "rgba(56, 189, 248, 0.25)",
                "#38bdf8",
                "SCOPE: GENERAL PACKAGE",
            ),
            (
                "border: 2px solid #a855f7; box-shadow: 0 0 35px rgba(168, 85, 247, 0.55); background: rgba(38, 18, 62, 0.95);",
                "rgba(168, 85, 247, 0.25)",
                "#a855f7",
                "STANDARD RUNTIME UTILITY",
            ),
            (
                "border: 2px solid #10b981; box-shadow: 0 0 35px rgba(16, 185, 129, 0.55); background: rgba(12, 44, 40, 0.95);",
                "rgba(16, 185, 129, 0.25)",
                "#10b981",
                "DOWNSTREAM PIPELINE READY",
            ),
        ]
        st_card, st_bg, st_color, st_tag = phase_styles[sub_phase % len(phase_styles)]
        return f"""
        <div class="fit-card phase-{sub_phase}" style="{st_card}">
          <h2 class="card-title">Domain Scope & Applicability</h2>
          <div class="general-scope-banner" style="background: {st_bg}; border-left: 5px solid {st_color};">
            <span class="scope-tag" style="background: {st_color}; color: #0f172a; font-weight: 800;">{st_tag}</span>
            <p class="fit-desc" style="margin-top: 10px;">Repository does not specialize in video understanding; standard software package.</p>
          </div>
        </div>
        """

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
    return f"""
    <div class="fit-card phase-{sub_phase}" style="background: {fit_bg}; border: 2px solid {border_c}; box-shadow: 0 0 35px {border_c}55;">
      <h2 class="card-title">Structured Retrieval Package</h2>
      <p class="fit-desc">Generated assets for downstream search and multimodal indexing:</p>
      <div class="artifacts-row">{files_html}</div>
    </div>
    """
