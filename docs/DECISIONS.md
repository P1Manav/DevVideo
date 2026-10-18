# Architectural and Engineering Decisions

This log documents non-obvious design and engineering decisions made during the DevVideo rebuild.

- baseline_setup: Initialized verification log directory and captured baseline test run (108 tests passing against legacy codebase).
- ingest_security: Enforced strict GitHub URL regex rejecting '.' and '..' path traversals; configured git clone with core.symlinks=false, protocol.file.allow=never, and empty temp dir hooksPath to prevent Windows /dev/null failures.
- redaction_hardening: Added regexes for short symbol passwords, PEM, JWT, Slack, and cloud keys while exempting command lines and path/extension tokens from entropy checks; recorded raw secret values for independent eval verification.
- webhook_hardening: Implemented DNS pinning to prevent rebinding, blocked IPv4-mapped IPv6 SSRF attempts, rejected HTTP 3xx redirects, and sanitized all payload paths to relative POSIX format.
- analyze_repofacts: Implemented AST-based Python semantic extraction (import graph, symbols, docstrings, argparse flags) with regex JS/TS support; built resilient README cleaner stripping HTML/badges while extracting code fences; enforced word-boundary domain relevance scoring to eliminate false positives.
- schema_v2_and_beats: Extended Schema with Beat model (say, caption, focus), visual asset metadata, phonetic speech normalizer, and strict buzzword validator.
- claude_adapter_stdin: Refactored Claude subprocess to pipe prompts via stdin avoiding Windows 32K argv limit; isolated typed errors for missing binary, non-zero exits, and empty output.
- reason_and_plan_loop: Built bounded verify-revise reasoning loop with multi-tier fallback (claude -> offline -> degraded 3-scene plan) to eliminate UnboundLocalError and ensure zero unhandled failures on any repo structure.
- tts_probe_and_chain: Implemented runtime probe synthesis in priority order (edge -> espeak -> pyttsx3 -> silent); added subprocess pyttsx3 to protect Windows SAPI5 from COM deadlocks; enforced atomic chain restart on mid-scene failure to guarantee no mixed voices.
- audio_padding_and_timing: Added ffmpeg 0.25s lead and 0.35s tail padding to 44.1kHz mono PCM WAVs; synchronized beat start/end timings to spoken duration; added WPM calibration from first synthesized sentence.
- renderer_v2_architecture: Implemented HTML/SVG frame generator with single persistent Playwright Chromium browser (JS disabled); vendored Inter and JetBrains Mono OFL fonts; added chapter ribbon, glassmorphic caption card, and progress rail.
- indentation_and_pygments_p5: Integrated Pygments line-by-line syntax highlighting to preserve verbatim indentation, fixing P5 template whitespace distortion.
- pillow_overflow_detection_r7: Hardened Pillow fallback with strict text bounding metrics and explicit overflow flagging whenever lines exceed card capacity or are dropped past 15.
