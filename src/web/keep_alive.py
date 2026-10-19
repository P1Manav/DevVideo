"""
Render Keep-Alive & Health Check Worker.

Pings the deployment endpoint once a minute (default 60s) to prevent
Render free-tier instances from spinning down due to inactivity.
Detects RENDER_EXTERNAL_URL automatically.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class KeepAliveManager:
    """Background worker that periodically pings the web service to prevent Render spin-down."""

    def __init__(
        self,
        interval_seconds: float = 60.0,
        target_url: str | None = None,
        enabled: bool = True,
    ) -> None:
        self.interval_seconds = float(
            os.environ.get("KEEP_ALIVE_INTERVAL_SECONDS", interval_seconds)
        )
        self.target_url_override = target_url or os.environ.get("KEEP_ALIVE_URL")
        self.enabled = os.environ.get("KEEP_ALIVE_ENABLED", str(enabled)).lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.port = int(os.environ.get("PORT", "10000"))

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.start_time = time.time()
        self.total_pings = 0
        self.successful_pings = 0
        self.failed_pings = 0
        self.last_ping_time: float | None = None
        self.last_status_code: int | None = None
        self.last_latency_ms: float | None = None
        self.last_error: str | None = None

    def resolve_target_url(self) -> str:
        """Resolve target URL: RENDER_EXTERNAL_URL > KEEP_ALIVE_URL > localhost."""
        if self.target_url_override:
            base = self.target_url_override.rstrip("/")
            return base if base.endswith("/healthz") else f"{base}/healthz"

        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if render_url:
            base = render_url.rstrip("/")
            return base if base.endswith("/healthz") else f"{base}/healthz"

        return f"http://127.0.0.1:{self.port}/healthz"

    def ping_once(self) -> dict[str, Any]:
        """Perform a single HTTP GET ping to the resolved target URL."""
        target = self.resolve_target_url()
        self.total_pings += 1
        self.last_ping_time = time.time()
        t0 = time.time()

        req = urllib.request.Request(
            target,
            headers={
                "User-Agent": "DevVideo-Render-KeepAlive/1.0",
                "X-Keep-Alive-Ping": "true",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                code = resp.getcode()
                latency_ms = round((time.time() - t0) * 1000, 2)
                self.last_status_code = code
                self.last_latency_ms = latency_ms
                self.last_error = None
                self.successful_pings += 1
                logger.info(
                    f"[KeepAlive] Ping OK: {target} (status={code}, latency={latency_ms}ms, ping_count={self.total_pings})"
                )
                return {
                    "success": True,
                    "target": target,
                    "status_code": code,
                    "latency_ms": latency_ms,
                }
        except urllib.error.HTTPError as e:
            latency_ms = round((time.time() - t0) * 1000, 2)
            self.last_status_code = e.code
            self.last_latency_ms = latency_ms
            self.last_error = f"HTTP {e.code}: {e.reason}"
            # An HTTP response still wakes up Render ingress
            self.successful_pings += 1
            logger.warning(
                f"[KeepAlive] Ping HTTP status {e.code} for {target} (latency={latency_ms}ms)"
            )
            return {
                "success": True,
                "target": target,
                "status_code": e.code,
                "latency_ms": latency_ms,
            }
        except Exception as e:
            latency_ms = round((time.time() - t0) * 1000, 2)
            self.last_status_code = None
            self.last_latency_ms = latency_ms
            self.last_error = str(e)
            self.failed_pings += 1
            logger.warning(f"[KeepAlive] Ping failed for {target}: {e}")
            return {
                "success": False,
                "target": target,
                "error": str(e),
                "latency_ms": latency_ms,
            }

    def _run_loop(self) -> None:
        """Internal background loop running approximately once a minute."""
        logger.info(
            f"[KeepAlive] Worker started. Interval: {self.interval_seconds}s. Target: {self.resolve_target_url()}"
        )
        # Initial brief delay to let uvicorn finish binding
        if self._stop_event.wait(5.0):
            return

        while not self._stop_event.is_set():
            if self.enabled:
                self.ping_once()
            # Wait for interval or stop event
            if self._stop_event.wait(self.interval_seconds):
                break

        logger.info("[KeepAlive] Worker stopped.")

    def start(self) -> None:
        """Start the background keep-alive loop."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="KeepAliveWorker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background keep-alive loop gracefully."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None

    def get_status(self) -> dict[str, Any]:
        """Return comprehensive status of the keep-alive monitor."""
        target = self.resolve_target_url()
        is_render = "RENDER_EXTERNAL_URL" in os.environ or "RENDER" in os.environ
        return {
            "enabled": self.enabled,
            "is_running": self._thread is not None and self._thread.is_alive(),
            "target_url": target,
            "render_detected": is_render,
            "render_external_url": os.environ.get("RENDER_EXTERNAL_URL"),
            "interval_seconds": self.interval_seconds,
            "uptime_seconds": round(time.time() - self.start_time, 1),
            "total_pings": self.total_pings,
            "successful_pings": self.successful_pings,
            "failed_pings": self.failed_pings,
            "last_ping_time": (
                time.strftime(
                    "%Y-%m-%d %H:%M:%S UTC", time.gmtime(self.last_ping_time)
                )
                if self.last_ping_time
                else None
            ),
            "last_status_code": self.last_status_code,
            "last_latency_ms": self.last_latency_ms,
            "last_error": self.last_error,
        }
