"""
Main entry point shim (for run.yaml compatibility).
Delegates to src.cli.main().
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
