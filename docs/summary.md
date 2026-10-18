# DevVideo: Autonomous Developer Explainer Video Generator

## Executive Summary & Problem Context
Modern codebases are difficult for engineers and retrieval systems to digest rapidly. Static README files, fragmented documentation, and ad-hoc wikis often fail to explain how a repository is structured, how its core modules interact, and how to execute it. Previous video generation prototypes degraded into silent, ungrounded slideshows—narrating raw HTML tags, quoting phantom features, hallucinating commands, and publishing silent media with broken indentation and audio drift.

DevVideo rebuilds the generation pipeline from the ground up as a deterministic, verified explainer generator for AI video understanding and retrieval engines. It takes any GitHub repository or local directory as input and autonomously produces an audible, 50–58 second, 720p 30fps explainer video accompanied by synchronized multimodal retrieval assets (`transcript.vtt`, `chapters.json`, `index.jsonl`).

## Architecture & System Design
DevVideo implements a strict 7-stage linear pipeline reinforced by bounded verify-revise loops:

1. **Ingest & Security Perimeter**: Validates GitHub URLs against path-traversal attacks (`.` and `..`), executes shallow clones with git security hardening (`core.symlinks=false`, `protocol.file.allow=never`, empty hooks path), and caps repository scans (50 files, 500 KB total). Content undergoes multi-pattern secret redaction (JWT, PEM, cloud keys, high-entropy tokens), recording exact secret values for independent post-generation gate validation.
2. **Semantic Analysis (`RepoFacts`)**: Parses code structure using AST for Python and regex for JavaScript/TypeScript, extracting internal dependency graphs, top symbol definitions, line slices, CLI flags, and cleaned README sections. Domain relevance to AI video processing is evaluated via strict word-boundary token matching.
3. **Planners & Reasoning Loop (`reason.py`)**: A dual-planner architecture supports `OfflinePlanner` (deterministic, fact-grounded blueprints) and `ClaudePlanner` (optional LLM reasoning via standard input within a nonce-delimited untrusted data block). Before speech synthesis, plans are verified against lexical overlap, line ranges, and duration budgets, executing up to 2 automated repair cycles before graceful fallback to a minimal 3-scene degraded plan.
4. **Adaptive Voice Chain (`tts.py`)**: Probes speech synthesis engines at runtime in order (`edge` -> `espeak-ng` -> `pyttsx3` -> `silent`). To prevent mixed voices across scenes, any mid-run engine failure triggers an atomic restart from scene 1 using the next backend. Audio segments are normalized to 44.1 kHz mono PCM WAVs with 0.25s lead and 0.35s tail acoustic padding.
5. **Precision Rendering (`render.py`)**: Uses a single persistent Playwright Chromium browser (JavaScript disabled) to render SVG architecture graphs, verbatim Pygments-highlighted code slices, and terminal typing animations with Inter and JetBrains Mono typography. A pure-Pillow fallback measures bounding boxes and explicitly flags overflow.
6. **Demuxer Assembly (`assemble.py`)**: Muxes frame sequences and audio via ffmpeg concat-demuxer with repeated final frame entries, guaranteeing zero A/V drift.
7. **Companion Outputs & Search Demo**: Emits synchronized WebVTT/SRT subtitles, chapter markers, video thumbnails, and `index.jsonl` retrieval records queryable via `tools/search_demo.py` (a pure-Python TF-IDF retrieval tool).

## Why the Verification Loop & Hard Gates Matter
Modern LLMs and heuristic planners are inherently prone to subtle grounding errors, hallucinations, and formatting drift. DevVideo treats video generation as an engineering process governed by 13 runnable hard gates and 1 voice presence check defined in `src/evals/registry.py`:
- **duration**: Final MP4 duration <= 60.0s measured via ffprobe.
- **av_sync**: Scene drift <= 0.15s, container stream drift <= 0.30s.
- **audio_audible**: Audio loudness > -35.0 dB via ffmpeg `volumedetect`.
- **groundedness**: 100% of scenes/beats cite verified source spans with >= 60% token grounding.
- **code_verbatim**: On-screen code is an exact verbatim line range from cited source.
- **rendered_code_matches**: 100% preservation of code characters and indentation in rendered output.
- **command_validity**: Shell commands exist in repository code fences (N/A if 0 commands).
- **secret_leaks**: 0 credentials detected via independent multi-pattern regex scanner.
- **no_overflow**: 0 dropped lines or bounding box clipping across DOM and Pillow frames.
- **frames_valid**: 100% of sampled video frames contain non-flat visual content.
- **narration_quality**: 0 violations of style rules (no banned buzzwords, no dangling endings, verbs in every beat).
- **specificity**: 100% of beats name concrete repository-specific identifiers or symbols.
- **onscreen_text_integrity**: 0 dangling stopwords, 0 mid-word splits, and fully grounded bullet points.
- **motion**: Dynamic visual interest (>= 24 content changes, max idle gap <= 5.0s).
- **voice_present**: Verified speech engine present (non-blocking for headless environments).

If any hard gate fails, publication is refused and artifacts are quarantined to `out/_rejected/`.

## Tradeoffs & Decisions
1. **Fact-Conditional Templating vs Unconstrained LLM Generation**: The LLM selects focal points and narrative emphasis, but visuals (code excerpts, SVG graphs) are extracted directly by AST and syntax tools. This eliminates visual hallucination while preserving narrative clarity.
2. **Subprocess Isolation vs Native In-Process Threads**: Windows COM/SAPI5 threading models frequently freeze when invoked concurrently. Running `pyttsx3` in an isolated subprocess with explicit timeouts guarantees crash-free Windows execution.
3. **Honest Fit Scene**: Rather than fabricating artificial AI video capabilities for general-purpose repos, DevVideo reports real relevance and emphasizes the video retrieval assets generated.

## Next Steps
- Implement voice pitch and emotion inflection modulation across scene transitions.
- Expand AST dependency extraction to Go, Rust, and C++ repositories.
- Support live frame-level vector embedding export for Qdrant and Milvus vector databases.
