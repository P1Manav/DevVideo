"""
Unit and integration tests for DevVideo Web Service, Frontend, and Keep-Alive Worker.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.cli import main as cli_main
from src.web.app import app, job_manager
from src.web.keep_alive import KeepAliveManager


@pytest.fixture
def client():
    """Create test client with lifespan handling."""
    with TestClient(app) as test_client:
        yield test_client


def test_index_page(client):
    """GET / returns the HTML frontend with video player, input form, and keep-alive status."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    html = res.text
    assert "DevVideo" in html
    assert "<video" in html
    assert "Generate Video" in html
    assert "Keep-Alive Active" in html
    assert "/healthz" in html


def test_health_endpoints(client):
    """GET /healthz and /health return 200 OK and health statistics for Render."""
    for path in ["/healthz", "/health"]:
        res = client.get(path)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert data["service"] == "devvideo"
        assert "uptime_seconds" in data
        assert "total_pings" in data
        assert "render_detected" in data
        assert "timestamp" in data


def test_keep_alive_resolution(monkeypatch):
    """KeepAliveManager resolves RENDER_EXTERNAL_URL, KEEP_ALIVE_URL, or localhost."""
    # 1. Default localhost
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("KEEP_ALIVE_URL", raising=False)
    monkeypatch.setenv("PORT", "10000")
    mgr = KeepAliveManager()
    assert mgr.resolve_target_url() == "http://127.0.0.1:10000/healthz"

    # 2. RENDER_EXTERNAL_URL
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://devvideo.onrender.com")
    mgr2 = KeepAliveManager()
    assert mgr2.resolve_target_url() == "https://devvideo.onrender.com/healthz"

    # 3. KEEP_ALIVE_URL override
    monkeypatch.setenv("KEEP_ALIVE_URL", "https://custom-proxy.internal")
    mgr3 = KeepAliveManager()
    assert mgr3.resolve_target_url() == "https://custom-proxy.internal/healthz"


def test_keep_alive_status_and_ping():
    """KeepAliveManager tracks ping status and handles responses."""
    mgr = KeepAliveManager(interval_seconds=60)
    status = mgr.get_status()
    assert status["enabled"] is True
    assert status["total_pings"] == 0
    assert status["successful_pings"] == 0

    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_open.return_value.__enter__.return_value = mock_resp

        res = mgr.ping_once()
        assert res["success"] is True
        assert res["status_code"] == 200
        assert mgr.total_pings == 1
        assert mgr.successful_pings == 1
        assert mgr.last_latency_ms is not None


def test_job_validation():
    """JobManager validates GitHub URLs and local paths, rejecting malicious inputs."""
    # Valid GitHub URL
    valid = job_manager.validate_source("https://github.com/psf/requests")
    assert valid == "https://github.com/psf/requests"

    # Valid local path
    fixture_dir = str(Path(__file__).parent / "fixtures" / "vidsearch_py")
    assert job_manager.validate_source(fixture_dir) == fixture_dir

    # Invalid empty
    with pytest.raises(ValueError, match="empty"):
        job_manager.validate_source("   ")

    # Invalid scheme / path traversal
    with pytest.raises(ValueError):
        job_manager.validate_source("https://github.com/../../etc")

    with pytest.raises(ValueError):
        job_manager.validate_source("ftp://github.com/foo/bar")


def test_api_jobs_endpoints(client):
    """Test job listing, details, and artifact endpoints."""
    # List jobs
    res = client.get("/api/jobs")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # Unknown job 404
    res_404 = client.get("/api/jobs/job_nonexistent_xyz")
    assert res_404.status_code == 404

    # Unknown video 404
    res_vid_404 = client.get("/api/jobs/job_nonexistent_xyz/video")
    assert res_vid_404.status_code == 404

    # Forbidden artifact
    res_forbid = client.get("/api/jobs/job_nonexistent_xyz/artifact/secret.env")
    assert res_forbid.status_code == 403


def test_cli_serve_help(monkeypatch, capsys):
    """devvideo serve --help shows host and port options."""
    monkeypatch.setattr(sys, "argv", ["devvideo", "serve", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli_main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "--host" in captured.out
    assert "--port" in captured.out
