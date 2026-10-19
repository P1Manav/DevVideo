"""
Ingest package: safe repository cloning, local loading, file collection, and secret redaction.
"""

from .clone import (
    clone_repo,
    get_git_commit_sha,
    ingest_github,
    ingest_local,
    safe_clone_github,
)
from .collector import (
    MAX_FILE_SIZE,
    MAX_FILES,
    MAX_TOTAL_SIZE,
    RepoContent,
    collect_files,
)
from .security import (
    neutralize_repo_text,
    redact_secrets,
    validate_github_url,
)

__all__ = [
    "validate_github_url",
    "redact_secrets",
    "neutralize_repo_text",
    "RepoContent",
    "collect_files",
    "clone_repo",
    "get_git_commit_sha",
    "safe_clone_github",
    "ingest_github",
    "ingest_local",
    "MAX_FILES",
    "MAX_FILE_SIZE",
    "MAX_TOTAL_SIZE",
]
