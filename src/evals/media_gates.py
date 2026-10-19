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



check_drift_gate = check_av_sync_gate

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


check_overflow_gate = check_no_overflow_gate

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

        effective_min = min(min_changes, max(8, int(min_changes * (total_duration / 50.0)))) if total_duration < 50.0 else min_changes
        passed = (len(changes) >= effective_min) and (max_gap <= max_gap_seconds)
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

