# Architecture Diagram Description (draw.io)

This document describes the architecture diagram for the DevVideo pipeline.
Import the XML below into [draw.io](https://app.diagrams.net/) to view/edit.

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DevVideo Pipeline                                │
│                                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────────┐ │
│  │  CLI      │──►│   Ingest     │──►│ Plan+Script│──►│    Verify     │ │
│  │ (cli.py)  │   │ (ingest.py)  │   │ (llm.py)   │   │  (verify.py)  │ │
│  └──────────┘   └──────────────┘   └──────────────┘   └───────┬───────┘ │
│                                                               │ ▲       │
│                                                          pass │ │ fail  │
│                                                               │ │ retry │
│                                                               ▼ │       │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────────┐ │
│  │  Eval    │◄──│   Assemble   │◄──│   Render   │◄──│    TTS        │ │
│  │(evals.py)│   │(assemble.py) │   │ (render.py)│   │  (tts.py)     │ │
│  └────┬─────┘   └──────────────┘   └────────────┘   └───────────────┘ │
│       │                                                                 │
│       ▼                                                                 │
│  ┌──────────────────────────────────┐                                   │
│  │ eval_report.json + manifest.json │                                   │
│  │ + video.mp4                      │                                   │
│  └──────────────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘

External Dependencies:
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │  GitHub  │  │ Claude   │  │ Edge TTS │  │  ffmpeg  │
  │  (clone) │  │ CLI (opt)│  │  (opt)   │  │          │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

## Component Details

### 1. CLI Layer (cli.py)
- Entry point: `python -m src.cli generate <source> --out <dir>`
- Parses arguments, sets up logging
- Calls pipeline.run_pipeline()
- Handles webhook POST on completion

### 2. Pipeline Orchestrator (pipeline.py)
- Coordinates the 7-step flow
- Manages the verify-revise loop (max 2 retries)
- Produces manifest.json with full audit trail

### 3. Ingest (ingest.py)
- **Input**: GitHub URL or local path
- **Security**: URL allowlist, hooks disabled, secret redaction
- **Output**: RepoContent (repo_name, owner, files dict)
- **Caps**: 50 files max, 100KB/file, 500KB total

### 4. LLM Adapter (llm.py)
- **Protocol**: LLMBackend.complete(prompt) -> str
- **Backends**: auto (default), offline (deterministic extractive planner), mock (test only), claude (subprocess)
- **Auto logic**: claude if on PATH + CLAUDE_KEY, else offline planner
- **Prompt**: Repo text in UNTRUSTED DATA block

### 5. Verify (verify.py)
- **Deterministic checks**: evidence grounding, secrets, duration
- **Output**: VerifyResult(ok, errors, warnings)
- **Loop**: On failure, errors fed back to LLM for retry

### 6. TTS (tts.py)
- **Protocol**: TTSBackend.synthesize(text, output_path) -> None
- **Backends**: silent (WAV silence), edge (Microsoft), espeak (local)
- **Auto**: edge → espeak → silent

### 7. Render (render.py)
- **Input**: Scene data (id, type, content, narration)
- **Process**: HTML card → Playwright screenshot (JS disabled)
- **Fallback**: Pillow structured rendering with real scene text and badges
- **Security**: All text HTML-escaped

### 8. Assemble (assemble.py)
- **Input**: PNG frames + WAV audio per scene
- **Process**: ffmpeg per-scene segments → concat → MP4
- **Duration**: scene_duration = audio_length + 0.3s padding

### 9. Eval (evals.py)
- **Hard gates**: duration ≤ 60s, secrets = 0 (script + raw input), groundedness = 100%, command validity = 100%, no text overflow, drift ≤ 0.5s
- **Metrics**: domain_relevance, clarity (LLM judge or skipped)
- **Output**: eval_report.json

## Data Flow

```
GitHub URL
    │
    ▼
validate_github_url() ──► ValueError if invalid
    │
    ▼
clone_repo() ──► shallow clone, hooks disabled
    │
    ▼
collect_files() ──► priority files first, caps applied
    │
    ▼
redact_secrets() ──► regex + entropy check
    │
    ▼
RepoContent {repo_name, owner, files: {path: content}}
    │
    ▼
_build_prompt() ──► UNTRUSTED DATA block
    │
    ▼
LLM.complete(prompt) ──► raw JSON string
    │
    ▼
_parse_llm_response() ──► ScriptPlan (pydantic validated)
    │
    ▼
verify_script() ──► VerifyResult
    │               │
    │ (ok)          │ (fail, retry ≤ 2)
    ▼               └──► append errors to prompt, retry
    │
TTS.synthesize() ──► per-scene .wav files
    │
    ▼
render_scene_to_png() ──► per-scene .png files
    │
    ▼
assemble_video() ──► video.mp4
    │
    ▼
run_eval() ──► eval_report.json + manifest.json
```

## draw.io XML

To recreate this diagram in draw.io, create a new diagram and use the
"Arrange > Insert > Advanced > XML" option with a flowchart layout.
The components map 1:1 to the Python modules listed above.
