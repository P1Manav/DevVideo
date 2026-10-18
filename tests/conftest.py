"""
Pytest configuration and CI guardrails.
Ensures that key integration tests marked 'must_run' cannot be silently skipped in CI,
and provides 'requires_voice' guardrail for voice-dependent tests.
"""

from __future__ import annotations

import os
import pytest


def has_voice_engine() -> bool:
    """Probe whether any real voice engine is available on the machine."""
    try:
        from src.tts import EdgeTTS, PiperTTS, EspeakTTS, Pyttsx3TTS
        for backend in [EdgeTTS(), PiperTTS(), EspeakTTS(), Pyttsx3TTS()]:
            if backend.probe():
                return True
    except Exception:
        pass
    return False


def check_requires_voice() -> None:
    """Check voice engine requirement; fail in CI, skip locally if absent."""
    is_ci = os.environ.get("CI", "").lower() in ("true", "1") or os.environ.get("DEVVIDEO_REQUIRE_VOICE") == "1"
    if not has_voice_engine():
        if is_ci:
            pytest.fail("CI error: Real voice engine (e.g. espeak-ng) required, but none was detected.")
        else:
            pytest.skip("No real voice engine available in local environment.")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "must_run: marks test as required in CI; skips are converted into failures",
    )
    config.addinivalue_line(
        "markers",
        "requires_voice: marks test as requiring a voice engine (fails in CI if missing, skips locally)",
    )


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("requires_voice"):
        check_requires_voice()


@pytest.fixture
def requires_voice():
    """Pytest fixture requiring a working voice engine."""
    check_requires_voice()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    outcome = yield
    report = outcome.get_result()

    ci_env = os.environ.get("CI", "").lower() in ("true", "1")
    if ci_env and report.skipped:
        must_run_marker = item.get_closest_marker("must_run")
        if must_run_marker:
            report.outcome = "failed"
            report.longrepr = f"CI failure: Test '{item.name}' marked @pytest.mark.must_run was skipped."
