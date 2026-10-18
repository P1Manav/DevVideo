"""
CLI entry point for DevVideo generator.

Usage:
  python -m src.cli generate <github-url|local-dir> --out out/
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="devvideo",
        description="DevVideo: Generate developer walkthrough videos from GitHub repositories",
    )
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Generate a video from a repository")
    gen.add_argument("source", help="GitHub URL or local path to repository")
    gen.add_argument("--out", "-o", default="out", help="Output directory (default: out/)")
    gen.add_argument(
        "--llm",
        choices=["auto", "offline", "claude", "mock"],
        default="auto",
        help="LLM planner backend (default: auto)",
    )
    gen.add_argument(
        "--tts",
        choices=["auto", "edge", "espeak", "pyttsx3", "silent"],
        default="auto",
        help="Text-to-speech voice backend (default: auto)",
    )
    gen.add_argument("--voice", default=None, help="TTS voice name override (e.g. en-US-AriaNeural)")
    gen.add_argument(
        "--renderer",
        choices=["auto", "playwright", "pillow"],
        default="auto",
        help="Frame rendering engine (default: auto)",
    )
    gen.add_argument("--budget-seconds", type=float, default=55.0, help="Target video duration budget (default: 55)")
    gen.add_argument("--webhook", default=None, help="Webhook URL to POST manifest upon completion")
    gen.add_argument("--keep-frames", action="store_true", help="Preserve rendered PNG frames in output directory")

    parser.add_argument("--version", action="version", version="devvideo 0.2.0")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "generate":
        result = run_pipeline(
            source=args.source,
            output_dir=Path(args.out),
            llm_backend=args.llm,
            tts_backend=args.tts,
            voice=args.voice,
            renderer=args.renderer,
            budget_seconds=args.budget_seconds,
            webhook_url=args.webhook,
            keep_frames=args.keep_frames,
        )

        if result.exit_code == 0:
            print(f"\n[OK] Video published successfully: {result.video_path}")
            print(f"  Duration: {result.manifest.get('timings', {}).get('total', '?')}s")
            print(f"  All gates passed: {result.manifest.get('all_gates_passed', False)}")
        elif result.exit_code == 1:
            print(f"\n[REJECTED] Video generated but rejected by eval gates: {result.error}")
            print("  Check out/_rejected/ and eval_report.json for details.")
        else:
            print(f"\n[ERROR] Video generation pipeline failed: {result.error}")

        return result.exit_code

    return 0


if __name__ == "__main__":
    sys.exit(main())
