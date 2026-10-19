"""
DevVideo Web package: FastAPI app, frontend interface, and Render keep-alive worker.
"""

from .app import app, health_check, job_manager, keep_alive_manager

__all__ = ["app", "health_check", "job_manager", "keep_alive_manager"]
