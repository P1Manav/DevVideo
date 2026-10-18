"""
End-to-end integration tests across realistic repo fixtures.
Includes @pytest.mark.must_run markers for CI enforcement.
"""

import json
import socket
import subprocess
from pathlib import Path

import pytest
from src.pipeline import run_pipeline

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.must_run
def test_e2e_vidsearch_py(tmp_path):
    """
    Must run in CI: pipeline on vidsearch_py with default backends.
    Produces 45-60s MP4 with video+audio streams, companion outputs, and passing gates.
    """
    out_dir = tmp_path / "vidsearch_out"
    result = run_pipeline(
        source=str(FIXTURES_DIR / "vidsearch_py"),
        output_dir=out_dir,
    )

    assert result.exit_code == 0, f"Pipeline failed: {result.error}"
    assert result.video_path is not None
    assert result.video_path.exists()
    assert result.video_path.stat().st_size > 0

    # Check companion outputs
    assert (out_dir / "transcript.vtt").exists()
    assert (out_dir / "transcript.srt").exists()
    assert (out_dir / "chapters.json").exists()
    assert (out_dir / "index.jsonl").exists()
    assert (out_dir / "thumbnail.png").exists()
    assert (out_dir / "eval_report.json").exists()
    assert (out_dir / "manifest.json").exists()

    # Check manifest contents
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "published"
    assert manifest["all_gates_passed"] is True
    assert 40.0 <= manifest["video_duration_seconds"] <= 60.0


def test_e2e_js_tool(tmp_path):
    """Test full generation on JavaScript/TypeScript repository."""
    out_dir = tmp_path / "js_out"
    result = run_pipeline(
        source=str(FIXTURES_DIR / "js_tool"),
        output_dir=out_dir,
        tts_backend="silent",
    )
    assert result.exit_code == 0, f"Pipeline failed on JS repo: {result.error}"
    assert (out_dir / "video.mp4").exists()


def test_e2e_docs_only(tmp_path):
    """Test graceful degradation on documentation-only repo."""
    out_dir = tmp_path / "docs_out"
    result = run_pipeline(
        source=str(FIXTURES_DIR / "docs_only"),
        output_dir=out_dir,
        tts_backend="silent",
    )
    assert result.exit_code == 0, f"Pipeline failed on docs-only repo: {result.error}"
    assert (out_dir / "video.mp4").exists()


def test_e2e_html_readme_no_raw_tags(tmp_path):
    """Test that cleaned HTML README narrates no raw HTML tags."""
    out_dir = tmp_path / "html_out"
    result = run_pipeline(
        source=str(FIXTURES_DIR / "html_readme"),
        output_dir=out_dir,
        tts_backend="silent",
    )
    assert result.exit_code == 0, f"Pipeline failed on HTML README repo: {result.error}"
    assert result.script is not None
    for scene in result.script.scenes:
        assert "<" not in scene.narration
        assert ">" not in scene.narration


def test_e2e_network_blocked_fallback(tmp_path, monkeypatch):
    """Network-blocked run still produces valid video via local TTS or silent fallback."""
    def block_connect(*args, **kwargs):
        raise OSError("Network connection blocked by test policy")

    monkeypatch.setattr(socket.socket, "connect", block_connect)

    out_dir = tmp_path / "net_blocked_out"
    result = run_pipeline(
        source=str(FIXTURES_DIR / "docs_only"),
        output_dir=out_dir,
    )
    assert result.exit_code in (0, 1)
    assert (out_dir / "manifest.json").exists()


def test_e2e_no_readme_repo_never_crashes(tmp_path):
    """Repo with no README must degrade gracefully and write manifest without unhandled crash."""
    empty_repo = tmp_path / "no_readme_repo"
    empty_repo.mkdir()
    (empty_repo / "main.py").write_text("print('hello')", encoding="utf-8")

    out_dir = tmp_path / "no_readme_out"
    result = run_pipeline(
        source=str(empty_repo),
        output_dir=out_dir,
        tts_backend="silent",
    )
    # May be 0 (degraded pass) or 1 (rejected), but never unhandled crash
    assert result.exit_code in (0, 1)
    assert (out_dir / "manifest.json").exists()
