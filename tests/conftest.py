"""
Pytest configuration and CI guardrails.
Ensures that key integration tests marked 'must_run' cannot be silently skipped in CI.
"""

from __future__ import annotations

import os
import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "must_run: marks test as required in CI; skips are converted into failures",
    )


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
