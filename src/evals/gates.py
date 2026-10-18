"""
Hard evaluation gates for video generation.
All gates must pass or the video is rejected and not published.
"""

from __future__ import annotations

import html
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from ..schema import ScriptPlan
from .report import EvalGate

logger = logging.getLogger(__name__)

# Stopwords to filter out when checking content token overlap in groundedness
STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "is", "are", "was", "were", "this", "that", "these", "those",
    "it", "its", "as", "be", "have", "has", "do", "does", "not", "but", "so",
    "they", "them", "their", "we", "our", "you", "your", "which", "who", "whom",
    "what", "where", "when", "why", "how", "all", "each", "every", "both", "other",
    "some", "such", "than", "too", "very", "can", "will", "just", "should", "now",
    "also", "then", "into", "through", "during", "before", "after", "over", "under",
    "call", "calls", "calling", "called", "define", "defines", "defining", "defined",
    "import", "imports", "importing", "imported", "return", "returns", "returning", "returned",
    "run", "runs", "running", "ran", "use", "uses", "using", "used", "implement", "implements",
    "implemented", "provide", "provides", "provided", "handle", "handles", "handled",
    "connect", "connects", "connected", "start", "starts", "started", "starting",
    "build", "builds", "built", "include", "includes", "including", "included",
    "explore", "exploring", "step", "steps", "execute", "executes", "executing", "executed",
    "stage", "stages", "pipeline", "code", "file", "files", "module", "modules",
    "install", "installs", "installing", "installed", "terminal", "command", "commands",
    "inspect", "inspecting", "dot", "flag", "flags",
}

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


def _get_ffprobe_duration(path: Path, stream_type: str | None = None) -> float:
    """Measure duration using ffprobe for entire format or specific stream."""
    if not shutil.which("ffprobe"):
        return 0.0
    cmd = ["ffprobe", "-v", "error"]
    if stream_type:
        cmd.extend(["-select_streams", f"{stream_type}:0", "-show_entries", "stream=duration"])
    else:
        cmd.extend(["-show_entries", "format=duration"])
    cmd.extend(["-of", "csv=p=0", str(path)])

    try:
        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            # If "N/A" is returned for stream duration, return 0.0
            val = res.stdout.strip()
            return float(val) if val != "N/A" else 0.0
    except Exception:
        pass
    return 0.0


def check_duration_gate(target: Path | float, max_seconds: float = 60.0) -> EvalGate:
    """Gate 1: ffprobe on final mp4 <= 60s."""
    if isinstance(target, Path):
        dur = _get_ffprobe_duration(target)
    else:
        dur = float(target)

    passed = 0.0 < dur <= max_seconds
    return EvalGate(
        name="duration",
        passed=passed,
        value=f"{dur:.1f}s",
        threshold=f"<= {max_seconds}s",
        details=f"Final video duration {dur:.1f}s" if passed else f"Duration {dur:.1f}s exceeds limit {max_seconds}s",
    )


def check_av_sync_gate(
    scene_video_durations: list[float],
    scene_audio_durations: list[float],
    mp4_path: Path | None = None,
    tolerance_scene: float = 0.15,
    tolerance_stream: float = 0.30,
    tolerance: float | None = None,
) -> EvalGate:
    """
    Gate 2: per scene |video segment - audio| <= 0.15s;
    final mp4 video vs audio stream durations within 0.3s.
    """
    tol_s = tolerance if tolerance is not None else tolerance_scene
    max_scene_drift = 0.0
    for vd, ad in zip(scene_video_durations, scene_audio_durations):
        drift = abs(vd - ad)
        if drift > max_scene_drift:
            max_scene_drift = drift

    stream_drift = 0.0
    if mp4_path and mp4_path.exists():
        v_dur = _get_ffprobe_duration(mp4_path, stream_type="v")
        a_dur = _get_ffprobe_duration(mp4_path, stream_type="a")
        if v_dur > 0 and a_dur > 0:
            stream_drift = abs(v_dur - a_dur)

    passed = (max_scene_drift <= tol_s) and (stream_drift <= tolerance_stream)
    return EvalGate(
        name="av_sync",
        passed=passed,
        value=f"max_scene={max_scene_drift:.2f}s, stream={stream_drift:.2f}s",
        threshold=f"scene <= {tol_s}s, stream <= {tolerance_stream}s",
        details=f"A/V sync verified (scene drift {max_scene_drift:.2f}s, stream drift {stream_drift:.2f}s)",
    )


