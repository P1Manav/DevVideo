"""
CLI entry point for the DevVideo generator.

Usage:
  python -m src.cli generate <github-url-or-local-path> --out out/
  python -m src.cli generate https://github.com/owner/repo --out out/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="devvideo",
        description="Generate developer walkthrough videos from GitHub repos",
    )
    sub = parser.add_subparsers(dest="command")

    # generate command
    gen = sub.add_parser("generate", help="Generate a video from a repo")
    gen.add_argument("source", help="GitHub URL or local path to repository")
    gen.add_argument("--out", "-o", default="out", help="Output directory (default: out/)")
    gen.add_argument("--llm", choices=["auto", "offline", "mock", "claude"], default="auto", help="LLM backend (default: auto)")
    gen.add_argument("--tts", choices=["auto", "silent", "edge", "espeak"], help="TTS backend")
    gen.add_argument("--no-playwright", action="store_true", help="Skip Playwright, use fallback rendering")
    gen.add_argument("--webhook", help="URL to POST manifest on completion")

    # version
    parser.add_argument("--version", action="version", version="devvideo 0.1.0")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Setup logging
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
            use_playwright=not args.no_playwright,
        )

        if result.success:
            print(f"\n[OK] Video generated: {result.video_path}")
            print(f"  Duration: {result.manifest.get('video_duration_seconds', '?')}s")
            print(f"  Eval: all gates passed")
        else:
            print(f"\n[FAIL] Pipeline {'completed with warnings' if result.video_path else 'failed'}")
            if result.error:
                print(f"  Error: {result.error}")

        # Webhook
        webhook_target = args.webhook or os.environ.get("WEBHOOK_URL")
        if webhook_target and result.manifest:
            from .webhook import send_webhook
            send_webhook(url=webhook_target, payload=result.manifest)

        return 0 if result.success else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
