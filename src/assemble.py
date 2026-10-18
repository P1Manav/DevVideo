"""
Assembler module: stitches frame PNGs + audio WAVs into final MP4 explainer video.

Features:
- Concat-demuxer from (frame, duration) lists with repeated last entry
- Audio concatenation from scene WAVs with pads into narration.wav
- ffmpeg mux: libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -r 30 -movflags +faststart, aac 128k
- Generates subtitles (VTT + SRT), chapters.json, index.jsonl, and thumbnail.png
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import Beat, Scene
from .tts import get_audio_duration

logger = logging.getLogger(__name__)


@dataclass
class SceneAsset:
    """Compatibility asset container for callers."""
    scene_id: str
    png_path: Path
    audio_path: Path
    duration: float = 0.0


def measure_scene_durations(scenes: list[SceneAsset], pad: float = 0.3) -> float:
    """Compatibility function: measure audio durations and set scene.duration."""
    total = 0.0
    for scene in scenes:
        audio_dur = get_audio_duration(scene.audio_path)
        scene.duration = audio_dur + pad
        total += scene.duration
    return total


def concat_audio_files(wav_paths: list[Path], output_wav: Path) -> float:
    """Concatenate scene WAV files into a single narration.wav using ffmpeg."""
    if not wav_paths:
        return 0.0
    if len(wav_paths) == 1:
        shutil.copyfile(wav_paths[0], output_wav)
        return get_audio_duration(output_wav)

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_wav.parent / "_audio_concat.txt"
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for wp in wav_paths:
                f.write(f"file '{wp.resolve().as_posix()}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c:a", "pcm_s16le",
            str(output_wav),
        ]
        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg audio concat failed: {res.stderr[:300]}")
    finally:
        list_file.unlink(missing_ok=True)

    return get_audio_duration(output_wav)


def assemble_video_from_timeline(
    timeline: list[tuple[Path, float]],
    audio_path: Path,
    output_mp4: Path,
) -> float:
    """
    Stitch (frame_path, duration) timeline and narration audio into MP4.
    Uses concat demuxer repeating the last file entry for correct final duration.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found on PATH")

    if not timeline:
        raise ValueError("Empty timeline provided to assemble_video")

    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output_mp4.parent / "_video_concat.txt"

    try:
        with open(concat_file, "w", encoding="utf-8") as f:
            for frame_path, dur in timeline:
                f.write(f"file '{frame_path.resolve().as_posix()}'\n")
                f.write(f"duration {dur:.3f}\n")
            # Repeat last file entry without duration (required by ffmpeg concat demuxer)
            f.write(f"file '{timeline[-1][0].resolve().as_posix()}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            str(output_mp4),
        ]

        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg video mux failed: {res.stderr[:400]}")
    finally:
        concat_file.unlink(missing_ok=True)

    final_dur = get_audio_duration(output_mp4)
    logger.info(f"Assembled video {final_dur:.2f}s -> {output_mp4}")
    return final_dur


def assemble_video(scenes: list[SceneAsset], output_path: Path, fps: int = 1) -> float:
    """Compatibility wrapper for legacy callers."""
    timeline = [(s.png_path, s.duration) for s in scenes]
    wav_paths = [s.audio_path for s in scenes]
    concat_wav = output_path.parent / "_narration_tmp.wav"
    try:
        concat_audio_files(wav_paths, concat_wav)
        return assemble_video_from_timeline(timeline, concat_wav, output_path)
    finally:
        concat_wav.unlink(missing_ok=True)