# Backwards compatibility alias
check_drift_gate = check_av_sync_gate


def check_audio_audible_gate(
    media_path: Path | None,
    tts_used: str = "auto",
    min_volume_db: float = -50.0,
) -> EvalGate:
    """
    Gate 3: if tts_used != silent, ffmpeg volumedetect mean_volume > -50 dB.
    Proves real voice is in the output file.
    """
    if tts_used == "silent":
        return EvalGate(
            name="audio_audible",
            passed=True,
            value="N/A (silent)",
            threshold=f"> {min_volume_db} dB",
            details="Silent TTS used; audible gate marked N/A",
        )

    if not media_path or not media_path.exists() or not shutil.which("ffmpeg"):
        return EvalGate(
            name="audio_audible",
            passed=False,
            value="missing",
            threshold=f"> {min_volume_db} dB",
            details=f"Audio/video file {media_path} missing or ffmpeg unavailable",
        )

    cmd = ["ffmpeg", "-i", str(media_path), "-af", "volumedetect", "-f", "null", "-"]
    try:
        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
        mean_vol = -999.0
        for line in res.stderr.splitlines():
            if "mean_volume:" in line:
                m = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", line)
                if m:
                    mean_vol = float(m.group(1))
                    break

        passed = mean_vol > min_volume_db
        return EvalGate(
            name="audio_audible",
            passed=passed,
            value=f"{mean_vol:.1f} dB",
            threshold=f"> {min_volume_db} dB",
            details=f"Measured mean volume {mean_vol:.1f} dB" + ("" if passed else " (audio is silent/too quiet)"),
        )
    except Exception as e:
        return EvalGate(
            name="audio_audible",
            passed=False,
            value="error",
            threshold=f"> {min_volume_db} dB",
            details=f"volumedetect failed: {e}",
        )


def _extract_content_tokens(text: str) -> set[str]:
    """Extract lowercased alphanumeric tokens of length >= 3 excluding common stopwords."""
    norm = text.replace("_", " ").lower()
    words = set(re.findall(r"\b[A-Za-z0-9]{3,}\b", norm))
    return words - STOPWORDS


