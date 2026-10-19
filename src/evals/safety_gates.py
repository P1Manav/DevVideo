"""Evaluation gates submodule."""
from __future__ import annotations
import html
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from PIL import Image

from ..schema import ScriptPlan, is_disallowed_span
from .report import EvalGate

logger = logging.getLogger(__name__)

CMD_PREFIXES = (
    "sudo ", "pip ", "pip3 ", "python ", "python3 ", "npm ", "npx ", "yarn ",
    "pnpm ", "uv ", "poetry ", "cargo ", "go ", "make ", "docker ", "git ",
    "curl ", "bash ", "sh ", "cd ", "export ",
)

# Independent secret leak detector patterns (different from ingest redaction)
INDEPENDENT_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z0-9_-]+ PRIVATE KEY-----"),
    re.compile(r"ey[A-Za-z0-9_-]{10,}\.ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"xox[baprs]-[0-9]{10,}-[0-9]{10,}-[a-zA-Z0-9]{24,}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
]


def check_code_verbatim_gate(script: ScriptPlan, repo_files: dict[str, str]) -> EvalGate:
    """Gate 5: every on-screen code excerpt is an exact line range of the cited file."""
    code_scenes = [s for s in script.scenes if s.kind == "code" or getattr(s.on_screen, "type", "") == "code"]
    if not code_scenes:
        return EvalGate(name="code_verbatim", passed=True, value="100% (0 code scenes)", threshold="100%")

    valid = 0
    failures: list[str] = []

    for scene in code_scenes:
        ev = scene.evidence
        if not ev.file or ev.file not in repo_files:
            failures.append(f"{scene.id}: file '{ev.file}' not in repo")
            continue
        file_text = repo_files[ev.file]
        code_excerpt = scene.on_screen.content.strip()
        if code_excerpt in file_text:
            valid += 1
        else:
            failures.append(f"{scene.id}: code snippet not verbatim line range in {ev.file}")

    ratio = valid / len(code_scenes)
    passed = ratio >= 1.0
    return EvalGate(
        name="code_verbatim",
        passed=passed,
        value=f"{ratio:.0%}",
        threshold="100%",
        details=f"{valid}/{len(code_scenes)} code scenes verbatim" + (f" (Failed: {failures})" if failures else ""),
    )


def extract_rendered_code_from_html(frame_html: str) -> list[str]:
    """
    Extract visible code lines from a rendered code frame HTML.
    Strips tags, unescapes entities, drops line numbers and wrap markers (â†³),
    and rejoins continuation rows into original lines.
    """
    lines: list[str] = []
    pattern = re.compile(r'<div class="code-line([^"]*)">.*?<span class="code-text">(.*?)</span>\s*</div>', re.DOTALL)
    for m in pattern.finditer(frame_html):
        div_cls = m.group(1)
        text_content = m.group(2)
        raw = re.sub(r'<[^>]+>', '', text_content)
        raw = html.unescape(raw)
        is_cont = ("cont-row" in div_cls) or ("\u21b3" in raw) or ("↳" in raw) or ("â†³" in raw)
        if is_cont:
            cleaned = re.sub(r"^\s*[\u21b3↳â†³] ?", "", raw)
            if lines:
                lines[-1] = lines[-1] + cleaned
            else:
                lines.append(cleaned)
        else:
            lines.append(raw)
    return lines


def check_rendered_code_matches_gate(
    script: ScriptPlan,
    frame_html_map: dict[str, str] | None = None,
    repo_files: dict[str, str] | None = None,
) -> EvalGate:
    """
    Gate: rendered_code_matches
    Extracts visible text from frame HTML (stripping tags, unescaping, dropping line numbers & wrap markers,
    rejoining continuation rows) and asserts it equals the cited source lines exactly (whitespace-normalized per line).
    """
    code_scenes = [s for s in script.scenes if s.kind == "code" or getattr(s.on_screen, "type", "") == "code"]
    if not code_scenes:
        return EvalGate(
            name="rendered_code_matches",
            passed=True,
            value="100% (0 code scenes)",
            threshold="100%",
            details="No code scenes to verify",
            blocking=True,
        )

    all_scene_titles = [s.title for s in script.scenes]
    passed_scenes = 0
    failures: list[str] = []

    for idx, scene in enumerate(code_scenes):
        frame_html = ""
        if frame_html_map and scene.id in frame_html_map:
            frame_html = frame_html_map[scene.id]
        else:
            from ..render_html import build_frame_html
            meta = scene.on_screen.metadata or {}
            content = scene.on_screen.content or ""
            caption = scene.beats[0].caption if scene.beats else scene.narration
            frame_html = build_frame_html(
                repo_name=script.repo_name,
                scene_id=scene.id,
                scene_kind="code",
                scene_title=scene.title,
                content=content,
                caption=caption,
                all_scene_titles=all_scene_titles,
                current_scene_idx=idx,
                progress_pct=50.0,
                metadata=meta,
                active_focus=scene.beats[0].focus if scene.beats else None,
                state_kind="default",
                state_data={"file": meta.get("file", ""), "code": content},
            )

        extracted_lines = extract_rendered_code_from_html(frame_html)
        expected_lines = scene.on_screen.content.strip().splitlines()[:14]

        if not extracted_lines and expected_lines:
            failures.append(f"{scene.id}: No code lines extracted from frame HTML")
            continue

        scene_matches = True
        for line_no, (ext_l, exp_l) in enumerate(zip(extracted_lines, expected_lines), start=1):
            norm_ext = " ".join(ext_l.split())
            norm_exp = " ".join(exp_l.split())
            if norm_ext != norm_exp:
                scene_matches = False
                failures.append(
                    f"{scene.id} line {line_no} mismatch: extracted {norm_ext!r} != expected {norm_exp!r}"
                )
                break

        if len(extracted_lines) < len(expected_lines):
            scene_matches = False
            failures.append(
                f"{scene.id}: extracted {len(extracted_lines)} lines, expected {len(expected_lines)}"
            )

        if scene_matches:
            passed_scenes += 1

    ratio = passed_scenes / len(code_scenes)
    passed = (ratio >= 1.0)
    return EvalGate(
        name="rendered_code_matches",
        passed=passed,
        value=f"{ratio:.0%}",
        threshold="100%",
        details=f"{passed_scenes}/{len(code_scenes)} code frames match source lines exactly"
        + (f" (Mismatches: {failures})" if failures else ""),
        blocking=True,
    )


