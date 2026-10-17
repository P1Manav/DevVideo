# DevVideo: Developer Walkthrough Video Generator

## Executive Summary & System Design

---

### 1. Problem Statement & Domain Grounding

Developer onboarding often suffers from dense, outdated documentation. Text-based READMEs lack pacing, visual hierarchy, and dynamic demonstration. **DevVideo** automates the end-to-end generation of concise (<60 seconds), readable developer walkthrough videos directly from GitHub repository source code and documentation.

To deliver immediate utility for **AI Video Understanding and Retrieval Engines**, DevVideo enforces **verbatim evidence grounding**:
- Every statement spoken or shown on screen is linked directly to an exact line and quote in the repository.
- Video scenes follow a structured schema (`intro`, `installation`, `usage`, `architecture`, `retrieval integration`).
- Generated videos produce semantic transcriptions and visual badges that multimodal retrieval pipelines (e.g., neural video search, TwelveLabs, CLIP-based embeddings) can index directly by timestamp and code entity.

---

### 2. Architecture & Key Technical Decisions

DevVideo is structured as an 8-stage linear pipeline orchestrated by a lightweight, stateful coordinator:

```
Ingest ──► Plan ──► Verify/Revise Loop ──► TTS + Render ──► Assemble ──► Eval Gates ──► Publish
```

#### Key Architecture Decisions:
1. **Separation of Concerns (Modular Protocol Backends)**:
   - Each phase is encapsulated behind a minimal Python Protocol (`LLMBackend`, `TTSBackend`, `Renderer`).
   - Every module is kept under 180 lines, making unit testing straightforward and eliminating complex dependency injection frameworks.
2. **Deterministic Verify-and-Revise Loop (Reasoning Layer)**:
   - Rather than trusting raw model outputs, scripts undergo strict deterministic verification *before* expensive rendering or audio synthesis.
   - If evidence quotes or schema checks fail, specific error messages are fed back into the planner (max 2 retries).
3. **Playwright Chromium as Default Renderer with Structural Pillow Fallback**:
   - Modern developer tools demand crisp syntax highlighting, contrast, and layout formatting. Playwright renders semantic HTML/CSS cards to 1280x720 PNGs.
   - If Chromium cannot be launched, an automated fallback using Pillow generates non-flat, structured cards with badges, card containers, and narration previews, preventing opaque solid-color failures.
   - Dynamic font step-down and visible truncation markers (`... [truncated for display]`) prevent text box overflow.
4. **Deterministic Offline Extractive Planner (Zero-Key Default)**:
   - To guarantee that a fresh clone runs out-of-the-box without requiring API keys or third-party cloud accounts, an offline extractive planner parses repository files and generates fully grounded scripts with real quotes.

---

### 3. Security Posture & Defense in Depth

DevVideo treats all ingested repository content as **untrusted user data**:

- **No Remote Code Execution**: Clones are performed with `core.hooksPath=/dev/null`, shallow depth (`--depth 1`), and strictly as passive text extraction. No repository scripts or tests are ever executed.
- **SSRF Defense**:
  - Ingestion URL allowlist strictly enforces `https://github.com/<owner>/<repo>`.
  - Webhook dispatch resolves DNS hostnames and verifies that destination IPs are neither loopback (`127.0.0.0/8`, `::1`), RFC 1918 private (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), nor cloud link-local metadata addresses (`169.254.169.254`).
- **XSS & Injection Protection**:
  - All rendered content is HTML-escaped.
  - Playwright browser context runs with `java_script_enabled=False`, preventing script injection.
  - LLM prompts isolate repository files within a delimited `=== UNTRUSTED DATA BLOCK ===`.
- **Secret Redaction**:
  - Shannon entropy scanning (>4.0 threshold) and regex patterns (`sk-...`, `ghp_...`, `AKIA...`, `Bearer...`) redact tokens to `[REDACTED]` before content leaves the ingestion layer.
- **Non-Root Container Hardening**:
  - Docker container runs under dedicated unprivileged user `devvideo` (UID 10001).
  - Playwright browser binaries are installed globally in `/ms-playwright` with read/execute permissions.

---

### 4. Evaluation Framework & Fail-Safe Publishing

Evaluation runs at runtime as a mandatory stage of every pipeline execution. Results are saved to `eval_report.json` and `manifest.json`.

#### Hard Gates (Must Pass 100% or Video is Unlinked):
| Gate | Threshold | Rationale |
|------|-----------|-----------|
| **Duration** | `≤ 60.0s` | Strict task constraint for high-retention developer media. |
| **Secret Leaks** | `0` | Inspects narration, visual text, and the raw prompt fed to the LLM. |
| **Groundedness** | `100%` | Every scene must cite an existing file and verbatim substring quote. |
| **Command Validity** | `100%` | 100% of executable on-screen commands must appear in repository files. |
| **Text Overflow** | `0 scenes` | Computed via element bounding-box analysis; no text clips frame edges. |
| **Drift** | `≤ 0.5s` | Audio duration and visual duration must stay synchronized. |

**Fail-Safe Publishing Guarantee**: If any hard gate fails, `out/video.mp4` is immediately unlinked and removed. Only the diagnostic `eval_report.json` remains.

#### Informational Metrics:
- **Domain Relevance**: Measures keyword density for AI video understanding and retrieval pipelines (soft warning if < 0.5).
- **Clarity**: Evaluated via LLM judge when a real LLM is active; explicitly recorded as `"clarity: skipped (no LLM)"` when running offline or with mocks.

---

### 5. Verification Matrix: Live vs Mocked

| Component | Status | Verification Method |
|-----------|--------|---------------------|
| **Core Pipeline** | **Live** | Ingests real local and cloned repos, parses schema, measures audio, renders frames, stitches MP4. |
| **Docker Container** | **Live** | Built and executed live with `docker run --user $(id -u):$(id -g)` on Docker Desktop (Engine 29.8). |
| **Playwright Renderer** | **Live** | Renders 1280x720 Chromium snapshots with >100 distinct colors and layout verification. |
| **Pillow Fallback** | **Live** | Tested without browser; produces multi-colored structured cards with visible truncation. |
| **Offline Planner** | **Live** | Extracts real lines from two distinct repos (`fixture_repo` vs `fixture_repo_2`); generates distinct, valid scripts. |
| **Eval Hard Gates** | **Live** | 24 unit tests covering pass and fail paths for each gate; verified live in integration tests. |
| **Claude CLI Adapter** | **Mocked** | Subprocess invocation (`claude -p`), timeout handling, error exits, and missing binary tested via mocks. |
| **Webhook SSRF/HMAC**| **Mocked** | DNS resolver, forbidden IP ranges, query token stripping, and HMAC-SHA256 headers tested via mocks. |

---

### 6. Roadmap: 2-Week Extension Plan

1. **Dynamic Video Capture (Code Walkthrough Animation)**:
   - Replace static code card snapshots with animated line-by-line typing and terminal playback (using `asciinema` or Playwright canvas recordings).
2. **Neural Voice & Multi-Speaker Dubbing**:
   - Integrate open-source local neural speech synthesis (e.g., Piper TTS / Coqui XTTS v2) to produce natural voice modulation without internet dependencies.
3. **Retrieval-Augmented Scene Chunking**:
   - For repositories exceeding 500KB, use AST-based symbol chunking (tree-sitter) and BM25/dense vector indexing to select the most relevant source files.
4. **Interactive Video Chapters & Web Player**:
   - Export WebVTT chapter tracks and interactive JSON cue points aligned with `eval_report.json` to allow developers to jump directly to specific functions.
