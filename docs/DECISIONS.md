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
