# DevVideo Code Tour (5-Minute Technical Interview Guide)

This document provides a concise 2–3 sentence interview walkthrough for each modular package and key source file in the repository. Every module is strictly under 400 lines of code.

---

### `src/ingest/` (`security.py`, `collector.py`, `clone.py`)
"This package forms our first security perimeter by sanitizing input repository URLs and isolating untrusted git operations. `security.py` enforces shallow clones with symlinks disabled, blocks path traversal and private network targets, and redacts sensitive credentials. `collector.py` enforces size caps and harvests untrusted files safely, while `clone.py` orchestrates safe disk staging."

### `src/analyze/` (`readme.py`, `python_ast.py`, `js_graph.py`, `languages.py`, `relevance.py`)
"This package parses codebases into a structured semantic `RepoFacts` object without ever executing repository code. `readme.py` extracts genuine prose, title taglines, and bullet points without vendor noise; `python_ast.py` and `js_graph.py` parse AST trees to identify public symbols, call graphs, and entry points. `languages.py` filters vendored assets to report true first-party languages, and `relevance.py` calculates objective domain alignment."

### `src/schema.py`
"This module defines our Pydantic data contracts for scenes, beats, on-screen visual assets, source spans, and timing models. It separates what is spoken from what is displayed on-screen, includes phonetic speech normalizers, and enforces strict provenance rules (rejection of disallowed span formats). It guarantees that every single scene has explicit visual focus, timing boundaries, and verifiable evidence."

### `src/narrate/` (`compress.py`, `verbs.py`, `speech.py`, `scenes_*.py`)
"This package implements the Explainer Writer that drafts deterministic, extractive narration strictly obeying truth-first rules without filler. `compress.py` compresses sentences at natural clause boundaries rather than arbitrary truncation, while `verbs.py` handles deterministic bullet-to-sentence transformations. Each scene generator (`scenes_title.py`, `scenes_overview.py`, `scenes_diagram.py`, `scenes_code.py`, `scenes_terminal.py`, `scenes_fit.py`, `scenes_recap.py`) ensures spoken facts are fully grounded in cited spans."

### `src/timeline/` (`layout.py`, `animation.py`, `compiler.py`, `scenes_*.py`)
"This package compiles script scenes into visual layout models with precise per-beat timestamps and animation curves. `layout.py` and the scene layout helpers calculate exact spatial coordinates for chips, syntax-highlighted code windows, and terminal prompts. `animation.py` creates smooth ease-in transitions, and `compiler.py` verifies frame geometry across scenes."

### `src/render_html/` (`base.py`, `title.py`, `overview.py`, `diagram.py`, `code.py`, `terminal.py`, `fit.py`, `recap.py`)
"This package renders visual cards into self-contained HTML/CSS and drives Playwright Chromium to capture 1280x720 frames. `base.py` injects responsive CSS design tokens and Google Font typography without external CDN dependencies. Specialized modules generate DOM elements for architecture diagrams, Pygments-highlighted code, terminal sessions, and domain fit stage indicators."

### `src/tts/` (`engines.py`, `chain.py`)
"This package orchestrates speech synthesis across available engines (`edge` -> `piper` -> `espeak` -> `pyttsx3` -> `silent`). `engines.py` isolates engine-specific invocation and subprocessing to prevent COM thread deadlocks on Windows and normalizes audio to 44.1 kHz PCM WAV. `chain.py` enforces an atomic restart rule so that if any scene fails mid-run, the entire script restarts on the next engine to avoid mixed voices."

### `src/assemble.py`
"This module handles media multiplexing and the creation of multimodal companion outputs. It generates an FFmpeg concat-demuxer script with repeated final frame padding to guarantee perfect audio-video synchronization and muxes H.264 video with AAC audio. It also emits synchronized WebVTT subtitles, SRT transcripts, chapter markers, video thumbnails, and `index.jsonl` retrieval records."

### `src/evals/` (`registry.py`, `media_gates.py`, `text_gates.py`, `safety_gates.py`, `groundedness.py`, `gates.py`)
"This package contains the hard evaluation gates that dictate whether a video is published or rejected. `media_gates.py` checks duration, AV-sync drift, audio loudness, and visual motion; `text_gates.py` and `groundedness.py` enforce verbatim quotes, onscreen text integrity, and lack of filler. `safety_gates.py` prevents secret leaks and unsafe command execution; any failure quarantines the video to `out/_rejected/` with exit code 1."

### `src/pipeline/` (`models.py`, `runner.py`)
"This package orchestrates the end-to-end video generation pipeline from repository ingestion to final artifact publishing. `runner.py` tracks granular per-stage execution timings, handles quarantined video movement on gate failures, and writes `manifest.json`. `models.py` defines structured pipeline results and configuration parameters."

### `src/cli.py`
"This module provides the production command-line interface with standardized flags for backend selection, voice overrides, rendering engines, and webhook URLs. It returns standardized exit codes—0 for published, 1 for rejected gates, and 2 for errors—and validates inputs cleanly. It is designed for seamless integration into CI/CD workflows and automated containers."

### `tools/search_demo.py`
"This is a standalone, pure-Python TF-IDF retrieval tool that demonstrates the multimodal search utility of our generated video outputs. It loads `index.jsonl`, computes cosine similarity between search queries and beat narration, and prints matching video timestamps. It proves that generated videos are immediately indexable and searchable by AI video understanding and retrieval engines."
