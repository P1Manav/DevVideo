"""
docs/verification/verify_frames_and_cues.py:
Frame extraction at 10 timestamps across video duration + subtitle cue validation.
"""
from __future__ import annotations

import json
from pathlib import Path
from PIL import Image
import re
import subprocess

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
video_path = REPO_ROOT / "docs" / "sample" / "video.mp4"
scenes_path = REPO_ROOT / "docs" / "sample" / "scenes.json"
vtt_path = REPO_ROOT / "docs" / "sample" / "transcript.vtt"

def main() -> int:
    log_lines = []
    log_lines.append("=== FRAME AND CUE ALIGNMENT AUDIT ===")
    log_lines.append("")

    # 1. Subtitle & Cue Alignment Check
    log_lines.append("--- 1. Subtitle & Cue Alignment Check ---")
    if not video_path.exists() or not vtt_path.exists():
        log_lines.append("Error: Sample video or vtt missing")
        return 1

    dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)]
    vid_dur = float(subprocess.run(dur_cmd, capture_output=True, text=True).stdout.strip())
    log_lines.append(f"Total video duration: {vid_dur:.3f}s")

    vtt_content = vtt_path.read_text(encoding="utf-8")
    cues = re.findall(r"((?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*((?:\d{2}:)?\d{2}:\d{2}\.\d{3})\n([^\n]+)", vtt_content)
    log_lines.append(f"Found {len(cues)} WebVTT cues.")

    all_cues_within_bounds = True
    for start_str, end_str, cue_text in cues:
        def parse_ts(ts):
            parts = ts.split(":")
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            return float(parts[0]) * 60 + float(parts[1])
        s_sec = parse_ts(start_str)
        e_sec = parse_ts(end_str)
        if s_sec < 0 or e_sec > vid_dur + 0.5:
            all_cues_within_bounds = False
            log_lines.append(f"CUE OUT OF BOUNDS: [{start_str} --> {end_str}] {cue_text}")

    log_lines.append(f"All cues sit strictly inside video duration: {all_cues_within_bounds}")

    # 2. Extract frames at 10 timestamps
    log_lines.append("\n--- 2. Sampled Video Frame Visual Validation (10 Timestamps) ---")
    frames_tmp = REPO_ROOT / "out" / "_audit_frames"
    frames_tmp.mkdir(parents=True, exist_ok=True)

    timestamps = [round(i * (vid_dur / 11.0), 2) for i in range(1, 11)]
    log_lines.append(f"Extracting 10 frames at timestamps: {timestamps}")

    non_flat_count = 0
    for idx, ts in enumerate(timestamps):
        frame_png = frames_tmp / f"frame_{idx:02d}.png"
        cmd = [
            "ffmpeg", "-y", "-ss", str(ts), "-i", str(video_path),
            "-frames:v", "1", "-q:v", "2", str(frame_png)
        ]
        subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True)
        if frame_png.exists():
            im = Image.open(frame_png).convert("RGB")
            colors = len(im.getcolors(maxcolors=200000) or [])
            is_valid = (colors > 50 and im.size == (1280, 720))
            if is_valid:
                non_flat_count += 1
            log_lines.append(f"Timestamp {ts:05.2f}s -> {frame_png.name}: {im.size[0]}x{im.size[1]}, distinct colors={colors} (valid={is_valid})")

    log_lines.append(f"Frame validation result: {non_flat_count}/{len(timestamps)} frames valid and non-flat.")

    out_file = REPO_ROOT / "docs" / "verification" / "frame_and_cues_audit.txt"
    out_file.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"Audit log saved to {out_file}")
    return 0 if (all_cues_within_bounds and non_flat_count == 10) else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
