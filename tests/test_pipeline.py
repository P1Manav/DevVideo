"""
Integration test: full pipeline on the fixture repo.

Uses mock LLM + silent TTS, asserts:
- Valid MP4 is produced
- eval_report.json exists and all gates pass
- manifest.json is complete and contains renderer_used
- Video duration is under 60s

This test needs ffmpeg on PATH. If ffmpeg is missing, the test is skipped.
"""

import json
import shutil
import pytest
from pathlib import Path

from src.pipeline import run_pipeline

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "vidsearch_py"


@pytest.fixture
def output_dir(tmp_path):
    """Fresh output directory for each test."""
    return tmp_path / "out"


def _has_ffmpeg():
    return shutil.which("ffmpeg") is not None


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not on PATH")
class TestFullPipeline:
    def test_pipeline_produces_video_with_playwright_default(self, output_dir):
        """End-to-end: fixture repo -> MP4 + eval report with Playwright default."""
        result = run_pipeline(
            source=str(FIXTURE_REPO),
            output_dir=output_dir,
            llm_backend="mock",
            tts_backend="silent",
            use_playwright=True,  # Default
        )

        # Video was produced
        assert result.video_path is not None
        assert result.video_path.exists()
        assert result.video_path.suffix == ".mp4"
        assert result.video_path.stat().st_size > 0

        # Eval report
        eval_path = output_dir / "eval_report.json"
        assert eval_path.exists()
        report = json.loads(eval_path.read_text())
        assert report["all_gates_passed"] is True
        assert report["renderer_used"] == "playwright"

        # Manifest
        manifest_path = output_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["backend_used"] == "mock"
        assert manifest["tts_backend"] == "silent"
        assert manifest["renderer_used"] == "playwright"
        assert manifest["video_duration_seconds"] <= 60.0

        # Script
        script_path = output_dir / "scenes.json"
        assert script_path.exists()

    def test_pipeline_fallback_rendering_produces_video(self, output_dir):
        """Pipeline falls back to Pillow and still produces a valid video."""
        result = run_pipeline(
            source=str(FIXTURE_REPO),
            output_dir=output_dir,
            llm_backend="mock",
            tts_backend="silent",
            use_playwright=False,  # Force fallback
        )

        assert result.video_path is not None
        assert result.video_path.exists()
        assert result.manifest["renderer_used"] == "fallback_pillow"
        assert result.eval_report.renderer_used == "fallback_pillow"
        assert result.eval_report.all_gates_passed is True

    def test_pipeline_result_fields(self, output_dir):
        """Check that PipelineResult has all expected fields."""
        result = run_pipeline(
            source=str(FIXTURE_REPO),
            output_dir=output_dir,
            llm_backend="mock",
            tts_backend="silent",
            use_playwright=True,
        )

        assert result.script is not None
        assert len(result.script.scenes) >= 2
        assert result.eval_report is not None
        assert result.manifest["repo_name"] == "vidsearch_py"

    def test_hard_gate_failure_prevents_video_publishing(self, output_dir, monkeypatch):
        """When an eval gate fails, video is unlinked and not published."""
        import src.pipeline as pl
        from src.evals import EvalGate

        original_run_eval = pl.run_eval

        def failing_run_eval(*args, **kwargs):
            rep = original_run_eval(*args, **kwargs)
            rep.all_gates_passed = False
            rep.gates.append(EvalGate(name="test_hard_gate", passed=False, value="failed", threshold="pass"))
            return rep

        monkeypatch.setattr(pl, "run_eval", failing_run_eval)

        result = pl.run_pipeline(
            source=str(FIXTURE_REPO),
            output_dir=output_dir,
            llm_backend="mock",
            tts_backend="silent",
            use_playwright=False,
        )

        assert result.success is False
        assert result.video_path is None
        assert not (output_dir / "video.mp4").exists()
        assert (output_dir / "eval_report.json").exists()
        eval_data = json.loads((output_dir / "eval_report.json").read_text())
        assert eval_data["all_gates_passed"] is False


class TestPipelineWithoutFFmpeg:
    """Tests that work even without ffmpeg (unit-level pipeline checks)."""

    def test_invalid_source(self, output_dir):
        """Pipeline fails cleanly on invalid input."""
        result = run_pipeline(
            source="/nonexistent/path",
            output_dir=output_dir,
            llm_backend="mock",
            tts_backend="silent",
            use_playwright=False,
        )
        assert not result.success
        assert result.error
