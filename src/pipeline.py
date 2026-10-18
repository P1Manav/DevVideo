"""
Pipeline orchestrator: linear generation pipeline with bounded loops and hard eval gates.

Architecture v2:
1. Ingest   : safe clone/read, secret redaction & recording
2. Analyze  : RepoFacts (AST & regex analysis, cleaned README)
3. Plan     : ScriptPlan via reason-and-plan verify loop
4. Voice    : multi-backend TTS chain, calibration, beat timing
5. Render   : Playwright singleton or Pillow fallback, SVG & syntax highlighting
6. Assemble : concat-demuxer, audio mux, VTT, SRT, chapters, index, thumbnail
7. Evals    : 9 hard gates, video moved to out/_rejected/ on gate failure
8. Output   : manifest.json & webhook notification on all outcomes
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .analyze import analyze_repository
from .assemble import (
    SceneAsset,
    assemble_video_from_timeline,
    concat_audio_files,
    generate_chapters,
    generate_index_jsonl,
    generate_subtitles,
    generate_thumbnail,
    measure_scene_durations,
)
from .evals import EvalReport, run_eval
from .ingest import RepoContent, ingest_github, ingest_local
from .llm import select_planners

from .reason import reason_and_plan
from .render import PlaywrightRenderer, render_scene_to_png
from .repair import RepairManager
from .schema import ScriptPlan
from .timeline import expand_script_to_timeline
from .tts import get_audio_duration, synthesize_scenes_chain
from .webhook import send_webhook

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of the full pipeline run."""
    success: bool = False
    exit_code: int = 0  # 0: published, 1: rejected, 2: error
    video_path: Path | None = None
    script: ScriptPlan | None = None
    eval_report: EvalReport | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    error: str = ""


def get_git_sha(repo_dir: Path | None = None) -> str:
    """Retrieve git HEAD sha from repo directory or current repo."""
    try:
        cmd = ["git", "rev-parse", "HEAD"]
        res = subprocess.run(cmd, cwd=str(repo_dir) if repo_dir else None, capture_output=True, text=True, timeout=5)
        return res.stdout.strip() if res.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def get_environment_versions() -> dict[str, str]:
    """Retrieve environment versions for Python, ffmpeg, and Playwright."""
    versions = {"python": sys.version.split()[0]}
    if shutil.which("ffmpeg"):
        try:
            res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
            m = re.search(r"ffmpeg version (\S+)", res.stdout)
            versions["ffmpeg"] = m.group(1) if m else "available"
        except Exception:
            versions["ffmpeg"] = "available"
    else:
        versions["ffmpeg"] = "not_found"

    try:
        import playwright
        versions["playwright"] = getattr(playwright, "__version__", "installed")
    except Exception:
        versions["playwright"] = "not_installed"

    return versions


