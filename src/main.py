"""
Main entry point (for run.yaml compatibility).
Delegates to the CLI module.

Usage: python -m src.cli generate <url-or-path> --out out/
   or: python src/main.py --help  (adds parent dir to sys.path)
"""

import sys
import os

# When run as `python src/main.py`, the parent dir isn't on sys.path
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src.cli import main
    sys.exit(main())