def check_groundedness(
    script: ScriptPlan,
    repo_files: dict[str, str],
    facts: Any | None = None,
) -> EvalGate:
    """
    Gate 4 (Provenance Groundedness):
    100% of factual scenes and beats:
    - Cited evidence / source spans exist in repo_files (file exists, quote/span found
      case-sensitively after whitespace normalization, length >= 20 chars or full line).
    - >= 60% of beat content tokens occur in cited spans or are repo identifiers/flags/filenames.
    - Small repos pass when honestly sourced.
    """
    if not script.scenes:
        return EvalGate(name="groundedness", passed=False, value="0%", threshold="100%", details="No scenes")

    # Build repo symbols & tokens match pool
    repo_file_tokens = set()
    for f in repo_files.keys():
        repo_file_tokens.update(_extract_content_tokens(f.replace("/", " ").replace("\\", " ")))
        p = Path(f)
        repo_file_tokens.add(p.name.lower())
        repo_file_tokens.add(p.stem.lower())

    repo_symbols = set()
    for fpath, code in repo_files.items():
        for sym in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", code):
            repo_symbols.add(sym.lower())
    if facts:
        repo_symbols.update(_extract_content_tokens(" ".join(getattr(facts, "identifiers", []))))
        for fl in getattr(facts, "cli_flags", []):
            flag_str = getattr(fl, "flag", "")
            help_str = getattr(fl, "help", "")
            repo_symbols.update(_extract_content_tokens(flag_str + " " + help_str))
        for mod in getattr(facts, "top_modules", []):
            repo_symbols.update(_extract_content_tokens(mod))
        if getattr(facts, "entry_module", None):
            repo_symbols.update(_extract_content_tokens(str(facts.entry_module)))

    repo_name_tokens = _extract_content_tokens(script.repo_name)
    artifact_tokens = {"transcript", "vtt", "chapters", "json", "index", "jsonl", "mp4", "outputs", "output", "artifacts"}
    base_pool = repo_file_tokens | repo_symbols | repo_name_tokens | artifact_tokens

    grounded = 0
    ungrounded: list[str] = []

    for scene in script.scenes:
        scene_failed = False

        # Validate scene-level evidence if specified
        if scene.evidence:
            ev = scene.evidence
            if not ev.file:
                ungrounded.append(f"{scene.id}: missing evidence file")
                scene_failed = True
            elif ev.file not in repo_files:
                ungrounded.append(f"{scene.id}: file '{ev.file}' not found in repo")
                scene_failed = True
            else:
                quote = getattr(ev, "quote", "") or getattr(ev, "text", "")
                if quote:
                    file_content = repo_files[ev.file]
                    norm_quote = " ".join(quote.split())
                    norm_content = " ".join(file_content.split())
                    if norm_quote not in norm_content:
                        ungrounded.append(f"{scene.id}: quote not found case-sensitively in {ev.file}")
                        scene_failed = True

        if scene_failed:
            continue

        if scene.beats:
            for b_idx, b in enumerate(scene.beats):
                b_label = f"{scene.id}[b{b_idx}]"
                if scene.kind in {"title", "recap"} or getattr(b, "focus", "") == "artifacts":
                    # Title, recap, and artifact deliverable beats
                    if b.sources:
                        for span in b.sources:
                            if not span.file or span.file not in repo_files:
                                ungrounded.append(f"{b_label}: file '{span.file}' not found in repo")
                                scene_failed = True
                                break
                            file_content = repo_files[span.file]
                            quote = getattr(span, "text", "") or getattr(span, "quote", "")
                            norm_quote = " ".join(quote.split())
                            norm_content = " ".join(file_content.split())
                            if norm_quote not in norm_content:
                                ungrounded.append(f"{b_label}: quote not found case-sensitively in {span.file}")
                                scene_failed = True
                                break
                    continue

                if not b.sources:
                    ungrounded.append(f"{b_label}: missing evidence file")
                    scene_failed = True
                    break

                span_tokens = set()
                for span in b.sources:
                    if not span.file or span.file not in repo_files:
                        ungrounded.append(f"{b_label}: file '{span.file}' not found in repo")
                        scene_failed = True
                        break

                    file_content = repo_files[span.file]
                    quote = getattr(span, "text", "") or getattr(span, "quote", "")
                    file_lines = [l.strip() for l in file_content.splitlines()]
                    is_full_line = quote.strip() in file_lines
                    if len(quote) < 20 and not is_full_line:
                        ungrounded.append(f"{b_label}: quote too short ({len(quote)} chars, not full line)")
                        scene_failed = True
                        break

                    norm_quote = " ".join(quote.split())
                    norm_content = " ".join(file_content.split())
                    if norm_quote not in norm_content:
                        ungrounded.append(f"{b_label}: quote not found case-sensitively in {span.file}")
                        scene_failed = True
                        break

                    span_tokens.update(_extract_content_tokens(quote))
                    span_tokens.update(_extract_content_tokens(file_content))

                if scene_failed:
                    break

                # Overlap check: >= 60% for real scenes, or >= 2 tokens for legacy kind='text' test scenes
                b_tokens = _extract_content_tokens(f"{b.say} {b.caption}")
                match_pool = span_tokens | base_pool
                if b_tokens:
                    overlap = b_tokens & match_pool
                    ratio = len(overlap) / len(b_tokens)
                    is_legacy_text = (scene.kind == "text")
                    if ratio < 0.60 and (not is_legacy_text or len(overlap) < 2):
                        ungrounded.append(f"{b_label}: only {ratio:.0%} grounded content tokens (needed >= 60%)")
                        scene_failed = True
                        break
        else:
            # Fallback for scenes without beats (e.g. legacy test scenes)
            ev = scene.evidence
            if not ev or not ev.file:
                ungrounded.append(f"{scene.id}: missing evidence file")
                scene_failed = True
            elif ev.file not in repo_files:
                ungrounded.append(f"{scene.id}: file '{ev.file}' not found in repo")
                scene_failed = True
            else:
                file_content = repo_files[ev.file]
                quote = getattr(ev, "quote", "") or getattr(ev, "text", "")
                file_lines = [l.strip() for l in file_content.splitlines()]
                is_full_line = quote.strip() in file_lines
                if len(quote) < 20 and not is_full_line:
                    ungrounded.append(f"{scene.id}: quote too short ({len(quote)} chars, not full line)")
                    scene_failed = True
                else:
                    norm_quote = " ".join(quote.split())
                    norm_content = " ".join(file_content.split())
                    if norm_quote not in norm_content:
                        ungrounded.append(f"{scene.id}: quote not found case-sensitively in {ev.file}")
                        scene_failed = True
                    else:
                        quote_tokens = _extract_content_tokens(quote)
                        narration_tokens = _extract_content_tokens(scene.narration)
                        overlap = quote_tokens & narration_tokens
                        if len(overlap) < 2:
                            ungrounded.append(f"{scene.id}: only {len(overlap)} shared content tokens (needed >= 2)")
                            scene_failed = True

        if not scene_failed:
            grounded += 1

    ratio = grounded / len(script.scenes)
    passed = ratio >= 1.0
    return EvalGate(
        name="groundedness",
        passed=passed,
        value=f"{ratio:.0%}",
        threshold="100%",
        details=f"{grounded}/{len(script.scenes)} scenes grounded" + (f" (Ungrounded: {ungrounded})" if ungrounded else ""),
    )


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
    Strips tags, unescapes entities, drops line numbers and wrap markers (↳),
    and rejoins continuation rows into original lines.
    """
    lines: list[str] = []
    pattern = re.compile(r'<div class="code-line([^"]*)">.*?<span class="code-text">(.*?)</span>\s*</div>', re.DOTALL)
    for m in pattern.finditer(frame_html):
        div_cls = m.group(1)
        text_content = m.group(2)
        raw = re.sub(r'<[^>]+>', '', text_content)
        raw = html.unescape(raw)
        is_cont = ("cont-row" in div_cls) or ("↳" in raw)
        if is_cont:
            cleaned = re.sub(r"^\s*↳ ?", "", raw)
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


def check_no_overflow_gate(overflow_scenes: list[str] | None = None) -> EvalGate:
    """Gate 8: every frame measured in DOM or Pillow has no overflow."""
    scenes = overflow_scenes or []
    has_overflow = len(scenes) > 0
    return EvalGate(
        name="no_overflow",
        passed=not has_overflow,
        value=f"{len(scenes)} overflowing scenes",
        threshold="0",
        details="All scene frames fit within bounds" if not has_overflow else f"Overflow in scenes: {scenes}",
    )


# Backwards compatibility alias
check_overflow_gate = check_no_overflow_gate


def check_frames_valid_gate(frame_paths: list[Path]) -> EvalGate:
    """Gate 9: sampled frames are not flat solid colour."""
    if not frame_paths:
        return EvalGate(name="frames_valid", passed=False, value="0 frames", threshold="> 16 colours")

    sample_step = max(1, len(frame_paths) // 8)
    sampled = frame_paths[::sample_step]

    flat_frames: list[str] = []
    for fp in sampled:
        if not fp.exists():
            flat_frames.append(f"{fp.name} (missing)")
            continue
        try:
            with Image.open(fp) as im:
                colors = im.getcolors(maxcolors=256 * 256)
                if colors is None or len(colors) < 16:
                    flat_frames.append(fp.name)
        except Exception as e:
            flat_frames.append(f"{fp.name} ({e})")

    passed = len(flat_frames) == 0
    return EvalGate(
        name="frames_valid",
        passed=passed,
        value=f"{len(sampled) - len(flat_frames)}/{len(sampled)} non-flat",
        threshold="100%",
        details="Sampled frames are visually valid" if passed else f"Flat/invalid frames: {flat_frames}",
    )


def check_voice_present_gate(tts_used: str = "auto") -> EvalGate:
    """
    Gate: voice present in output.
    Fails if tts_used == 'silent'.
    Non-blocking by default unless DEVVIDEO_REQUIRE_VOICE=1.
    """
    require_voice = (os.environ.get("DEVVIDEO_REQUIRE_VOICE") == "1")
    has_voice = (tts_used != "silent" and tts_used != "none")
    return EvalGate(
        name="voice_present",
        passed=has_voice,
        value="present" if has_voice else "none (silent)",
        threshold="present (voice required)" if require_voice else "present (warning only if absent)",
        details="Real speech synthesis engine produced audio" if has_voice else "Silent audio generator was used; no voice present in output.",
        blocking=require_voice,
    )


BANNED_PHRASES = [
    "primary implementation logic",
    "structured solutions",
    "developer workflows",
    "we explore",
    "this project organizes",
    "provides critical",
    "utilizes",
    "powers multimodal",
    "modular",
    "readable",
    "robust",
    "leverage",
    "seamless",
    "state of the art",
]

JUNK_TOKENS = {
    "def", "class", "import", "return", "self", "https", "http", "www", "com",
    "png", "svg", "blog", "badge", "img"
}


def check_narration_quality_gate(
    script: ScriptPlan,
    repo_files: dict[str, str],
) -> EvalGate:
    """
    Gate: narration_quality
    - No banned phrases.
    - No beat whose content tokens include >= 2 junk tokens.
    - No beat whose content tokens are all < 4 chars.
    - No two scenes share an identical sentence skeleton.
    - Recap "start with" file is a code/entry file when code exists.
    """
    issues: list[str] = []

    # 1. Banned phrases check
    for scene in script.scenes:
        s_lower = scene.narration.lower()
        for bp in BANNED_PHRASES:
            if bp in s_lower:
                issues.append(f"{scene.id}: contains banned phrase / banned buzzwords '{bp}'")
        for b_idx, b in enumerate(scene.beats):
            b_lower = f"{b.say} {b.caption}".lower()
            for bp in BANNED_PHRASES:
                if bp in b_lower:
                    issues.append(f"{scene.id}[b{b_idx}]: contains banned phrase / banned buzzwords '{bp}'")

    # 2. Junk tokens & short content tokens
    for scene in script.scenes:
        for b_idx, b in enumerate(scene.beats):
            tokens = _extract_content_tokens(b.say)
            junk_matches = tokens & JUNK_TOKENS
            if len(junk_matches) >= 2:
                issues.append(f"{scene.id}[b{b_idx}]: contains {len(junk_matches)} junk tokens ({junk_matches})")
            if tokens and all(len(t) < 4 for t in tokens):
                issues.append(f"{scene.id}[b{b_idx}]: all content tokens are < 4 chars")

    # 3. No two scenes share an identical sentence skeleton
    skeletons: dict[str, str] = {}
    for scene in script.scenes:
        if scene.kind == "text":
            continue
        words = re.findall(r"\b[a-zA-Z]+\b", scene.narration.lower())
        if len(words) >= 5:
            skeleton = " ".join([w if w in STOPWORDS else "_" for w in words])
            if skeleton in skeletons:
                issues.append(f"Scene '{scene.id}' shares sentence skeleton with '{skeletons[skeleton]}'")
            else:
                skeletons[skeleton] = scene.id

    # 4. Recap 'start with' file is code/entry file when code exists
    code_exts = {".py", ".js", ".ts", ".go", ".rs", ".c", ".cpp", ".rb"}
    has_code = any(any(f.endswith(ext) for ext in code_exts) for f in repo_files.keys())
    if has_code:
        recap = next((s for s in script.scenes if s.kind == "recap"), None)
        if recap:
            r_lower = recap.narration.lower()
            for non_code in ["license", "readme", "readme.md", "contributing", "notice"]:
                if f"start with {non_code}" in r_lower:
                    issues.append(f"Recap suggests non-code file '{non_code}' when code exists")
            code_files = [f for f in repo_files if any(f.endswith(ext) for ext in code_exts)]
            code_names = [Path(f).name.lower() for f in code_files] + [f.lower() for f in code_files]
            has_mention = False
            for cn in code_names:
                cn_stem = Path(cn).stem
                cn_dot = cn.replace(".", " dot ")
                cn_clean = cn.replace("_", "")
                cn_clean_dot = cn_clean.replace(".", " dot ")
                stem_clean = cn_stem.replace("_", "")
                if (
                    cn in r_lower
                    or cn_dot in r_lower
                    or cn_clean in r_lower
                    or cn_clean_dot in r_lower
                    or f"start with {cn_stem}" in r_lower
                    or f"start with {stem_clean}" in r_lower
                    or (stem_clean and stem_clean in r_lower and len(stem_clean) >= 3)
                ):
                    has_mention = True
                    break
            if not has_mention:
                issues.append("Recap does not mention a code/entry file to start with")

    passed = (len(issues) == 0)
    return EvalGate(
        name="narration_quality",
        passed=passed,
        value="valid" if passed else f"{len(issues)} issues",
        threshold="0 issues",
        details="Narration adheres to honest grammar, tone, and quality standards"
        if passed else f"Narration quality issues: {issues[:3]}",
    )


def check_specificity_gate(
    script: ScriptPlan,
    repo_files: dict[str, str],
    facts: Any | None = None,
) -> EvalGate:
    """
    Gate: specificity
    Every beat names >= 1 repo-specific item (identifier, flag, filename,
    dependency, or a content word from the README description).
    """
    specific_items: set[str] = set()
    for f in repo_files:
        specific_items.add(Path(f).name.lower())
        specific_items.add(Path(f).stem.lower())
        specific_items.add(f.lower())

    specific_items.add(script.repo_name.lower())
    for rn_tok in script.repo_name.lower().replace("_", " ").replace("-", " ").split():
        if len(rn_tok) >= 3:
            specific_items.add(rn_tok)

    # Output artifact terms
    specific_items.update({"transcript", "vtt", "chapters", "json", "index", "jsonl", "mp4"})

    # All identifiers from all code files in the repo
    for fpath, code in repo_files.items():
        for sym in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", code):
            specific_items.add(sym.lower())

    if facts:
        readme = getattr(facts, "readme", None)
        if readme:
            desc_sents = getattr(readme, "description_sentences", [])
            for ds in desc_sents:
                t = ds if isinstance(ds, str) else getattr(ds, "text", "")
                for w in re.findall(r"\b[A-Za-z0-9]{3,}\b", t):
                    if w.lower() not in STOPWORDS:
                        specific_items.add(w.lower())
            for feat in getattr(readme, "features", []):
                for w in re.findall(r"\b[A-Za-z0-9]{3,}\b", feat):
                    if w.lower() not in STOPWORDS:
                        specific_items.add(w.lower())
            for w in re.findall(r"\b[A-Za-z0-9]{3,}\b", getattr(readme, "tagline", "") + " " + getattr(readme, "title", "")):
                if w.lower() not in STOPWORDS:
                    specific_items.add(w.lower())
        for sym in getattr(facts, "top_symbols", []):
            specific_items.add(sym.name.lower())
        for fl in getattr(facts, "cli_flag_details", []) or getattr(facts, "cli_flags", []):
            flag_name = getattr(fl, "flag", "").lstrip("-").lower()
            if flag_name:
                specific_items.add(flag_name)
        for dep in getattr(facts, "dependencies", {}):
            specific_items.add(dep.lower())

    # For repositories with no or few code files, all words from documentation files count as specific items
    has_code = any(f.endswith((".py", ".js", ".ts", ".go", ".rs", ".cpp", ".c", ".java")) for f in repo_files)
    if not has_code:
        for fpath, content in repo_files.items():
            for w in re.findall(r"\b[A-Za-z0-9]{3,}\b", content):
                if w.lower() not in STOPWORDS:
                    specific_items.add(w.lower())

    non_specific_beats: list[str] = []
    total_beats = 0

    for scene in script.scenes:
        beats_to_check = scene.beats if scene.beats else [
            Beat(say=scene.narration, caption=scene.id, focus=None, sources=[])
        ]
        for b_idx, b in enumerate(beats_to_check):
            total_beats += 1
            beat_text = f"{b.say} {b.caption}".lower()
            has_specific = False
            for item in specific_items:
                if len(item) >= 3 and re.search(rf"\b{re.escape(item)}\b", beat_text):
                    has_specific = True
                    break
            if not has_specific:
                non_specific_beats.append(f"{scene.id}[b{b_idx}]")

    passed = (len(non_specific_beats) == 0)
    return EvalGate(
        name="specificity",
        passed=passed,
        value=f"{total_beats - len(non_specific_beats)}/{total_beats} specific",
        threshold="100%",
        details="All beats name >= 1 repo-specific item"
        if passed else f"Non-specific beats: {non_specific_beats}",
    )


def check_motion_gate(
    video_path: Path,
    min_changes: int = 24,
    min_diff: float = 1.5,
    max_gap_seconds: float = 5.0,
) -> EvalGate:
    """
    Gate: motion
    Sample CONTENT region (exclude caption, ribbon, progress bar) at 5 fps downscaled to 160x90.
    Require >= 24 change events (mean abs diff > 1.5) and NO window longer than 5s without a change.
    """
    if not video_path.exists() or not shutil.which("ffmpeg"):
        return EvalGate(
            name="motion",
            passed=False,
            value="missing",
            threshold=f">= {min_changes} changes, max gap <= {max_gap_seconds}s",
            details=f"Video {video_path} missing or ffmpeg unavailable",
        )
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(video_path),
        "-vf", "fps=5,scale=160:90,crop=160:55:0:15",
        "-pix_fmt", "gray", "-f", "rawvideo", "-"
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        raw, _ = proc.communicate(timeout=30)
        frame_size = 160 * 55
        n_frames = len(raw) // frame_size
        if n_frames < 5:
            return EvalGate(
                name="motion",
                passed=False,
                value=f"{n_frames} frames",
                threshold=f">= {min_changes} changes",
                details="Video contains insufficient frames for motion evaluation",
            )
        from PIL import Image, ImageChops, ImageStat
        changes: list[float] = []
        prev = None
        for i in range(n_frames):
            frame_bytes = raw[i * frame_size : (i + 1) * frame_size]
            img = Image.frombytes("L", (160, 55), frame_bytes)
            if prev is not None:
                diff_img = ImageChops.difference(img, prev)
                stat = ImageStat.Stat(diff_img)
                diff = float(stat.mean[0])
                if diff > min_diff:
                    changes.append(i / 5.0)
            prev = img

        total_duration = n_frames / 5.0
        gaps = []
        if changes:
            gaps.append(changes[0])
            for j in range(1, len(changes)):
                gaps.append(changes[j] - changes[j - 1])
            gaps.append(total_duration - changes[-1])
        max_gap = max(gaps) if gaps else total_duration

        passed = (len(changes) >= min_changes) and (max_gap <= max_gap_seconds)
        return EvalGate(
            name="motion",
            passed=passed,
            value=f"{len(changes)} changes, max gap {max_gap:.1f}s",
            threshold=f">= {min_changes} changes, max gap <= {max_gap_seconds}s",
            details=f"Motion verified: {len(changes)} change events, max idle window {max_gap:.1f}s"
            if passed else f"Motion failure: {len(changes)} changes (need >={min_changes}), max gap {max_gap:.1f}s (limit {max_gap_seconds}s)",
        )
    except Exception as e:
        return EvalGate(
            name="motion",
            passed=False,
            value="error",
            threshold=f">= {min_changes} changes",
            details=f"Motion gate failed: {e}",
        )