def extract_commands(content: str) -> list[str]:
    """Extract command lines from text or code blocks."""
    commands: list[str] = []
    norm = content.replace("\\n", "\n")
    for raw_line in norm.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("$ "):
            commands.append(line[2:].strip())
        elif any(line.startswith(prefix) for prefix in CMD_PREFIXES):
            commands.append(line)
    return commands


def check_command_validity_gate(script: ScriptPlan, repo_files: dict[str, str]) -> EvalGate:
    """
    Gate 6: every command shown appears verbatim in repo files.
    If 0 commands detected, reports 'not applicable', not pass.
    """
    total_commands = 0
    valid_commands = 0
    missing: list[str] = []
    all_repo_text = "\n".join(repo_files.values())

    for scene in script.scenes:
        cmds = extract_commands(scene.on_screen.content)
        for cmd in cmds:
            total_commands += 1
            if cmd in all_repo_text:
                valid_commands += 1
            else:
                missing.append(f"{scene.id}: '{cmd}'")

    if total_commands == 0:
        return EvalGate(
            name="command_validity",
            passed=True,
            value="not applicable (0 commands)",
            threshold="100%",
            details="No on-screen shell commands detected in script",
        )

    ratio = valid_commands / total_commands
    passed = ratio >= 1.0
    return EvalGate(
        name="command_validity",
        passed=passed,
        value=f"{ratio:.0%}",
        threshold="100%",
        details=f"{valid_commands}/{total_commands} commands verified verbatim" + (f" (Missing: {missing})" if missing else ""),
    )


def check_secret_leaks_gate(
    script: ScriptPlan,
    ingest_secrets: set[str] | list[str] | None = None,
    transcripts: list[str] | None = None,
    raw_input: str | None = None,
) -> EvalGate:
    """
    Gate 7: independent check asserting recorded secrets do not appear,
    plus secondary regex detector across script, captions, transcripts.
    """
    leaks = 0
    locations: list[str] = []
    recorded = set(ingest_secrets or [])

    texts_to_check: list[tuple[str, str]] = []
    if raw_input:
        texts_to_check.append(("raw_input", raw_input))

    for scene in script.scenes:
        texts_to_check.append((f"narration:{scene.id}", scene.narration))
        texts_to_check.append((f"on_screen:{scene.id}", scene.on_screen.content))
        for b in scene.beats:
            texts_to_check.append((f"beat_say:{scene.id}", b.say))
            texts_to_check.append((f"beat_caption:{scene.id}", b.caption))

    for i, t in enumerate(transcripts or []):
        texts_to_check.append((f"transcript:{i}", t))

    # 1. Check recorded secrets
    for label, text in texts_to_check:
        for sec in recorded:
            if sec and sec in text:
                leaks += 1
                locations.append(f"{label} contains recorded secret")

    # 2. Secondary regex detector
    for label, text in texts_to_check:
        for pat in INDEPENDENT_SECRET_PATTERNS:
            if pat.search(text):
                leaks += 1
                locations.append(f"{label} matched secret pattern {pat.pattern[:20]}")

    passed = leaks == 0
    return EvalGate(
        name="secret_leaks",
        passed=passed,
        value=str(leaks),
        threshold="0",
        details="No secrets detected" if passed else f"Leaks detected in: {locations}",
    )


# Backwards compatibility alias
check_secret_gate = check_secret_leaks_gate



check_secret_gate = check_secret_leaks_gate
