"""
FastAPI Application for DevVideo Web Service.

Provides:
- Embedded Single Page Application frontend
- Asynchronous video generation API
- Video streaming & artifact downloads
- Health check endpoints (/healthz, /health)
- Keep-Alive background worker to prevent Render free-tier spin-down
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .frontend import get_index_html
from .jobs import JobManager
from .keep_alive import KeepAliveManager

logger = logging.getLogger(__name__)

job_manager = JobManager()
keep_alive_manager = KeepAliveManager()
_app_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager: start keep-alive worker on startup, stop on shutdown."""
    logger.info("DevVideo Web Service starting up...")
    keep_alive_manager.start()
    try:
        yield
    finally:
        logger.info("DevVideo Web Service shutting down...")
        keep_alive_manager.stop()


app = FastAPI(
    title="DevVideo Web Service",
    description="Generate developer walkthrough videos from GitHub repositories",
    version="0.2.0",
    lifespan=lifespan,
)


class GenerateRequest(BaseModel):
    source: str = Field(..., description="GitHub repository URL or local path")
    llm: str = Field(default="auto", description="LLM backend: auto | offline | claude | mock")
    tts: str = Field(default="auto", description="TTS backend: auto | edge | espeak | pyttsx3 | silent")
    voice: str | None = Field(default=None, description="Optional TTS voice override")
    renderer: str = Field(default="auto", description="Renderer backend: auto | playwright | pillow")
    budget_seconds: float = Field(default=55.0, description="Target duration budget in seconds")
    keep_frames: bool = Field(default=False, description="Whether to keep rendered frames")


@app.get("/", response_class=HTMLResponse)
def index_page() -> str:
    """Serve the single-page frontend application."""
    return get_index_html()


@app.get("/healthz")
@app.get("/health")
def health_check() -> dict[str, Any]:
    """Health check endpoint used by Render and the keep-alive monitor."""
    uptime = round(time.time() - _app_start_time, 1)
    status = keep_alive_manager.get_status()
    return {
        "status": "healthy",
        "service": "devvideo",
        "version": "0.2.0",
        "uptime_seconds": uptime,
        "keep_alive_enabled": status["enabled"],
        "total_pings": status["total_pings"],
        "last_ping_time": status["last_ping_time"],
        "render_detected": status["render_detected"],
        "active_jobs": sum(1 for j in job_manager.jobs.values() if j.status == "running"),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }


@app.get("/api/keepalive")
def get_keepalive_status() -> dict[str, Any]:
    """Return keep-alive monitor status and statistics."""
    return keep_alive_manager.get_status()


@app.post("/api/keepalive/ping")
def trigger_keepalive_ping() -> dict[str, Any]:
    """Manually trigger a keep-alive ping."""
    return keep_alive_manager.ping_once()


@app.post("/api/generate")
def create_generation_job(req: GenerateRequest) -> dict[str, Any]:
    """Start asynchronous video generation for a given GitHub repository."""
    try:
        job = job_manager.submit_job(
            source=req.source,
            llm=req.llm,
            tts=req.tts,
            voice=req.voice,
            renderer=req.renderer,
            budget_seconds=req.budget_seconds,
            keep_frames=req.keep_frames,
        )
        return {
            "job_id": job.job_id,
            "source": job.source,
            "status": job.status,
            "created_at": job.created_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to submit job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/jobs")
def list_jobs() -> list[dict[str, Any]]:
    """List recent and sample jobs."""
    return job_manager.list_recent()


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> dict[str, Any]:
    """Get status and details of a specific job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    out_p = Path(job.output_dir)
    vid_p = out_p / "video.mp4"
    if not vid_p.exists():
        vid_p = out_p / "_rejected" / "video.mp4"
    has_vid = vid_p.exists() and vid_p.stat().st_size > 0

    return {
        "job_id": job.job_id,
        "source": job.source,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "duration_seconds": job.duration_seconds,
        "voice_used": job.voice_used,
        "all_gates_passed": job.all_gates_passed,
        "error": job.error,
        "video_available": has_vid,
        "transcript_available": (out_p / "transcript.vtt").exists(),
        "thumbnail_available": (out_p / "thumbnail.png").exists(),
        "chapters": job.chapters,
        "manifest": job.manifest,
    }


@app.get("/api/jobs/{job_id}/video")
def get_job_video(job_id: str) -> FileResponse:
    """Stream or download the generated MP4 video."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    vid_path = Path(job.output_dir) / "video.mp4"
    if not vid_path.exists() or vid_path.stat().st_size == 0:
        vid_path = Path(job.output_dir) / "_rejected" / "video.mp4"

    if not vid_path.exists() or vid_path.stat().st_size == 0:
        raise HTTPException(status_code=404, detail="Video file not available for this job")

    return FileResponse(
        path=str(vid_path),
        media_type="video/mp4",
        filename=f"walkthrough_{job.job_id}.mp4",
    )


_ALLOWED_ARTIFACTS = {
    "transcript.vtt": "text/vtt",
    "transcript.srt": "text/plain",
    "thumbnail.png": "image/png",
    "chapters.json": "application/json",
    "manifest.json": "application/json",
    "eval_report.json": "application/json",
    "narration.txt": "text/plain",
}


@app.get("/api/jobs/{job_id}/artifact/{filename}")
def get_job_artifact(job_id: str, filename: str) -> FileResponse:
    """Download job artifacts (subtitles, thumbnails, manifests)."""
    if filename not in _ALLOWED_ARTIFACTS:
        raise HTTPException(status_code=403, detail="Requested artifact type not permitted")

    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    target = Path(job.output_dir) / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Artifact {filename} not found")

    return FileResponse(
        path=str(target),
        media_type=_ALLOWED_ARTIFACTS[filename],
        filename=filename,
    )
