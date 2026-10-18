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

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "vidsearch_py"


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
        assert manifest["status"] in ("published", "published-no-voice")
        assert manifest["voice"] == "none"
        assert manifest["video"] == "video.mp4"
        assert manifest["all_gates_passed"] is True

    def test_cli_summary_printed_duration_matches_ffprobe(self, tmp_path, monkeypatch, capsys):
        """CLI prints video duration from ffprobe within 0.1s."""
        import re
        from src.tts import get_audio_duration
        out_dir = tmp_path / "cli_summary_test"
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

        captured = capsys.readouterr()
        m = re.search(r"Duration:\s*([\d.]+)s", captured.out)
        assert m, f"Duration not found in stdout: {captured.out}"
        printed_dur = float(m.group(1))

        mp4_path = out_dir / "video.mp4"
        assert mp4_path.exists()
        ffprobe_dur = get_audio_duration(mp4_path)

        assert abs(printed_dur - ffprobe_dur) <= 0.1, (
            f"Printed duration {printed_dur}s does not match ffprobe {ffprobe_dur}s within 0.1s"
        )
        assert "Voice: none" in captured.out
        assert "Gates:" in captured.out
        assert "Outputs:" in captured.out

    def test_run_yaml_independent_ffmpeg_espeak(self):
        """Assert run.yaml handles espeak-ng and ffmpeg in independent commands to prevent short-circuiting."""
        run_yaml_path = Path(__file__).resolve().parent.parent / "run.yaml"
        assert run_yaml_path.exists()
        content = run_yaml_path.read_text(encoding="utf-8")
        setup_cmds = []
        in_setup = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("setup_commands:"):
                in_setup = True
                continue
            if in_setup:
                if stripped.startswith("-"):
                    cmd = stripped.lstrip("- ").strip("\"'")
                    setup_cmds.append(cmd)
                elif stripped and not stripped.startswith("#"):
                    break

        ffmpeg_cmds = [cmd for cmd in setup_cmds if "ffmpeg" in cmd]
        espeak_cmds = [cmd for cmd in setup_cmds if "espeak-ng" in cmd]

        assert len(ffmpeg_cmds) >= 1, "ffmpeg setup command missing from run.yaml"
        assert len(espeak_cmds) >= 1, "espeak-ng setup command missing from run.yaml"

        # Assert they are not bundled in a single short-circuiting chain
        for cmd in setup_cmds:
            if "which espeak-ng" in cmd and "which ffmpeg" in cmd:
                assert False, f"run.yaml short-circuits espeak-ng and ffmpeg in one command: {cmd}"

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
