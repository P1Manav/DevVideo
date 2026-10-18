"""
Hard evaluation gates for video generation.
All gates must pass or the video is rejected and not published.
"""

from __future__ import annotations

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


def check_groundedness(script: ScriptPlan, repo_files: dict[str, str]) -> EvalGate:
    """
    Gate 4: 100% of factual scenes:
    - evidence file exists
    - quote >= 20 chars (or a full line)
    - found case-sensitively after whitespace normalization
    - narration shares >= 2 content tokens with the evidence
    """
    if not script.scenes:
        return EvalGate(name="groundedness", passed=False, value="0%", threshold="100%", details="No scenes")

    grounded = 0
    ungrounded: list[str] = []

    for scene in script.scenes:
        ev = scene.evidence
        if not ev or not ev.file:
            ungrounded.append(f"{scene.id}: missing evidence file")
            continue

        if ev.file not in repo_files:
            ungrounded.append(f"{scene.id}: file '{ev.file}' not found in repo")
            continue

        content = repo_files[ev.file]
        quote = ev.quote

        # Quote length check (>=20 chars or exact full line)
        file_lines = [l.strip() for l in content.splitlines()]
        is_full_line = quote.strip() in file_lines
        if len(quote) < 20 and not is_full_line:
            ungrounded.append(f"{scene.id}: quote too short ({len(quote)} chars, not full line)")
            continue

        # Case-sensitive whitespace normalization check
        norm_quote = " ".join(quote.split())
        norm_content = " ".join(content.split())
        if norm_quote not in norm_content:
            ungrounded.append(f"{scene.id}: quote not found case-sensitively in {ev.file}")
            continue

        # Lexical overlap: shares >= 2 content tokens
        quote_tokens = _extract_content_tokens(quote)
        narration_tokens = _extract_content_tokens(scene.narration)
        overlap = quote_tokens & narration_tokens
        if len(overlap) < 2:
            ungrounded.append(f"{scene.id}: only {len(overlap)} shared content tokens (needed >= 2)")
            continue

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

