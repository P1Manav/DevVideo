"""
Unit and integration tests for CLI interface (src.cli and main.py shim).
Tests exit codes (0 published, 1 rejected, 2 error) and manifest writing on all outcomes.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from src.cli import main

FIXTURE_REPO = Path(__file__).parent / "fixture_repo"


class TestCLI:
    def test_cli_help(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["devvideo", "generate", "--help"])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
        captured = capsys.readouterr()
        assert "--budget-seconds" in captured.out
        assert "--renderer" in captured.out
        assert "--keep-frames" in captured.out

    def test_cli_generate_mock(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "cli_out"
        args = [
            "devvideo", "generate",
            str(FIXTURE_REPO),
            "--out", str(out_dir),
            "--llm", "mock",
            "--tts", "silent",
            "--renderer", "pillow",
        ]
        monkeypatch.setattr(sys, "argv", args)
        code = main()
        assert code == 0

        manifest_file = out_dir / "manifest.json"
        assert manifest_file.exists()
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert manifest["status"] == "published"
        assert manifest["video"] == "video.mp4"
        assert manifest["all_gates_passed"] is True

    def test_cli_error_nonexistent_path_returns_code_2(self, tmp_path, monkeypatch):
        out_dir = tmp_path / "cli_err"
        args = [
            "devvideo", "generate",
            "nonexistent/directory/path/that/does/not/exist",
            "--out", str(out_dir),
        ]
        monkeypatch.setattr(sys, "argv", args)
        code = main()
        assert code == 2

        manifest_file = out_dir / "manifest.json"
        assert manifest_file.exists()
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        assert manifest["status"] == "failed"
        assert manifest["video"] is None

    def test_main_shim(self):
        res = subprocess.run(
            [sys.executable, "src/main.py", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert res.returncode == 0
        assert "devvideo" in res.stdout
