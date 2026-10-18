"""
Simulate fresh-clone execution of run.yaml commands and record output.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
temp_clone = Path(tempfile.mkdtemp(prefix="fresh_devvideo_"))

log_lines = []
log_lines.append("=== FRESH CLONE SIMULATION AUDIT ===")
log_lines.append(f"Cloning from: {repo_root}")
log_lines.append(f"Target temp dir: {temp_clone}")
log_lines.append("")

try:
    # 1. Clone local repo
    res = subprocess.run(["git", "clone", str(repo_root), str(temp_clone)], capture_output=True, text=True)
    log_lines.append(f"$ git clone {repo_root} {temp_clone}")
    log_lines.append(res.stdout + res.stderr)
    log_lines.append(f"Exit code: {res.returncode}\n")
    
    # 2. Run python src/main.py --help
    log_lines.append("$ python src/main.py --help")
    res = subprocess.run([sys.executable, "src/main.py", "--help"], cwd=temp_clone, capture_output=True, text=True)
    log_lines.append(res.stdout)
    log_lines.append(f"Exit code: {res.returncode}\n")
    
    # 3. Run python src/main.py generate tests/fixtures/vidsearch_py --out out/
    log_lines.append("$ python src/main.py generate tests/fixtures/vidsearch_py --out out/")
    res = subprocess.run([sys.executable, "src/main.py", "generate", "tests/fixtures/vidsearch_py", "--out", "out/"], cwd=temp_clone, capture_output=True, text=True)
    log_lines.append(res.stdout + res.stderr)
    log_lines.append(f"Exit code: {res.returncode}\n")
    
    out_dir = temp_clone / "out"
    if (out_dir / "video.mp4").exists():
        log_lines.append(f"Generated video: {(out_dir / 'video.mp4').stat().st_size} bytes")
    if (out_dir / "eval_report.json").exists():
        log_lines.append("Eval report: " + (out_dir / "eval_report.json").read_text(encoding="utf-8")[:300] + "...")
        
    # 4. Run test suite
    log_lines.append("\n$ pytest tests/test_e2e.py -v")
    res = subprocess.run([sys.executable, "-m", "pytest", "tests/test_e2e.py", "-v"], cwd=temp_clone, capture_output=True, text=True)
    log_lines.append(res.stdout + res.stderr)
    log_lines.append(f"Exit code: {res.returncode}\n")

finally:
    shutil.rmtree(temp_clone, ignore_errors=True)

out_log = Path("docs/verification/fresh_clone.txt")
out_log.write_text("\n".join(log_lines), encoding="utf-8")
print(f"Fresh clone simulation log written to {out_log}")
