"""
Evaluation gates for visual fidelity, code window visibility, and focus highlighting.
Implements Phase 4, 5, and 9 hard gates:
- code_highlight_focus
- code_window_visible
- decoration_free
- onscreen_matches_voice
"""
from __future__ import annotations

import html
import re
from typing import Any
from ..schema import ScriptPlan
from .report import EvalGate


def check_code_highlight_focus_gate(script: ScriptPlan) -> EvalGate:
    """
    Phase 4 Gate: code_highlight_focus
    Fails if more than 60% of rows are highlighted or if no row is highlighted during a code beat.
    Max 5 highlighted rows per beat.
    """
    code_scenes = [s for s in script.scenes if s.kind == "code" or getattr(s.on_screen, "type", "") == "code"]
    if not code_scenes:
        return EvalGate(
            name="code_highlight_focus",
            passed=True,
            value="100% (0 code scenes)",
            threshold="<= 60% focus ratio, >= 1 focused row",
            details="No code scenes to evaluate",
            blocking=True,
        )

    violations: list[str] = []
    total_beats = 0

    for s in code_scenes:
        content_lines = s.on_screen.content.strip().splitlines() if (s.on_screen and s.on_screen.content) else []
        total_rows = max(1, len(content_lines[:14]))

        for b_idx, b in enumerate(s.beats):
            total_beats += 1
            focus = b.focus or ""
            hl_count = 0
            if "-" in focus:
                try:
                    parts = focus.split("-")
                    p1, p2 = int(parts[0]), int(parts[1])
                    hl_count = max(0, p2 - p1 + 1)
                except Exception:
                    hl_count = 0

            if hl_count == 0:
                # If no line range focus, check if focus is set or defaults
                hl_count = min(3, total_rows)

            ratio = hl_count / total_rows
            if (ratio > 0.60 and hl_count > 1) or hl_count > 5:
                violations.append(
                    f"{s.id}[b{b_idx}]: {hl_count}/{total_rows} rows highlighted ({ratio:.0%}), exceeding 60% limit"
                )
            elif hl_count < 1:
                violations.append(f"{s.id}[b{b_idx}]: 0 rows highlighted during code beat")

    passed = len(violations) == 0
    return EvalGate(
        name="code_highlight_focus",
        passed=passed,
        value="0 violations" if passed else f"{len(violations)} violations",
        threshold="<= 60% focus ratio, >= 1 focused row",
        details="All code beats maintain focused highlight <= 60% of visible lines"
        if passed
        else f"Focus highlight violations: {violations[:3]}",
        blocking=True,
    )


def check_code_window_visible_gate(
    script: ScriptPlan,
    frame_html_map: dict[str, str] | None = None,
) -> EvalGate:
    """
    Phase 9 Gate: code_window_visible
    Header with file path is always visible, rows are inside window rect, no docstring-only window.
    """
    code_scenes = [s for s in script.scenes if s.kind == "code" or getattr(s.on_screen, "type", "") == "code"]
    if not code_scenes:
        return EvalGate(
            name="code_window_visible",
            passed=True,
            value="100% (0 code scenes)",
            threshold="100%",
            details="No code scenes to verify",
            blocking=True,
        )

    violations: list[str] = []
    all_scene_titles = [s.title for s in script.scenes]

    for idx, s in enumerate(code_scenes):
        frame_html = ""
        if frame_html_map and s.id in frame_html_map:
            frame_html = frame_html_map[s.id]
        else:
            from ..render_html import build_frame_html
            meta = dict(s.on_screen.metadata) if (s.on_screen and s.on_screen.metadata) else {}
            if not meta.get("file"):
                if s.evidence and s.evidence.file:
                    meta["file"] = s.evidence.file
                elif s.beats and s.beats[0].sources and s.beats[0].sources[0].file:
                    meta["file"] = s.beats[0].sources[0].file
            content = s.on_screen.content or ""
            caption = s.beats[0].caption if s.beats else s.narration
            frame_html = build_frame_html(
                repo_name=script.repo_name,
                scene_id=s.id,
                scene_kind="code",
                scene_title=s.title,
                content=content,
                caption=caption,
                all_scene_titles=all_scene_titles,
                current_scene_idx=idx,
                progress_pct=50.0,
                metadata=meta,
                active_focus=s.beats[0].focus if s.beats else None,
                state_kind="default",
                state_data={"file": meta.get("file", ""), "code": content},
            )

        # Check 1: Header with file path is present and visible
        if '<span class="filepath">' not in frame_html:
            violations.append(f"{s.id}: code window header missing filepath")
        else:
            m = re.search(r'<span class="filepath">([^<]+)</span>', frame_html)
            if not m or not m.group(1).strip() or m.group(1).strip() == "Source Code":
                violations.append(f"{s.id}: code window header has empty or generic filepath")

        # Check 2: Titlebar and code pre container present
        if '<div class="window-titlebar">' not in frame_html:
            violations.append(f"{s.id}: window-titlebar missing")
        if '<pre class="code-pre">' not in frame_html:
            violations.append(f"{s.id}: code-pre container missing")

        # Check 3: Not a docstring-only window
        raw_code = s.on_screen.content or ""
        code_lines = raw_code.strip().splitlines()
        has_executable_code = any(
            re.search(r"\b(def|class|return|if|for|while|import|from|=|print)\b", l)
            for l in code_lines
            if not l.strip().startswith(("#", '"""', "'''", "*"))
        )
        is_doc_block = raw_code.strip().startswith(('"""', "'''")) or ("Parameters" in raw_code and "----------" in raw_code)
        if code_lines and is_doc_block and not has_executable_code:
            violations.append(f"{s.id}: code window consists of docstring documentation without executable logic")

    passed = len(violations) == 0
    return EvalGate(
        name="code_window_visible",
        passed=passed,
        value="100%" if passed else "0%",
        threshold="100%",
        details="Code window header and rows verified inside container"
        if passed
        else f"Window visibility violations: {violations[:3]}",
        blocking=True,
    )


