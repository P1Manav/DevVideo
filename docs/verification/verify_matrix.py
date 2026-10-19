"""
docs/verification/verify_matrix.py: Multi-fixture generation matrix.
Runs generation with default backends (auto/edge), measures ffprobe duration and volumedetect.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.pipeline import run_pipeline

FIXTURES = [
    ("vidsearch_py", "tests/fixtures/vidsearch_py"),
    ("ffmpeg_wrapper_real", "tests/fixtures/ffmpeg_wrapper_real"),
    ("clip_real_like", "tests/fixtures/clip_real_like"),
    ("js_tool", "tests/fixtures/js_tool"),
    ("docs_only", "tests/fixtures/docs_only"),
    ("html_readme", "tests/fixtures/html_readme"),
    ("readme_only", "tests/fixtures/readme_only"),
]

def main() -> int:
    out_matrix_dir = REPO_ROOT / "out" / "_matrix"
    out_matrix_dir.mkdir(parents=True, exist_ok=True)

    log_lines = []
    log_lines.append("=== GENERATION MATRIX VERIFICATION LOG ===")
    log_lines.append("")

    all_passed = True

    for name, path_str in FIXTURES:
        target_out = out_matrix_dir / name
        shutil.rmtree(target_out, ignore_errors=True)
        target_out.mkdir(parents=True, exist_ok=True)
        
        log_lines.append(f"--- Running fixture: {name} ({path_str}) [LLM=auto, TTS=auto] ---")
        result = run_pipeline(
            source=str(REPO_ROOT / path_str),
            output_dir=target_out,
            llm_backend="auto",
            tts_backend="auto",
        )
        
        log_lines.append(f"Exit code: {result.exit_code}")
        log_lines.append(f"Status: {result.manifest.get('status') if result.manifest else 'None'}")
        
        mp4 = target_out / "video.mp4"
        if mp4.exists():
            ff_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name", "-of", "json", str(mp4)]
            ff_res = subprocess.run(ff_cmd, capture_output=True, text=True)
            try:
                probe_data = json.loads(ff_res.stdout)
                dur = float(probe_data["format"]["duration"])
                streams = [f"{s.get('codec_type')}:{s.get('codec_name')}" for s in probe_data.get("streams", [])]
                log_lines.append(f"FFprobe Duration: {dur:.2f}s")
                log_lines.append(f"FFprobe Streams: {', '.join(streams)}")
            except Exception as e:
                log_lines.append(f"FFprobe parse error: {e}")
                
            vol_cmd = ["ffmpeg", "-i", str(mp4), "-af", "volumedetect", "-f", "null", "-"]
            vol_res = subprocess.run(vol_cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
            m = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", vol_res.stderr)
            if m:
                log_lines.append(f"Mean Volume: {m.group(1)} dB")
            else:
                log_lines.append("Mean Volume: not detected")
        else:
            log_lines.append("Video: not generated")
            
        eval_f = target_out / "eval_report.json"
        if eval_f.exists():
            rep = json.loads(eval_f.read_text(encoding="utf-8"))
            passed_gates = [g["name"] for g in rep.get("gates", []) if g["passed"]]
            failed_gates = [g["name"] for g in rep.get("gates", []) if not g["passed"]]
            log_lines.append(f"All Gates Passed: {rep.get('all_gates_passed')}")
            log_lines.append(f"Passed Gates: {', '.join(passed_gates)}")
            if failed_gates:
                log_lines.append(f"Failed Gates: {', '.join(failed_gates)}")
                all_passed = False
        else:
            all_passed = False
        
        log_lines.append("")

    output_file = REPO_ROOT / "docs" / "verification" / "generation_matrix.txt"
    output_file.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"Matrix verification saved to {output_file}")
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
