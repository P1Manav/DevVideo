"""Audit test for docs/sample/ and docs/sample_fixture/ deliverables."""
import json
from pathlib import Path
import pytest

from src.tts.engines import EdgeTTS

ROOT_DIR = Path(__file__).parent.parent
SAMPLE_DIRS = [ROOT_DIR / "docs" / "sample", ROOT_DIR / "docs" / "sample_fixture"]

REQUIRED_FILES = [
    "video.mp4",
    "transcript.vtt",
    "transcript.srt",
    "chapters.json",
    "index.jsonl",
    "thumbnail.png",
    "scenes.json",
    "eval_report.json",
    "manifest.json",
    "narration.txt",
    "README.md",
]

def test_samples_deliverables_exist_and_non_empty():
    for sdir in SAMPLE_DIRS:
        assert sdir.exists(), f"Sample directory missing: {sdir}"
        for fname in REQUIRED_FILES:
            fpath = sdir / fname
            assert fpath.exists(), f"Required sample deliverable {fname} missing in {sdir}"
            assert fpath.stat().st_size > 0, f"Sample deliverable {fname} is empty in {sdir}"

def test_sample_manifests_not_mock_or_silent():
    voice_available = EdgeTTS().probe()
    for sdir in SAMPLE_DIRS:
        manifest_path = sdir / "manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data.get("llm_used") != "mock", f"Sample in {sdir} used mock LLM planner"
        if voice_available:
            assert data.get("tts_used") != "silent", f"Sample in {sdir} used silent TTS while voice was available"
        
        narration_path = sdir / "narration.txt"
        lines = [l.strip() for l in narration_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) >= 5, f"narration.txt in {sdir} has fewer than 5 beats ({len(lines)})"
