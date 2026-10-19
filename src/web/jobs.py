"""
Job Manager for asynchronous video generation jobs.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..ingest.security import validate_github_url
from ..pipeline import run_pipeline

logger = logging.getLogger(__name__)


@dataclass
class JobRecord:
    job_id: str
    source: str
    status: str = "queued"  # queued | running | completed | failed
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    output_dir: str = ""
    error: str | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    video_available: bool = False
    duration_seconds: float = 0.0
    voice_used: str = "none"
    all_gates_passed: bool = False
    chapters: list[dict[str, Any]] = field(default_factory=list)


class JobManager:
    """Manages asynchronous video generation runs and status tracking."""

    def __init__(self, base_out_dir: Path | str = "out") -> None:
        self.base_out_dir = Path(base_out_dir).resolve()
        self.base_out_dir.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, JobRecord] = {}
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="VideoJob"
        )
        self._discover_existing()

    def _discover_existing(self) -> None:
        """Discover existing runs in base_out_dir or docs/sample for quick access."""
        candidates = []
        if self.base_out_dir.exists():
            candidates.extend(self.base_out_dir.glob("job_*"))
            # If default out/ has a video directly
            if (self.base_out_dir / "manifest.json").exists():
                candidates.append(self.base_out_dir)

        # Also check docs/sample
        sample_dir = self.base_out_dir.parent / "docs" / "sample"
        if sample_dir.exists() and (sample_dir / "manifest.json").exists():
            candidates.append(sample_dir)

        for d in candidates:
            if not d.is_dir():
                continue
            manifest_file = d / "manifest.json"
            if manifest_file.exists():
                try:
                    data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    jid = d.name if d.name.startswith("job_") else f"sample_{d.name}"
                    if jid not in self.jobs:
                        vid_file = d / "video.mp4"
                        if not vid_file.exists():
                            vid_file = d / "_rejected" / "video.mp4"
                        has_vid = vid_file.exists() and vid_file.stat().st_size > 0
                        chap_file = d / "chapters.json"
                        chaps = []
                        if chap_file.exists():
                            try:
                                chaps = json.loads(chap_file.read_text(encoding="utf-8"))
                            except Exception:
                                pass
                        self.jobs[jid] = JobRecord(
                            job_id=jid,
                            source=data.get("repo_name", "Pre-generated Sample"),
                            status="completed" if (data.get("all_gates_passed", False) or has_vid) else "failed",
                            output_dir=str(d),
                            manifest=data,
                            video_available=has_vid,
                            duration_seconds=data.get("video_duration_seconds", 0.0),
                            voice_used=data.get("voice", "auto"),
                            all_gates_passed=data.get("all_gates_passed", False),
                            chapters=chaps,
                        )
                except Exception as e:
                    logger.debug(f"Failed to index candidate run {d}: {e}")

    def validate_source(self, source: str) -> str:
        """Validate source GitHub URL or local repository path."""
        clean = source.strip()
        if not clean:
            raise ValueError("Repository source URL cannot be empty.")
        if clean.startswith("https://"):
            validate_github_url(clean)
            return clean
        # Local path check (useful for testing & development)
        p = Path(clean)
        if p.exists() and p.is_dir():
            return clean
        raise ValueError(
            f"Invalid source: {clean!r}. Must be a valid GitHub HTTPS URL (https://github.com/owner/repo) or local path."
        )

    def submit_job(
        self,
        source: str,
        llm: str = "auto",
        tts: str = "auto",
        voice: str | None = None,
        renderer: str = "auto",
        budget_seconds: float = 55.0,
        keep_frames: bool = False,
    ) -> JobRecord:
        """Create and queue a new video generation job."""
        valid_source = self.validate_source(source)
        ts = time.strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:6]
        job_id = f"job_{ts}_{uid}"
        job_dir = self.base_out_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        record = JobRecord(
            job_id=job_id,
            source=valid_source,
            status="queued",
            output_dir=str(job_dir),
            created_at=time.time(),
        )
        self.jobs[job_id] = record

        self._executor.submit(
            self._execute_pipeline,
            job_id=job_id,
            source=valid_source,
            output_dir=job_dir,
            llm=llm,
            tts=tts,
            voice=voice,
            renderer=renderer,
            budget_seconds=budget_seconds,
            keep_frames=keep_frames,
        )

        return record

    def _execute_pipeline(
        self,
        job_id: str,
        source: str,
        output_dir: Path,
        llm: str,
        tts: str,
        voice: str | None,
        renderer: str,
        budget_seconds: float,
        keep_frames: bool,
    ) -> None:
        """Worker function executing the pipeline."""
        rec = self.jobs[job_id]
        rec.status = "running"
        rec.started_at = time.time()
        logger.info(f"[Job {job_id}] Started generation for {source}")

        try:
            result = run_pipeline(
                source=source,
                output_dir=output_dir,
                llm_backend=llm,
                tts_backend=tts,
                voice=voice,
                renderer=renderer,
                budget_seconds=budget_seconds,
                keep_frames=keep_frames,
            )

            rec.completed_at = time.time()
            rec.manifest = result.manifest or {}
            vid_file = output_dir / "video.mp4"
            if not vid_file.exists():
                rejected_vid = output_dir / "_rejected" / "video.mp4"
                if rejected_vid.exists():
                    vid_file = rejected_vid
            rec.video_available = vid_file.exists() and vid_file.stat().st_size > 0
            rec.duration_seconds = rec.manifest.get("video_duration_seconds", 0.0)
            rec.voice_used = rec.manifest.get("voice", "auto")
            rec.all_gates_passed = rec.manifest.get("all_gates_passed", False)

            chap_file = output_dir / "chapters.json"
            if chap_file.exists():
                try:
                    rec.chapters = json.loads(chap_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            if rec.video_available:
                rec.status = "completed"
                if result.exit_code != 0:
                    rec.error = result.error or "Published with gate warning"
                logger.info(f"[Job {job_id}] Video ready: {vid_file}")
            else:
                rec.status = "failed"
                rec.error = result.error or f"Pipeline rejected (exit code {result.exit_code})"
                logger.warning(f"[Job {job_id}] Pipeline completed with exit code {result.exit_code}: {rec.error}")

        except Exception as e:
            rec.status = "failed"
            rec.completed_at = time.time()
            rec.error = str(e)
            logger.error(f"[Job {job_id}] Execution crashed: {e}", exc_info=True)

    def get_job(self, job_id: str) -> JobRecord | None:
        """Retrieve job record by ID."""
        return self.jobs.get(job_id)

    def list_recent(self, limit: int = 15) -> list[dict[str, Any]]:
        """List recent jobs sorted by creation time."""
        sorted_jobs = sorted(
            self.jobs.values(), key=lambda j: j.created_at, reverse=True
        )
        return [asdict(j) for j in sorted_jobs[:limit]]
