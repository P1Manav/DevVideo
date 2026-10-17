# DevVideo: Developer Video Generator — Design Summary

## What It Does

DevVideo takes a GitHub repository URL and produces a narrated developer walkthrough video (<60 seconds) grounded in the repo's actual documentation and code. The output is positioned for the AI video understanding and retrieval domain — every claim in the video traces back to a real file in the repo, making the content indexable and searchable by retrieval engines.

## Architecture

The system is a linear pipeline with a verify-and-revise loop:

```
┌──────────┐    ┌─────────────┐    ┌────────────┐    ┌─────┐    ┌────────┐    ┌──────────┐    ┌──────┐
│  Ingest  │───►│ Plan Script │───►│   Verify   │───►│ TTS │───►│ Render │───►│ Assemble │───►│ Eval │
└──────────┘    └─────────────┘    └────────────┘    └─────┘    └────────┘    └──────────┘    └──────┘
     │                │                 │ ▲                                                       │
  Clone repo     LLM adapter      Deterministic                                           eval_report.json
  + redact        scenes.json     checks + retry                                          manifest.json
  secrets                          (max 2)                                                video.mp4
```

### Key Design Decisions

1. **Protocol-based backends**: LLM, TTS, and Renderer are swappable via Python Protocols. No heavyweight dependency injection — just small classes behind a factory function. This makes testing trivial (mock everything) and extension easy (add a new backend in ~30 lines).

2. **Verify-revise loop**: The script goes through deterministic checks (evidence grounding, secret detection, duration bounds) before any expensive TTS/rendering. Failures are fed back as structured error messages, and the LLM gets max 2 retries. This is the "reasoning layer" — it's not just one LLM call, it's LLM → verify → feedback → retry.

3. **Security by default**: Repo text is HTML-escaped before rendering, Playwright runs with JS disabled, cloning disables hooks, the URL allowlist prevents SSRF, and secrets are redacted before anything leaves the ingest module. The Docker container runs as non-root.

4. **Eval gates as runtime checks**: The eval module isn't just for CI — it runs at the end of every pipeline execution. If a hard gate fails, the video is NOT published and the report explains why. This means the system fails safely rather than producing bad output.

## Eval Framework

### Hard Gates
| Gate | Threshold | Rationale |
|------|-----------|-----------|
| Duration | ≤ 60s | Task requirement |
| Secret leaks | 0 | Security: never leak keys in video |
| Groundedness | ≥ 50% | Every claim should trace to repo |
| Audio/scene drift | ≤ 2s | Video must feel synchronized |

### Metrics
- **Domain relevance**: Keyword-based score for AI/video/retrieval terms (0–1)
- **Clarity**: LLM-judge rubric, only when a real LLM is available. Skipped otherwise (marked "skipped", never faked)

### Guardrails
- **Pre**: URL validation, file size caps (100KB/file, 500KB total, 50 files max), secret regex + entropy redaction
- **Mid**: Pydantic schema validation, evidence grounding, retry cap
- **Post**: All hard gates, produces eval_report.json with full breakdown

## Honest Limits

- **Claude CLI**: Implemented with ~40 lines in one function, tested via mocked subprocess. Not run live — the author does not have the Claude CLI. Tests cover command construction (`claude -p`), non-zero exit, timeout, and missing binary.
- **Edge TTS**: Requires internet. Gracefully falls back to espeak-ng → silent.
- **No HTTP server**: The task calls for a CLI tool. An HTTP server is not included because the core pipeline is the priority.
- **Mock LLM scripts are canned**: They produce plausible but generic output. A real LLM would produce repo-specific narration.

## Running It

```bash
# From a fresh clone (no API keys needed):
pip install -r requirements.txt
pytest tests/ -v
python -m src.cli generate tests/fixture_repo --out out/ --tts silent --no-playwright

# With Docker:
docker build -t devvideo .
docker run -v $(pwd)/out:/app/out devvideo generate tests/fixture_repo --out out/ --tts silent
```

## System Design for Extensibility

- **Add a new LLM backend**: Implement `complete(prompt: str) -> str`, register in `get_llm_backend()`.
- **Add a new TTS backend**: Implement `synthesize(text: str, output_path: Path) -> None`, register in `get_tts_backend()`.
- **Webhook integration**: `--webhook <url>` POSTs manifest.json on completion.
- **CI/CD**: GitHub Action runs tests on push, regenerates video on release.
- **Manifest**: `manifest.json` records everything — backends used, fallback reasons, timings, revision history — for debugging and audit.
