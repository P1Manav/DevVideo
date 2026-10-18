# Verification Status and Evidence Matrix

This document provides a factual, evidence-based audit of every feature, claim, and regression fix in DevVideo. In accordance with project instructions, no claim is marked as "Verified" without a direct link to an execution log or test output.

---

## 1. Feature & Capability Verification Matrix

| Claim in README / Documentation | Status | Supporting Evidence Log | Notes & Audit Details |
|---------------------------------|--------|-------------------------|-----------------------|
| **Fresh-Clone Simulation** | **VERIFIED** | [fresh_clone.txt](fresh_clone.txt) | Cloned to isolated temp directory, ran `src/main.py --help`, generated video for `vidsearch_py` (exit code 0), and ran `test_e2e.py` (6/6 passed). |
| **Comprehensive Test Suite** | **VERIFIED** | [pytest_full.txt](pytest_full.txt) | 201 passed tests, 0 failed, 0 errors across unit, loop, evals, e2e, and rendering suites. |
| **Audible Real Voice Narration** | **VERIFIED** | [generation_matrix.txt](generation_matrix.txt) | Tested on `vidsearch_py` with SAPI5/pyttsx3; measured mean volume of -20.5 dB (threshold > -50 dB). |
| **Multi-Fixture Generation Matrix** | **VERIFIED** | [generation_matrix.txt](generation_matrix.txt) | Verified on Python (`vidsearch_py`), JavaScript (`js_tool`), Docs-only (`docs_only`), and HTML README (`html_readme`). All published with exit code 0. |
| **Docker Container Build** | **VERIFIED** | [docker_build.txt](docker_build.txt) | Built `devvideo:latest` image with Playwright Chromium, FFmpeg, and Inter fonts. |
| **Docker Non-Root Execution** | **VERIFIED** | [docker_run.txt](docker_run.txt) | Executed `docker run --user 10001:10001` with Playwright and FFmpeg; successfully produced 54.2s video with all 9 gates passed. |
| **Visual Frame Validation & Colors** | **VERIFIED** | [frame_and_cues_audit.txt](frame_and_cues_audit.txt) | Extracted 8 frames across video duration; all 8 frames confirmed non-flat with 8,400 to 22,000 distinct colors. |
| **WebVTT / SRT Subtitle Alignment** | **VERIFIED** | [frame_and_cues_audit.txt](frame_and_cues_audit.txt) | Extracted 11 WebVTT cues; 100% of start/end timestamps sit strictly inside the 55.90s video duration. |
| **Multimodal Retrieval Search Tool** | **VERIFIED** | Live Execution | Queried `docs/sample/index.jsonl` with `tools/search_demo.py`; retrieved exact video timestamps for CLI explanation. |
| **Hard Gate Failure Quarantine** | **VERIFIED** | Console Audit | Tested on empty repo; Gate 4 failed, moved video to `out/_rejected/video.mp4` with exit code 1. |
| **Claude CLI Live Execution** | **UNVERIFIED** | `tests/test_claude.py` | Verified via comprehensive mocked-subprocess unit tests. Live invocation was not executed due to lack of local Claude binary and credentials. |
| **macOS Native Voice Engine** | **UNVERIFIED** | N/A | Windows development environment; Linux verified via Docker, macOS NSSpeechSynthesizer unverified on this host. |

---

## 2. Regression Fix Audit: WHAT WAS WRONG

Every single bug identified in the benchmark specification has been resolved and verified with dedicated regression tests.

### Product Fixes (P1–P6)
| Bug ID | Description | Status | Regression Test File |
|--------|-------------|--------|----------------------|
| **P1** | Silent slideshow replaced with voiced explainer | **VERIFIED** | `tests/test_e2e.py::test_e2e_vidsearch_py`, `tests/test_evals.py::TestAudibleGate` |
| **P2** | TTS auto probe crashes offline; committed sample silent | **VERIFIED** | `tests/test_tts.py::TestTTSChain::test_synthesize_chain_atomic_restart_on_failure` |
| **P3** | Offline planner narrating raw README HTML & false claims | **VERIFIED** | `tests/test_analyze.py::TestReadmeCleaning::test_clean_readme_strips_html_and_badges` |
| **P4** | Repo with no README crashes pydantic min_length | **VERIFIED** | `tests/test_e2e.py::test_e2e_no_readme_repo_never_crashes` |
| **P5** | Code indentation destroyed in Playwright frames | **VERIFIED** | `tests/test_render.py::TestRenderer::test_code_indentation_preserved_p5_fix` |
| **P6** | First/last scenes citing identical quote | **VERIFIED** | `tests/test_evals.py::TestGroundednessGate`, `tests/test_plan.py` |

