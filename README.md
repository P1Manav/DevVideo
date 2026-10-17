# DevVideo: Developer Video Generator

Generates short (<60s) developer walkthrough videos from GitHub repositories.  
Takes a repo URL, reads docs and code, produces a narrated video grounded in the actual codebase.  
Built for the AI video understanding and retrieval domain.

---

## Quick Start

### Local (no API keys needed)

```bash
pip install -r requirements.txt
python -m src.cli generate tests/fixture_repo --out out/ --tts silent --no-playwright
```

### With Playwright rendering

```bash
pip install -r requirements.txt
playwright install chromium --with-deps
python -m src.cli generate tests/fixture_repo --out out/ --tts silent
```

### Docker (everything included)

```bash
docker build -t devvideo .
docker run -v $(pwd)/out:/app/out devvideo generate tests/fixture_repo --out out/ --tts silent
```

### From a GitHub URL

```bash
python -m src.cli generate https://github.com/owner/repo --out out/
```

---

## How It Works

```
GitHub URL ──► Ingest ──► Plan Script ──► Verify ──► TTS ──► Render ──► Assemble ──► Eval
                │              │            │ ▲                                        │
                │         (LLM adapter)     │ │ retry (max 2)                         │
                ▼              ▼            ▼ │                                        ▼
          Clone + collect   scenes.json   Pass/Fail                              video.mp4
          + redact secrets                                                    eval_report.json
                                                                              manifest.json
```

1. **Ingest**: Validates URL, shallow-clones with hooks disabled, collects README + docs + key files, applies size/file caps, redacts secrets.
2. **Plan Script**: LLM adapter generates `scenes.json` (3-6 scenes, 45-55s narration). Repo text is in a delimited DATA block treated as untrusted.
3. **Verify**: Deterministic checks — evidence file exists, quote appears in it, no secrets, duration in bounds. On failure, feeds errors back for retry (max 2).
4. **TTS**: Per-scene audio from narration text.
5. **Render**: Per-scene HTML card → PNG screenshot (Playwright with JS disabled, or ffmpeg fallback).
6. **Assemble**: scene duration = audio length + padding. ffmpeg stitches into MP4.
7. **Eval**: Hard gates + metrics → `eval_report.json`. If a gate fails, video is NOT published.

---

## Backends

| Component | Env Var | Options | Default |
|-----------|---------|---------|---------|
| LLM | `LLM_BACKEND` | `auto`, `mock`, `claude`, `gemini` | `auto` |
| TTS | `TTS_BACKEND` | `auto`, `silent`, `edge`, `espeak` | `auto` |

**Auto logic (LLM)**: Uses `claude` if the binary is on PATH and `CLAUDE_KEY` is set; otherwise `mock`.  
**Auto logic (TTS)**: Tries `edge-tts` → `espeak-ng` → `silent`.

---

## Evals & Guardrails

### Hard Gates (must pass)

| Gate | Threshold | Description |
|------|-----------|-------------|
| Duration | ≤ 60s | Final video length |
| Secret leaks | 0 | No secrets in narration or visuals |
| Groundedness | ≥ 50% | Scenes backed by real repo evidence |
| Audio/scene drift | ≤ 2s | Audio matches scene duration |

### Metrics (informational)

| Metric | Description |
|--------|-------------|
| Domain relevance | AI/video/retrieval keyword coverage |
| Clarity | LLM-judge rubric (skipped when no real LLM, never faked) |
| Scene count | Number of scenes in the video |

### Guardrails

| Phase | What |
|-------|------|
| Pre | URL validation, size caps, secret redaction before LLM sees anything |
| Mid | Schema validation, retry cap (max 2), evidence grounding check |
| Post | Final gate: duration, secrets, drift. Produces eval_report.json |

---

## Hooks

- **CLI**: `python -m src.cli generate <url-or-path> --out out/`
- **Manifest**: `out/manifest.json` (video path, script, eval report, timings, backends)
- **Webhook**: `--webhook <url>` POSTs the manifest on completion
- **GitHub Action**: `.github/workflows/ci.yml` regenerates video on release

---

## Tests

```bash
pytest tests/ -v
```

Tests use the committed fixture repo (`tests/fixture_repo/`), mock LLM, and silent TTS — no network needed.  
Integration tests require `ffmpeg` on PATH (skipped if missing).

---

## Project Structure

```
src/
├── __init__.py      # Package init
├── __main__.py      # python -m src entry
├── cli.py           # CLI argument parsing
├── main.py          # Entry point (run.yaml compat)
├── pipeline.py      # 7-step orchestrator
├── schema.py        # Pydantic models (Scene, ScriptPlan)
├── ingest.py        # URL validation, clone, collect, redact
├── llm.py           # LLM adapters (mock, claude, auto)
├── verify.py        # Deterministic script verification
├── tts.py           # TTS backends (silent, edge, espeak)
├── render.py        # HTML→PNG rendering (Playwright/fallback)
├── assemble.py      # ffmpeg video assembly
└── evals.py         # Eval gates and metrics
tests/
├── fixture_repo/    # Committed test fixture (no network needed)
├── test_ingest.py   # URL, secrets, file collection
├── test_schema.py   # Pydantic validation
├── test_llm.py      # Mock, mocked-claude subprocess, auto selection
├── test_verify.py   # Evidence, secrets, duration checks
├── test_tts.py      # WAV generation, duration estimation
├── test_evals.py    # All eval gates
└── test_pipeline.py # Full end-to-end integration
```

---

## Honest Limits

- **Claude path**: The Claude CLI backend is implemented and tested via mocked subprocess. It was not run live because the author does not have the Claude CLI installed locally. The mock tests cover command construction, error handling, timeout, and missing binary cases.
- **Edge TTS**: Requires internet access. Falls back to espeak-ng (local) or silent (generates WAV silence).
- **Playwright**: Requires Chromium installation. Falls back to ffmpeg solid-color frames.
- **Gemini backend**: Placeholder only, not implemented.

---

## Security

- Never executes code from cloned repos. Clone with hooks disabled (`core.hooksPath=/dev/null`).
- URL allowlist: only `https://github.com/<owner>/<repo>`.
- HTML-escapes all repo text before rendering. Playwright runs with JS disabled.
- Secrets via env vars only, never logged. Docker runs non-root.
- Prompt-injection defense: repo text in delimited UNTRUSTED DATA block.
