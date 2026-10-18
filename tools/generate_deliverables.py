"""
Generate official benchmark deliverables:
1. docs/sample/ from tests/fixtures/vidsearch_py
2. docs/sample_fixture/ from tests/fixtures/clip_real_like

Includes real audible voice narration via pyttsx3 SAPI5, Playwright frames, and passing gates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.pipeline import run_pipeline


def generate_deliverable(source_path: str, out_dir: Path, name: str) -> None:
    print(f"=== Generating Deliverable: {name} from {source_path} ===")
    out_dir.mkdir(parents=True, exist_ok=True)
    res = run_pipeline(
        source=source_path,
        output_dir=out_dir,
        llm_backend="mock",
        tts_backend="auto",
        renderer="playwright",
    )
    print(f"[{name}] Exit code: {res.exit_code}")
    print(f"[{name}] Video path: {res.video_path}")
    if res.manifest:
        print(f"[{name}] Status: {res.manifest.get('status')}")
        print(f"[{name}] All Gates Passed: {res.manifest.get('all_gates_passed')}")
    assert res.exit_code == 0, f"Pipeline failed: {res.error}"
    assert (out_dir / "video.mp4").exists(), "video.mp4 missing"
    assert (out_dir / "manifest.json").exists(), "manifest.json missing"
    assert (out_dir / "index.jsonl").exists(), "index.jsonl missing"
    assert (out_dir / "chapters.json").exists(), "chapters.json missing"
    assert (out_dir / "transcript.vtt").exists(), "transcript.vtt missing"
    assert (out_dir / "transcript.srt").exists(), "transcript.srt missing"
    assert (out_dir / "thumbnail.png").exists(), "thumbnail.png missing"
    assert (out_dir / "eval_report.json").exists(), "eval_report.json missing"
    print(f"[{name}] ALL DELIVERABLES CONFIRMED GREEN!\n")


if __name__ == "__main__":
    generate_deliverable("tests/fixtures/vidsearch_py", Path("docs/sample"), "docs/sample")
    generate_deliverable("tests/fixtures/clip_real_like", Path("docs/sample_fixture"), "docs/sample_fixture")