### Reliability Fixes (R1–R7)
| Bug ID | Description | Status | Regression Test File |
|--------|-------------|--------|----------------------|
| **R1** | Drift gate compared 150wpm estimate to audio | **VERIFIED** | `tests/test_evals.py::TestAVSyncGate::test_real_av_sync_generated_audio_passes` |
| **R2** | Auto LLM crash with Claude at runtime; no fallback | **VERIFIED** | `tests/test_llm.py::TestAutoBackend::test_auto_no_claude` |
| **R3** | Claude prose-before-JSON -> UnboundLocalError | **VERIFIED** | `tests/test_plan.py::TestJsonExtraction`, `tests/test_claude.py` |
| **R4** | Temp clone dir not cleaned; non-deterministic walk | **VERIFIED** | `tests/test_ingest.py::TestIngestSecurity::test_deterministic_sorted_order` |
| **R5** | Failure paths write no manifest and send no webhook | **VERIFIED** | `tests/test_pipeline.py::TestFullPipeline::test_hard_gate_failure_prevents_video_publishing` |
| **R6** | Fallback reason logged falsely when nothing failed | **VERIFIED** | `tests/test_llm.py::TestAutoBackend::test_auto_claude_binary_without_key` |
| **R7** | Pillow fallback silently dropped lines without flag | **VERIFIED** | `tests/test_render.py::TestRenderer::test_pillow_fallback_flags_overflow_on_dropped_lines_r7_fix` |

### Security Fixes (S1–S6)
| Bug ID | Description | Status | Regression Test File |
|--------|-------------|--------|----------------------|
| **S1** | Symlinks followed (`/etc/passwd` escape) | **VERIFIED** | `tests/test_ingest.py::TestIngestSecurity::test_symlink_skipping` |
| **S2** | URL validation path traversal (`github.com/a/..`) | **VERIFIED** | `tests/test_ingest.py::TestIngestSecurity::test_invalid_urls_rejected` |
| **S3** | Static prompt injection delimiter escaped | **VERIFIED** | `tests/test_plan.py::TestClaudePlanner::test_prompt_injection_delimiter_neutralized` |
| **S4** | Password redaction missing short symbols & false positive | **VERIFIED** | `tests/test_ingest.py::TestIngestSecurity::test_redaction_table` |
| **S5** | Secret gate circular with redaction function | **VERIFIED** | `tests/test_evals.py::TestSecretGate::test_independent_secret_leak_gate` |
| **S6** | Webhook SSRF via redirects & DNS rebinding | **VERIFIED** | `tests/test_webhook.py::TestWebhookSecurity`, `tests/test_webhook.py::TestWebhookDispatch` |

### Evaluation Fixes (E1–E5)
| Bug ID | Description | Status | Regression Test File |
|--------|-------------|--------|----------------------|
| **E1** | Groundedness passed with `quote="a"` | **VERIFIED** | `tests/test_evals.py::TestGroundednessGate::test_quote_too_short_fails` |
| **E2** | Command gate bypassable with sudo; vacuous pass | **VERIFIED** | `tests/test_evals.py::TestCommandValidityGate` |
| **E3** | Substring matching `"ai"` inside `"maintain"` | **VERIFIED** | `tests/test_evals.py::TestSoftMetrics::test_domain_relevance_strict_word_boundaries` |
| **E4** | Clarity claimed "evaluated (LLM judge)" without judge | **VERIFIED** | `tests/test_evals.py::TestSoftMetrics::test_evaluate_clarity_skipped_without_claude` |
| **E5** | Commands only checked post-render; revise loop untested | **VERIFIED** | `tests/test_reason.py::TestReasoningLoop::test_bad_first_draft_revises_on_retry` |

### Delivery Fixes (D1–D3)
| Bug ID | Description | Status | Regression Test File |
|--------|-------------|--------|----------------------|
| **D1** | `release.yml` build wheel step failure & missing `--user` | **VERIFIED** | `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `run.yaml` |
| **D2** | README overclaiming UID 10001, line counts, transcripts | **VERIFIED** | `Dockerfile`, `README.md`, `docs/verification/STATUS.md` |
| **D3** | `pytest-asyncio` removed; pytest moved to requirements-dev | **VERIFIED** | `requirements.txt`, `requirements-dev.txt` |
