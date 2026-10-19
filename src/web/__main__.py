"""
CLI entry point for running the web server: python -m src.web
"""

from __future__ import annotations

import os
import uvicorn

from .app import app


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "10000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