def format_timestamp(seconds: float, vtt: bool = True) -> str:
    """Format seconds into HH:MM:SS.mmm (VTT) or HH:MM:SS,mmm (SRT)."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    msec = int(round((seconds - int(seconds)) * 1000))
    sep = "." if vtt else ","
    return f"{hrs:02d}:{mins:02d}:{secs:02d}{sep}{msec:03d}"


def generate_subtitles(scenes: list[Scene], vtt_path: Path, srt_path: Path) -> None:
    """Generate synchronized, monotonic WebVTT and SubRip subtitle files."""
    vtt_lines = ["WEBVTT\n"]
    srt_lines: list[str] = []
    cue_idx = 1
    current_time = 0.0

    for scene in scenes:
        for beat in scene.beats:
            b_start_offset = beat.start_seconds or 0.0
            b_end_offset = beat.end_seconds or (b_start_offset + 2.0)
            b_dur = max(0.5, b_end_offset - b_start_offset)
            b_start = current_time + b_start_offset
            b_end = current_time + b_end_offset
            if b_end <= b_start:
                b_end = b_start + b_dur

            text = beat.caption or beat.say

            vtt_lines.append(f"{format_timestamp(b_start, vtt=True)} --> {format_timestamp(b_end, vtt=True)}\n{text}\n")

            srt_lines.append(f"{cue_idx}\n{format_timestamp(b_start, vtt=False)} --> {format_timestamp(b_end, vtt=False)}\n{text}\n")
            cue_idx += 1

        current_time += scene.duration_seconds

    vtt_path.parent.mkdir(parents=True, exist_ok=True)
    vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(srt_lines), encoding="utf-8")


def generate_chapters(scenes: list[Scene], chapters_path: Path) -> None:
    """Generate chapters.json with chapter titles and timestamps."""
    chapters = []
    current_time = 0.0
    for scene in scenes:
        start = round(current_time, 2)
        end = round(current_time + scene.duration_seconds, 2)
        chapters.append({
            "title": scene.title or scene.id.capitalize(),
            "kind": scene.kind,
            "start_time": start,
            "end_time": end,
        })
        current_time += scene.duration_seconds

    chapters_path.parent.mkdir(parents=True, exist_ok=True)
    chapters_path.write_text(json.dumps(chapters, indent=2), encoding="utf-8")


def generate_index_jsonl(scenes: list[Scene], index_path: Path) -> None:
    """Generate index.jsonl with one searchable record per beat."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    current_time = 0.0
    with open(index_path, "w", encoding="utf-8") as f:
        for scene in scenes:
            for i, beat in enumerate(scene.beats):
                b_start = round(current_time + (beat.start_seconds or 0.0), 2)
                b_end = round(current_time + (beat.end_seconds or (beat.start_seconds or 0.0) + 2.0), 2)
                b_sources = [s.model_dump() for s in beat.sources]
                s_line = beat.sources[0].start_line if beat.sources else (getattr(scene.evidence, "line", 1) if scene.evidence else 1)
                e_line = beat.sources[0].end_line if beat.sources else (getattr(scene.evidence, "line", 1) if scene.evidence else 1)
                record = {
                    "beat_id": f"{scene.id}_{i}",
                    "scene_id": scene.id,
                    "scene_kind": scene.kind,
                    "text": beat.say,
                    "caption": beat.caption,
                    "focus": beat.focus,
                    "start_seconds": b_start,
                    "end_seconds": b_end,
                    "evidence_file": (beat.sources[0].file if beat.sources else (scene.evidence.file if scene.evidence else "")),
                    "evidence_quote": (beat.sources[0].text if beat.sources else (scene.evidence.quote if scene.evidence else "")),
                    "sources": b_sources,
                    "start_line": s_line,
                    "end_line": e_line,
                }
                f.write(json.dumps(record) + "\n")
            current_time += scene.duration_seconds


def generate_thumbnail(video_mp4: Path, fallback_frame: Path | None, thumbnail_path: Path) -> None:
    """Extract a thumbnail from the generated video or copy fallback frame."""
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg") and video_mp4.exists():
        cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:02.500",
            "-i", str(video_mp4),
            "-vframes", "1",
            str(thumbnail_path),
        ]
        res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=10)
        if res.returncode == 0 and thumbnail_path.exists() and thumbnail_path.stat().st_size > 0:
            return

    if fallback_frame and fallback_frame.exists():
        shutil.copyfile(fallback_frame, thumbnail_path)