def run_pipeline(
    source: str,
    output_dir: Path,
    llm_backend: str | None = None,
    tts_backend: str | None = None,
    voice: str | None = None,
    renderer: str | None = None,
    use_playwright: bool = True,
    budget_seconds: float = 55.0,
    webhook_url: str | None = None,
    keep_frames: bool = False,
) -> PipelineResult:
    """
    Run the end-to-end explainer video generation pipeline.
    """
    start_time = time.time()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = PipelineResult()

    timings: dict[str, float] = {}
    current_stage = "init"

    req_llm = llm_backend or os.environ.get("LLM_BACKEND", "auto")
    req_tts = tts_backend or os.environ.get("TTS_BACKEND", "auto")
    req_renderer = renderer or ("playwright" if use_playwright else "pillow")

    llm_used, llm_fallback_reason = req_llm, ""
    tts_used, tts_fallback_reason = "silent", ""
    renderer_used = "fallback_pillow" if req_renderer == "pillow" else "playwright"
    renderer_fallback_reason = "Pillow specified by caller" if req_renderer == "pillow" else ""

    tool_sha = get_git_sha()
    input_sha = "unknown"
    repair_manager = RepairManager()

    playwright_instance: PlaywrightRenderer | None = None

    try:
        # -------------------------------------------------------------------
        # 1. Ingest
        # -------------------------------------------------------------------
        current_stage = "ingest"
        t0 = time.time()
        logger.info(f"Stage 1 [Ingest]: from {source}")
        if source.startswith("https://"):
            repo = ingest_github(source)
        else:
            repo = ingest_local(source)

        input_sha = repo.commit_sha or "unknown"
        timings["ingest"] = round(time.time() - t0, 2)
        logger.info(f"Ingested {len(repo.files)} files from {repo.repo_name}")

        # -------------------------------------------------------------------
        # 2. Analyze
        # -------------------------------------------------------------------
        current_stage = "analyze"
        t0 = time.time()
        logger.info("Stage 2 [Analyze]: Computing RepoFacts")
        facts = analyze_repository(repo)
        timings["analyze"] = round(time.time() - t0, 2)

        # -------------------------------------------------------------------
        # 3. Plan & Reason
        # -------------------------------------------------------------------
        current_stage = "plan"
        t0 = time.time()
        logger.info(f"Stage 3 [Plan]: Planning script with LLM={req_llm}")

        planners, llm_requested, initial_fallback = select_planners(req_llm)
        script, revision_history, llm_used, llm_fallback_reason = reason_and_plan(
            facts=facts,
            repo_files=repo.files,
            planners=planners,
            max_duration=budget_seconds,
        )
        if not llm_fallback_reason and initial_fallback:
            llm_fallback_reason = initial_fallback


        result.script = script
        script_path = output_dir / "scenes.json"
        script_path.write_text(script.model_dump_json(indent=2), encoding="utf-8")
        timings["plan"] = round(time.time() - t0, 2)

        # -------------------------------------------------------------------
        # 4. Voice (TTS)
        # -------------------------------------------------------------------
        current_stage = "voice"
        t0 = time.time()
        logger.info(f"Stage 4 [Voice]: Synthesizing speech with TTS={req_tts}")
        audio_dir = output_dir / "audio"
        tts_used, tts_fallback_reason, calibrated_wpm, wav_paths = synthesize_scenes_chain(
            scenes=script.scenes,
            audio_dir=audio_dir,
            requested_backend=req_tts,
            voice=voice,
        )

        total_audio_dur = sum(s.duration_seconds for s in script.scenes)
        rate_multiplier = 1.0
        # Duration repair if over budget: +8% rate once, then drop recap bullets, then drop lowest-priority scene
        while total_audio_dur > budget_seconds + 3.0 and repair_manager.can_repair():
            action, rate_multiplier = repair_manager.repair_duration(script, rate_multiplier=rate_multiplier)
            if action in ("no_action", "max_attempts_exceeded"):
                break
            # Re-synthesize after repair
            tts_used, tts_fallback_reason, calibrated_wpm, wav_paths = synthesize_scenes_chain(
                scenes=script.scenes,
                audio_dir=audio_dir,
                requested_backend=tts_used,
                voice=voice,
                rate_multiplier=rate_multiplier,
            )
            total_audio_dur = sum(s.duration_seconds for s in script.scenes)

        timings["voice"] = round(time.time() - t0, 2)

        # -------------------------------------------------------------------
        # 5. Render
        # -------------------------------------------------------------------
        current_stage = "render"
        t0 = time.time()
        logger.info(f"Stage 5 [Render]: Rendering frames with renderer={req_renderer}")
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        use_pw = (req_renderer != "pillow")
        if use_pw:
            try:
                playwright_instance = PlaywrightRenderer()
                playwright_instance.start()
            except Exception as e:
                logger.warning(f"Failed to start Playwright ({e}); falling back to Pillow")
                use_pw = False
                renderer_used = "fallback_pillow"
                renderer_fallback_reason = str(e)

        audio_durs = [get_audio_duration(p) for p in wav_paths]
        frame_states = expand_script_to_timeline(script, facts, scene_audio_durations=audio_durs)

        timeline: list[tuple[Path, float]] = []
        frame_paths: list[Path] = []
        overflow_scenes: list[str] = []

        for f_idx, state in enumerate(frame_states):
            scene_obj = next((s for s in script.scenes if s.id == state.scene_id), script.scenes[0])
            content_val = scene_obj.on_screen.content if (scene_obj.on_screen and scene_obj.on_screen.content) else ""
            meta_val = scene_obj.on_screen.metadata if (scene_obj.on_screen and scene_obj.on_screen.metadata) else {}

            frame_file = frames_dir / f"frame_{f_idx:03d}_{state.scene_id}_{state.state_kind}.png"
            s_data = dict(state.state_data or {})
            s_data["state_index"] = f_idx
            res = render_scene_to_png(
                scene_id=state.scene_id,
                content_type=state.scene_kind,
                content=content_val,
                narration=state.caption,
                repo_name=script.repo_name,
                output_path=frame_file,
                use_playwright=use_pw,
                playwright_renderer=playwright_instance,
                all_scene_titles=state.all_scene_titles,
                current_scene_idx=state.current_scene_idx,
                progress_pct=state.progress_pct,
                metadata=meta_val,
                active_focus=state.active_focus,
                state_kind=state.state_kind,
                state_data=s_data,
            )
            if res.has_overflow:
                overflow_scenes.append(state.scene_id)
            timeline.append((frame_file, state.duration_seconds))
            frame_paths.append(frame_file)

        if playwright_instance:
            playwright_instance.close()

        timings["render"] = round(time.time() - t0, 2)

        # -------------------------------------------------------------------
        # 6. Assemble
        # -------------------------------------------------------------------
        current_stage = "assemble"
        t0 = time.time()
        logger.info("Stage 6 [Assemble]: Concatenating audio and muxing MP4")
        narration_wav = output_dir / "narration.wav"
        concat_audio_files(wav_paths, narration_wav)

        video_path = output_dir / "video.mp4"
        final_video_dur = assemble_video_from_timeline(timeline, narration_wav, video_path)

        # Generate companion outputs
        generate_subtitles(script.scenes, output_dir / "transcript.vtt", output_dir / "transcript.srt")
        generate_chapters(script.scenes, output_dir / "chapters.json")
        generate_index_jsonl(script.scenes, output_dir / "index.jsonl")
        generate_thumbnail(video_path, frame_paths[0] if frame_paths else None, output_dir / "thumbnail.png")

        timings["assemble"] = round(time.time() - t0, 2)

        # -------------------------------------------------------------------
        # 7. Eval Gates
        # -------------------------------------------------------------------
        current_stage = "eval"
        t0 = time.time()
        logger.info("Stage 7 [Eval]: Running all 9 hard evaluation gates")
        scene_durs = [s.duration_seconds for s in script.scenes]
        audio_durs = [get_audio_duration(p) for p in wav_paths]

        eval_report = run_eval(
            script=script,
            repo_files=repo.files,
            video_duration=final_video_dur,
            mp4_path=video_path,
            scene_durations=scene_durs,
            audio_durations=audio_durs,
            ingest_secrets=repo.redacted_secrets,
            frame_paths=frame_paths,
            overflow_scenes=overflow_scenes,
            backend_requested=req_llm,
            backend_used=llm_used,
            fallback_reason=llm_fallback_reason,
            tts_used=tts_used,
            renderer_used=renderer_used,
            renderer_fallback_reason=renderer_fallback_reason,
            calibrated_wpm=calibrated_wpm,
            facts=facts,
        )
        result.eval_report = eval_report
        eval_report.save(output_dir / "eval_report.json")
        timings["eval"] = round(time.time() - t0, 2)

        # -------------------------------------------------------------------
        # 8. Publication / Rejection Gate Check
        # -------------------------------------------------------------------
        if eval_report.all_gates_passed:
            result.success = True
            result.exit_code = 0
            result.video_path = video_path
            if tts_used == "silent":
                video_status = "published-no-voice"
                sys.stderr.write(
                    "\n"
                    "======================================================================\n"
                    "WARNING: DevVideo generated a silent video (voice: none)!\n"
                    "No functional text-to-speech voice engine was found or available.\n"
                    "For full audio narration, please install espeak-ng or configure\n"
                    "internet access for Edge Neural TTS.\n"
                    "======================================================================\n\n"
                )
                logger.warning("Published video with no voice engine (silent fallback).")
            else:
                video_status = "published"
            video_rel_path = "video.mp4"
            video_sha = hashlib.sha256(video_path.read_bytes()).hexdigest()
            logger.info(f"All gates passed! Published {video_path} ({final_video_dur:.1f}s)")
        else:
            result.success = False
            result.exit_code = 1
            video_status = "rejected"
            rejected_dir = output_dir / "_rejected"
            rejected_dir.mkdir(parents=True, exist_ok=True)
            rejected_video = rejected_dir / "video.mp4"
            if video_path.exists():
                shutil.move(str(video_path), str(rejected_video))
            video_rel_path = "_rejected/video.mp4"
            video_sha = hashlib.sha256(rejected_video.read_bytes()).hexdigest() if rejected_video.exists() else None
            failed_gates = [g.name for g in eval_report.gates if not g.passed and getattr(g, "blocking", True)]
            result.error = f"Eval gates failed: {failed_gates}"
            logger.warning(f"Gate check failed: {failed_gates}. Video moved to {rejected_video}")

        # Clean up frames if not requested
        if not keep_frames and frames_dir.exists():
            shutil.rmtree(frames_dir, ignore_errors=True)

        timings["total"] = round(time.time() - start_time, 2)

        # -------------------------------------------------------------------
        # 9. Manifest & Webhook
        # -------------------------------------------------------------------
        manifest = {
            "status": video_status,
            "voice": "none" if tts_used == "silent" else tts_used,
            "tool_git_sha": tool_sha,
            "input_repo_commit_sha": input_sha,
            "repo_name": repo.repo_name,
            "versions": get_environment_versions(),
            "timings": timings,
            "backend_requested": req_llm,
            "backend_used": llm_used,
            "tts_requested": req_tts,
            "tts_used": tts_used,
            "tts_backend": tts_used,
            "tts_fallback_reason": tts_fallback_reason,
            "llm_requested": req_llm,
            "llm_used": llm_used,
            "llm_fallback_reason": llm_fallback_reason,
            "renderer_requested": req_renderer,
            "renderer_used": renderer_used,
            "renderer_fallback_reason": renderer_fallback_reason,
            "video": video_rel_path if eval_report.all_gates_passed else None,
            "video_sha256": video_sha,
            "video_duration_seconds": round(final_video_dur, 2),
            "eval_report": "eval_report.json",
            "all_gates_passed": eval_report.all_gates_passed,
        }
        result.manifest = manifest
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        target_webhook = webhook_url or os.environ.get("WEBHOOK_URL")
        if target_webhook:
            evt = "video.generated" if eval_report.all_gates_passed else "video.rejected"
            send_webhook(url=target_webhook, payload={"event": evt, "manifest": manifest})

    except Exception as e:
        logger.error(f"Pipeline failed at stage [{current_stage}]: {e}", exc_info=True)
        result.success = False
        result.exit_code = 1 if "DEVVIDEO_REQUIRE_VOICE" in str(e) else 2
        result.error = f"Stage [{current_stage}] failed: {e}"

        timings["total"] = round(time.time() - start_time, 2)
        manifest = {
            "status": "failed",
            "error": str(e),
            "failed_stage": current_stage,
            "tool_git_sha": tool_sha,
            "input_repo_commit_sha": input_sha,
            "versions": get_environment_versions(),
            "timings": timings,
            "backend_requested": req_llm,
            "backend_used": llm_used,
            "tts_requested": req_tts,
            "tts_used": tts_used,
            "tts_backend": tts_used,
            "tts_fallback_reason": tts_fallback_reason,
            "llm_requested": req_llm,
            "llm_used": llm_used,
            "llm_fallback_reason": llm_fallback_reason,
            "renderer_requested": req_renderer,
            "renderer_used": renderer_used,
            "renderer_fallback_reason": renderer_fallback_reason,
            "video": None,
            "video_sha256": None,
            "all_gates_passed": False,
        }
        result.manifest = manifest
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        target_webhook = webhook_url or os.environ.get("WEBHOOK_URL")
        if target_webhook:
            send_webhook(url=target_webhook, payload={"event": "video.failed", "manifest": manifest})

    finally:
        if playwright_instance:
            try:
                playwright_instance.close()
            except Exception:
                pass

    return result


def _build_prompt(repo: Any) -> str:
    """Build prompt for LLM containing repository content (backwards compatibility)."""
    files = getattr(repo, "files", {})
    file_contents = ""
    for path, content in files.items():
        file_contents += f"\n--- FILE: {path} ---\n{content}\n"

    repo_name = getattr(repo, "repo_name", "unknown")
    owner = getattr(repo, "owner", "")
    return f"""Repository: {repo_name}
Owner: {owner}
{file_contents}
"""
