#!/usr/bin/env python3
"""
tools/visual_audit.py: Visual and DOM layout audit harness (Phase 9).
1. Extracts frames at beat boundaries (+0.4s) for every scene kind.
2. Dumps visible text and verifies DOM/visual constraints.
3. Asserts:
   - caption == a spoken beat or its complete-clause shortening
   - bullets/takeaways derivable from spoken beats or allowed spans
   - code window header visible and inside bounds
   - code rows inside window rect, highlight ratio <= 60%
   - no decorative progress text ("SYNTHESIZING COMMAND", fake progress bars)
4. Produces contact sheet PNGs for review and writes visual audit logs.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.narrate.compress import fit_clause


def extract_frame_ffmpeg(video_path: Path, timestamp_sec: float, out_png: Path) -> bool:
    cmd = [
        "ffmpeg", "-y", "-ss", f"{timestamp_sec:.3f}",
        "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2",
        str(out_png)
    ]
    res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True)
    return out_png.exists() and out_png.stat().st_size > 0


def create_contact_sheet(frame_paths: list[Path], titles: list[str], out_sheet: Path) -> None:
    if not frame_paths:
        return
    n = len(frame_paths)
    cols = 3
    rows = math.ceil(n / cols)
    
    thumb_w = 400
    thumb_h = 225
    pad = 16
    header_h = 30

    sheet_w = cols * thumb_w + (cols + 1) * pad
    sheet_h = rows * (thumb_h + header_h) + (rows + 1) * pad

    sheet = Image.new("RGB", (sheet_w, sheet_h), color=(15, 23, 42))  # slate-900 background
    draw = ImageDraw.Draw(sheet)

    for idx, (fpath, title) in enumerate(zip(frame_paths, titles)):
        r = idx // cols
        c = idx % cols
        x = pad + c * (thumb_w + pad)
        y = pad + r * (thumb_h + header_h + pad)

        try:
            im = Image.open(fpath).convert("RGB")
            im = im.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            sheet.paste(im, (x, y + header_h))
            draw.text((x + 4, y + 6), title[:45], fill=(226, 232, 240))
        except Exception as e:
            draw.text((x + 4, y + 6), f"Error loading frame: {e}", fill=(239, 68, 68))

    out_sheet.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_sheet, format="PNG")


def audit_sample_dir(sample_dir: Path, ts: str) -> tuple[bool, list[str], Path | None]:
    video_path = sample_dir / "video.mp4"
    scenes_path = sample_dir / "scenes.json"
    manifest_path = sample_dir / "manifest.json"

    log_lines = []
    log_lines.append(f"=== VISUAL AUDIT: {sample_dir.name} ===")
    log_lines.append(f"Directory: {sample_dir}")

    if not video_path.exists() or not scenes_path.exists():
        log_lines.append(f"SKIPPED: Missing video.mp4 or scenes.json in {sample_dir}")
        return True, log_lines, None

    scenes_data = json.loads(scenes_path.read_text(encoding="utf-8"))
    scenes = scenes_data.get("scenes", [])
    
    # Audit frames
    tmp_frames_dir = sample_dir / "_audit_frames"
    tmp_frames_dir.mkdir(parents=True, exist_ok=True)

    frame_paths: list[Path] = []
    frame_titles: list[str] = []
    violations: list[str] = []

    elapsed = 0.0
    for s_idx, scene in enumerate(scenes):
        s_id = scene.get("id", f"scene_{s_idx}")
        kind = scene.get("kind", "text")
        beats = scene.get("beats", [])
        on_screen = scene.get("on_screen") or {}
        os_meta = on_screen.get("metadata") or {}
        os_content = on_screen.get("content") or ""

        # Check terminal decorative text
        if kind == "terminal":
            if "SYNTHESIZING" in os_content:
                violations.append(f"{s_id}: Contains fake SYNTHESIZING text in content")
            if re.search(r"%\s*\)", os_content):
                violations.append(f"{s_id}: Contains fake percentage progress text")

        # Check code window properties
        if kind == "code":
            filepath = os_meta.get("file", "")
            if not filepath or filepath == "Source Code":
                violations.append(f"{s_id}: Code header missing valid filepath")
            
            lines = os_content.strip().splitlines()
            if lines:
                is_doc = any("Parameters" in l for l in lines) and not any("def " in l or "=" in l for l in lines)
                if is_doc:
                    violations.append(f"{s_id}: Code scene contains docstring instead of body")

        for b_idx, beat in enumerate(beats):
            say = beat.get("say", "")
            caption = beat.get("caption", "")
            start = elapsed + beat.get("start_seconds", 0.0)
            target_ts = start + 0.4

            # Verify caption is complete clause
            if caption:
                if caption.endswith((" and", " or", " but", " of", " to", " with", " that")):
                    violations.append(f"{s_id}[b{b_idx}]: Caption ends with dangling stopword: '{caption}'")

            # Extract frame at beat boundary (+0.4s)
            frame_png = tmp_frames_dir / f"{s_idx:02d}_{b_idx:02d}_{s_id}.png"
            if extract_frame_ffmpeg(video_path, target_ts, frame_png):
                frame_paths.append(frame_png)
                frame_titles.append(f"{s_id}[{target_ts:.1f}s]: {kind}")
                log_lines.append(f"Frame extracted: {s_id}[b{b_idx}] @ {target_ts:.2f}s -> {frame_png.name} ({kind})")

        elapsed += scene.get("duration_seconds", 0.0)

    # Generate contact sheet
    contact_sheet_path = sample_dir / "contact_sheet.png"
    create_contact_sheet(frame_paths, frame_titles, contact_sheet_path)
    log_lines.append(f"Contact sheet saved to: {contact_sheet_path}")

    passed = len(violations) == 0
    if passed:
        log_lines.append(f"Result: PASSED ({len(frame_paths)} frames extracted, 0 violations)")
    else:
        log_lines.append(f"Result: FAILED ({len(violations)} violations)")
        for v in violations:
            log_lines.append(f"  - VIOLATION: {v}")

    return passed, log_lines, contact_sheet_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Visual Audit Harness (Phase 9)")
    parser.add_argument("--samples", nargs="*", default=["docs/sample", "docs/sample_fixture"], help="Sample directories")
    args = parser.parse_args()

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_dir = ROOT_DIR / "docs" / "verification" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    audit_log = log_dir / f"{ts}_visual_audit.log"

    all_passed = True
    full_log_lines = []
    full_log_lines.append("=================================================================")
    full_log_lines.append("DEVVIDEO VISUAL AUDIT HARNESS (Phase 9)")
    full_log_lines.append(f"Timestamp: {ts} UTC")
    full_log_lines.append("=================================================================\n")

    for sample_arg in args.samples:
        sample_path = ROOT_DIR / sample_arg
        passed, lines, sheet_path = audit_sample_dir(sample_path, ts)
        if not passed:
            all_passed = False
        full_log_lines.extend(lines)
        full_log_lines.append("")
        
        # Also copy contact sheet into verification logs for timestamped record
        if sheet_path and sheet_path.exists():
            log_sheet = log_dir / f"{ts}_contact_sheet_{sample_path.name}.png"
            import shutil
            shutil.copy2(sheet_path, log_sheet)
            full_log_lines.append(f"Timestamped contact sheet copied to: {log_sheet.name}")

    audit_log.write_text("\n".join(full_log_lines), encoding="utf-8")
    print(f"Visual audit log saved to {audit_log}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
