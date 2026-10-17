"""
Unit tests for the ingest module.

Tests:
- URL validation (valid and invalid GitHub URLs)
- Secret redaction (API keys, tokens, high-entropy strings)
- File collection (priority files, caps, filtering)
"""

import pytest
from pathlib import Path

from src.ingest import (
    validate_github_url,
    redact_secrets,
    collect_files,
    ingest_local,
)

FIXTURE_REPO = Path(__file__).parent / "fixture_repo"


# --- URL validation ---

class TestURLValidation:
    def test_valid_github_url(self):
        owner, repo = validate_github_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_valid_github_url_with_git_suffix(self):
        owner, repo = validate_github_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"

    def test_valid_github_url_complex_names(self):
        owner, repo = validate_github_url("https://github.com/my-org/my_repo-v2")
        assert owner == "my-org"
        assert repo == "my_repo-v2"

    def test_invalid_url_not_github(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            validate_github_url("https://gitlab.com/owner/repo")

    def test_invalid_url_http(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            validate_github_url("http://github.com/owner/repo")

    def test_invalid_url_ssh(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            validate_github_url("git@github.com:owner/repo.git")

    def test_invalid_url_no_repo(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            validate_github_url("https://github.com/owner")

    def test_invalid_url_empty(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            validate_github_url("")

    def test_invalid_url_local_path(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            validate_github_url("/tmp/some/repo")

    def test_invalid_url_ssrf(self):
        with pytest.raises(ValueError, match="Invalid GitHub URL"):
            validate_github_url("https://github.com/../../../etc/passwd")


# --- Secret redaction ---

class TestSecretRedaction:
    def test_api_key_pattern(self):
        text = 'api_key = "sk-abc123def456ghi789jkl012mno345"'
        result = redact_secrets(text)
        assert "sk-abc123" not in result
        assert "[REDACTED]" in result

    def test_openai_key(self):
        text = "OPENAI_KEY=sk-abcdefghijklmnopqrstuvwxyz1234567890"
        result = redact_secrets(text)
        assert "sk-abcdef" not in result

    def test_github_pat(self):
        text = "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmn"
        result = redact_secrets(text)
        assert "ghp_" not in result

    def test_aws_key(self):
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        result = redact_secrets(text)
        assert "AKIAIOSF" not in result

    def test_normal_text_unchanged(self):
        text = "This is a normal README with no secrets."
        result = redact_secrets(text)
        assert result == text

    def test_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abcdef"
        result = redact_secrets(text)
        assert "eyJhbGci" not in result


# --- File collection ---

class TestFileCollection:
    def test_collects_readme(self):
        files = collect_files(FIXTURE_REPO)
        assert "README.md" in files

    def test_collects_docs(self):
        files = collect_files(FIXTURE_REPO)
        assert "docs/usage.md" in files

    def test_collects_python_files(self):
        files = collect_files(FIXTURE_REPO)
        assert "sample.py" in files

    def test_file_content_is_string(self):
        files = collect_files(FIXTURE_REPO)
        for content in files.values():
            assert isinstance(content, str)


# --- Local ingest ---

class TestIngestLocal:
    def test_ingest_fixture_repo(self):
        repo = ingest_local(str(FIXTURE_REPO))
        assert repo.repo_name == "fixture_repo"
        assert repo.owner == "local"
        assert len(repo.files) > 0
        assert "README.md" in repo.files

    def test_ingest_nonexistent_dir(self):
        with pytest.raises(ValueError, match="Not a directory"):
            ingest_local("/nonexistent/path")
