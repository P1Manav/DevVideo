# Architectural and Engineering Decisions

This log documents non-obvious design and engineering decisions made during the DevVideo rebuild.

- baseline_setup: Initialized verification log directory and captured baseline test run (108 tests passing against legacy codebase).
- ingest_security: Enforced strict GitHub URL regex rejecting '.' and '..' path traversals; configured git clone with core.symlinks=false, protocol.file.allow=never, and empty temp dir hooksPath to prevent Windows /dev/null failures.
- redaction_hardening: Added regexes for short symbol passwords, PEM, JWT, Slack, and cloud keys while exempting command lines and path/extension tokens from entropy checks; recorded raw secret values for independent eval verification.
- webhook_hardening: Implemented DNS pinning to prevent rebinding, blocked IPv4-mapped IPv6 SSRF attempts, rejected HTTP 3xx redirects, and sanitized all payload paths to relative POSIX format.