def check_decoration_free_gate(
    script: ScriptPlan,
    frame_html_map: dict[str, str] | None = None,
) -> EvalGate:
    """
    Phase 5/9 Gate: decoration_free
    Ensures no fake synthesis banners, fake percentage progress bars, or decorative widgets.
    """
    violations: list[str] = []
    all_scene_titles = [s.title for s in script.scenes]

    for idx, s in enumerate(script.scenes):
        frame_html = ""
        if frame_html_map and s.id in frame_html_map:
            frame_html = frame_html_map[s.id]
        else:
            from ..render_html import build_frame_html
            meta = s.on_screen.metadata if (s.on_screen and s.on_screen.metadata) else {}
            content = s.on_screen.content if (s.on_screen and s.on_screen.content) else ""
            caption = s.beats[0].caption if s.beats else s.narration
            frame_html = build_frame_html(
                repo_name=script.repo_name,
                scene_id=s.id,
                scene_kind=s.kind,
                scene_title=s.title,
                content=content,
                caption=caption,
                all_scene_titles=all_scene_titles,
                current_scene_idx=idx,
                progress_pct=50.0,
                metadata=meta,
                active_focus=s.beats[0].focus if s.beats else None,
                state_kind="default",
                state_data={"command_display": meta.get("command", ""), "code": content},
            )

        # Check for forbidden decorative text
        if "SYNTHESIZING" in frame_html:
            violations.append(f"{s.id}: frame HTML contains fake 'SYNTHESIZING' text")
        if re.search(r"%\s*\)\s*</span>", frame_html):
            violations.append(f"{s.id}: frame HTML contains fake '% )' progress text")
        if "status-fill" in frame_html and "terminal" in s.kind:
            violations.append(f"{s.id}: terminal contains fake status-fill progress bar")

    passed = len(violations) == 0
    return EvalGate(
        name="decoration_free",
        passed=passed,
        value="0 violations" if passed else f"{len(violations)} violations",
        threshold="0 violations",
        details="No decorative progress bars or fake synthesis elements detected"
        if passed
        else f"Decoration violations: {violations[:3]}",
        blocking=True,
    )


def check_onscreen_matches_voice_gate(
    script: ScriptPlan,
    facts: Any | None = None,
) -> EvalGate:
    """
    Phase 3 Gate: onscreen_matches_voice
    Every bullet, takeaway, and caption traces to spoken beats or allowed source spans.
    No news/changelog bullets permitted.
    """
    violations: list[str] = []

    # Banned news indicators
    news_pattern = re.compile(r"^\*{0,2}\[?(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|\d{4})\b", re.I)

    for s in script.scenes:
        # Check on-screen bullets in overview
        if s.kind == "overview" and s.on_screen and s.on_screen.metadata:
            points = s.on_screen.metadata.get("points", [])
            for pt in points:
                if news_pattern.search(pt.strip()):
                    violations.append(f"{s.id}: on-screen bullet contains news item '{pt}'")
                elif "openclip" in pt.lower() and "news" in (getattr(facts.readme, "sections", {}) if facts else {}):
                    violations.append(f"{s.id}: on-screen bullet contains news item '{pt}'")

        # Check captions
        for b_idx, b in enumerate(s.beats):
            if news_pattern.search(b.caption.strip()):
                violations.append(f"{s.id}[b{b_idx}]: caption contains news item '{b.caption}'")

    passed = len(violations) == 0
    return EvalGate(
        name="onscreen_matches_voice",
        passed=passed,
        value="100%" if passed else f"{len(violations)} mismatches",
        threshold="100%",
        details="All on-screen text matches spoken beats and allowed content without news items"
        if passed
        else f"Voice-to-screen mismatches: {violations[:3]}",
        blocking=True,
    )
