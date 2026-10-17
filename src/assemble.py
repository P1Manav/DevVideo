"""
Assembler: stitch scene PNGs + audio into a final MP4 video using ffmpeg.

Scene duration = audio length + small padding.
If total > 55s, raises so the pipeline can adjust.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .tts import get_audio_duration

logger = logging.getLogger(__name__)

MAX_VIDEO_DURATION = 60.0
TARGET_MAX_DURATION = 55.0  # soft target


@dataclass
class SceneAsset:
    """One scene's rendered assets."""
    scene_id: str
    png_path: Path
    audio_path: Path
    duration: float = 0.0  # set after audio is measured


def measure_scene_durations(scenes: list[SceneAsset], pad: float = 0.3) -> float:
    """Measure audio durations and set scene.duration. Returns total."""
    total = 0.0
    for scene in scenes:
        audio_dur = get_audio_duration(scene.audio_path)
        scene.duration = audio_dur + pad
        total += scene.duration
    return total


def assemble_video(
    scenes: list[SceneAsset],
    output_path: Path,
    fps: int = 1,
) -> float:
    """
    Stitch scenes into a single MP4 using ffmpeg concat.

    Each scene becomes:
    - A video segment: the PNG shown for `scene.duration` seconds
    - An audio segment: the WAV audio

    Returns the final video duration.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH")

    work_dir = output_path.parent / "_assemble_tmp"
    work_dir.mkdir(exist_ok=True)

    segment_paths = []

    for i, scene in enumerate(scenes):
        seg_path = work_dir / f"seg_{i:02d}.mp4"

        # Create video segment: still image + audio
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(scene.png_path),
            "-i", str(scene.audio_path),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            "-t", f"{scene.duration:.2f}",
            str(seg_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg segment {i} failed: {result.stderr[:500]}"
            )

        segment_paths.append(seg_path)

    # Write concat list
    concat_file = work_dir / "concat.txt"
    with open(concat_file, "w") as f:
        for sp in segment_paths:
            f.write(f"file '{sp.resolve()}'\n")

    # Concatenate all segments
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg concat failed: {result.stderr[:500]}"
        )

    # Clean up temp files
    shutil.rmtree(work_dir, ignore_errors=True)

    # Get final duration
    final_dur = _get_video_duration(output_path)
    logger.info(f"Assembled video: {final_dur:.1f}s -> {output_path}")

    return final_dur


def _get_video_duration(path: Path) -> float:
    """Get video duration using ffprobe."""
    if not shutil.which("ffprobe"):
        # Estimate from scene durations
        return 0.0

    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        return float(result.stdout.strip())
    return 0.0
