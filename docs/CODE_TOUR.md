# DevVideo Code Tour (5-Minute Technical Interview Guide)

This document provides a concise 2–3 sentence interview walkthrough for each source file in the repository.

---

### `src/ingest.py`
"This file forms our first security perimeter by sanitizing input repository URLs and isolating untrusted git operations. It runs shallow clones with disabled symlinks and hooks, caps repository scan sizes, and redacts sensitive credentials while hashing them for downstream verification. We designed it to ensure untrusted repositories can never escape into host filesystems or inject malicious commands."

### `src/analyze.py`
"This module parses codebases into a structured semantic `RepoFacts` object without ever executing repository code. It uses Python AST parsing and JavaScript regex extraction to build internal module import graphs, extract verbatim line ranges for top symbols, and parse CLI flags. We built it to give planners real, grounded structural data instead of relying on vague LLM summaries."

### `src/schema.py`
"This file defines our Pydantic data contracts for scenes, beats, on-screen visual assets, and timing models. It separates what is spoken from what is displayed on-screen, includes a phonetic speech normalizer for speech synthesis, and enforces strict bans on marketing buzzwords. We created it to ensure every single scene has explicit visual focus and timing boundaries."

### `src/plan.py`
"This module contains our planning protocol and implementations: the deterministic `OfflinePlanner` and the prompt-based `ClaudePlanner`. The offline planner generates a fact-conditional 7-scene explainer directly from AST facts, while the Claude planner communicates safely via standard input inside a nonce-delimited data block. We separated planning from rendering so that LLMs only determine narrative structure while tools supply verified code and diagrams."

### `src/reason.py`
"This file implements our verify-revise reasoning loop that inspects planned scripts before speech synthesis or frame rendering. It enforces lexical overlap between narration and cited quotes, checks command validity, and estimates duration against calibrated speech rates. We added this pre-synthesis verification loop so the system can automatically correct errors or gracefully degrade to a minimal 3-scene plan without crashing."

### `src/claude.py`
"This is our lightweight subprocess adapter for the Claude CLI tool that passes prompts strictly via standard input. It prevents command-line argument length overflows on Windows and catches timeouts, missing binaries, and non-zero exit codes into typed exceptions. We wrote it to keep LLM integration completely optional, dependency-free, and subprocess-isolated."

### `src/tts.py`
"This module orchestrates our speech synthesis chain by probing available backends at runtime in priority order from Edge TTS to espeak, SAPI5/pyttsx3, and silent fallback. It runs Windows pyttsx3 in an isolated subprocess to protect against COM thread deadlocks, normalizes all audio to 44.1 kHz PCM WAVs, and adds lead/tail acoustic pads. We enforced an atomic restart rule so that if any scene fails mid-run, the entire script restarts on the next backend to prevent mixed voices."

### `src/render.py`
"This is our precision frame renderer that generates 1280x720 visual cards using a single persistent Playwright Chromium browser with JavaScript disabled. It draws SVG dependency graphs, highlights verbatim code lines with Pygments to preserve exact whitespace indentation, and animates terminal commands. It also includes an independent Pillow fallback engine that measures font bounding boxes and explicitly flags dropped or overflowing lines."

### `src/assemble.py`
"This module handles media multiplexing and the creation of all multimodal companion outputs. It generates an FFmpeg concat-demuxer script with repeated final frame entries to guarantee perfect audio-video synchronization and muxes H.264 video with AAC audio. It also emits synchronized WebVTT subtitles, SRT transcripts, chapter markers, video thumbnails, and `index.jsonl` retrieval records."

### `src/repair.py`
"This file implements a bounded automated repair manager that makes up to two attempts to fix minor defects before triggering gate rejections. It can step down text lines to resolve visual overflow, accelerate speech rates or drop low-priority recap scenes to respect duration budgets, and replace invalid commands with verified ones from the repository. We designed it to maximize pipeline completion rates while strictly respecting hard gate thresholds."

### `src/evals/gates.py`
"This package contains the implementation of our nine runnable hard gates that dictate whether a video is published or rejected. It tests final duration via ffprobe, container stream drift, audio loudness via ffmpeg `volumedetect`, quote groundedness with lexical overlap, verbatim line matching, and command validity. We built it with independent secret regexes to ensure post-generation evaluation never trusts the ingest redaction logic."

### `src/evals/metrics.py`
"This module computes soft informational metrics such as domain relevance, visual scene coverage, words-per-minute speech rates, and clarity scores. Domain relevance is calculated using strict word-boundary token matching to eliminate false positives on common words. We separated soft metrics from hard gates so that informational metrics never block video publication."

### `src/evals/report.py`
"This module defines the typed `EvalGate` and `EvalReport` models and handles serialization to `eval_report.json`. It provides convenience properties such as `all_gates_passed` and formatted terminal summaries. We created it to ensure every execution leaves an unambiguous, auditable quality record."

### `src/pipeline.py`
"This is our top-level orchestrator that connects all seven stages into a unified linear pipeline. It tracks granular per-stage execution timings, handles quarantined video movement to `out/_rejected/` on gate failures, writes `manifest.json` on all outcomes, and triggers outbound webhooks. We structured it to guarantee that every run produces a complete audit trail regardless of whether it succeeded, was rejected, or crashed."

### `src/cli.py`
"This file provides the production command-line interface with standardized flags for backend selection, voice overrides, rendering engines, and webhook URLs. It returns standardized exit codes—0 for published, 1 for rejected gates, and 2 for errors—and ensures local directory inputs exist. We designed it to be directly scriptable in CI/CD workflows and automated containers."

### `tools/search_demo.py`
"This is a standalone, 58-line pure-Python TF-IDF retrieval tool that demonstrates the multimodal search utility of our generated video outputs. It loads `index.jsonl`, computes cosine similarity between search queries and beat narration, and prints the exact matching video timestamps. We built it to prove that our video explainers are directly usable by AI video retrieval and understanding engines."
