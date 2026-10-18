"""
Unit tests for webhook dispatcher.

Tests:
- HTTPS scheme enforcement
- SSRF defense (loopback, RFC 1918 private, link-local metadata addresses, IPv4-mapped IPv6)
- URL sanitization / query token stripping in logging
- HMAC-SHA256 signature generation
- Redirect blocking (3xx = failure)
- DNS pinning and secure dispatch
- Path sanitization in payload (relative POSIX paths only)
- Environment variable fallback
"""

import hashlib
import hmac
import json
import os
import socket
from unittest.mock import patch, MagicMock

import pytest

from src.webhook import (
    is_forbidden_ip,
    sanitize_url_for_logging,
    validate_webhook_url,
    resolve_and_validate_webhook_url,
    sanitize_payload_paths,
    send_webhook,
)


class TestWebhookSecurity:
    def test_https_enforcement(self):
        """Rejects non-HTTPS schemes."""
        with pytest.raises(ValueError, match="MUST use https://"):
            validate_webhook_url("http://example.com/webhook")

        with pytest.raises(ValueError, match="MUST use https://"):
            validate_webhook_url("file:///etc/passwd")

        with pytest.raises(ValueError, match="MUST use https://"):
            validate_webhook_url("ftp://example.com/resource")

    @pytest.mark.parametrize("forbidden_ip", [
        "127.0.0.1",
        "127.0.1.1",
        "::1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # AWS/GCP instance metadata
        "fe80::1",
        "::ffff:127.0.0.1",  # IPv4-mapped IPv6 loopback
        "::ffff:10.0.0.1",   # IPv4-mapped IPv6 private
        "::ffff:169.254.169.254",
    ])
    def test_forbidden_ips(self, forbidden_ip):
        """is_forbidden_ip identifies loopback, private, link-local, and IPv4-mapped IPs."""
        assert is_forbidden_ip(forbidden_ip) is True

    @patch("socket.getaddrinfo")
    def test_ssrf_blocks_private_ip(self, mock_dns):
        """DNS resolving to private IP triggers SSRF block."""
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))
        ]
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_webhook_url("https://internal.corp/webhook")

    @patch("socket.getaddrinfo")
    def test_ssrf_blocks_loopback_ip(self, mock_dns):
        """DNS resolving to 127.0.0.1 triggers SSRF block."""
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ]
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_webhook_url("https://localhost/webhook")

    @patch("socket.getaddrinfo")
    def test_ssrf_blocks_cloud_metadata_ip(self, mock_dns):
        """DNS resolving to 169.254.169.254 triggers SSRF block."""
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))
        ]
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_webhook_url("https://metadata.google.internal/webhook")

    @patch("socket.getaddrinfo")
    def test_ssrf_blocks_ipv4_mapped_ipv6(self, mock_dns):
        """Regression test for S6: DNS resolving to ::ffff:127.0.0.1 triggers SSRF block."""
        mock_dns.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 443, 0, 0))
        ]
        with pytest.raises(ValueError, match="SSRF blocked"):
            validate_webhook_url("https://evil.internal/webhook")

    @patch("socket.getaddrinfo")
    def test_public_ip_passes_validation(self, mock_dns):
        """Public IP passes validation."""
        mock_dns.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        clean_url = validate_webhook_url("https://example.com/webhook")
        assert clean_url == "https://example.com/webhook"


class TestUrlLoggingSanitization:
    def test_query_string_stripped(self):
        """Sensitive tokens in query string are stripped for safe logging."""
        raw_url = "https://hooks.slack.com/services/T00/B00/X00?token=secret_token_12345&auth=true"
        safe = sanitize_url_for_logging(raw_url)
        assert "secret_token_12345" not in safe
        assert safe == "https://hooks.slack.com/services/T00/B00/X00"

    def test_userinfo_stripped(self):
        """User credentials in netloc are stripped."""
        raw_url = "https://admin:password123@api.example.com/webhook"
        safe = sanitize_url_for_logging(raw_url)
        assert "password123" not in safe
        assert safe == "https://api.example.com/webhook"


class TestPayloadSanitization:
    def test_local_absolute_paths_converted_to_relative(self):
        """Regression test for S6: local absolute paths must not leak in manifest payload."""
        payload = {
            "video": "C:\\Users\\User\\project\\out\\video.mp4",
            "eval_report": "/home/user/project/out/eval_report.json",
            "script": "out/scenes.json",
            "nested": {
                "file": "D:\\data\\chapter.json"
            }
        }
        clean = sanitize_payload_paths(payload)
        assert clean["video"] == "out/video.mp4"
        assert clean["eval_report"] == "out/eval_report.json"
        assert clean["script"] == "out/scenes.json"
        assert clean["nested"]["file"] == "out/chapter.json"


class TestWebhookDispatch:
    @patch("src.webhook.resolve_and_validate_webhook_url")
    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    @patch("http.client.HTTPSConnection")
    def test_send_webhook_success_and_payload(self, mock_conn_cls, mock_ssl, mock_sock, mock_val):
        """Successfully dispatches JSON payload with proper headers via pinned IP."""
        mock_val.return_value = ("https://example.com/webhook", "93.184.216.34", 443, "example.com")
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_conn.getresponse.return_value = mock_resp

        payload = {"repo": "test/repo", "video": "out/video.mp4"}
        ok = send_webhook("https://example.com/webhook", payload=payload)
        assert ok is True

        assert mock_conn.request.called
        method, path = mock_conn.request.call_args[0][:2]
        headers = mock_conn.request.call_args[1].get("headers", {})
        body = json.loads(mock_conn.request.call_args[1].get("body", b"").decode("utf-8"))

        assert method == "POST"
        assert path == "/webhook"
        assert headers.get("Content-Type") == "application/json"
        assert headers.get("Host") == "example.com"
        assert body["repo"] == "test/repo"
        assert body["event"] == "video.generated"

    @patch("src.webhook.resolve_and_validate_webhook_url")
    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    @patch("http.client.HTTPSConnection")
    def test_hmac_signature_header(self, mock_conn_cls, mock_ssl, mock_sock, mock_val):
        """Generates X-Signature-256 header when secret is provided."""
        mock_val.return_value = ("https://example.com/webhook", "93.184.216.34", 443, "example.com")
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_conn.getresponse.return_value = mock_resp

        secret = "super-secret-key"
        payload = {"event": "video.rejected"}
        ok = send_webhook("https://example.com/webhook", payload=payload, secret=secret)
        assert ok is True

        headers = mock_conn.request.call_args[1].get("headers", {})
        body_bytes = mock_conn.request.call_args[1].get("body", b"")
        expected_sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        assert headers.get("X-Signature-256") == f"sha256={expected_sig}"

    @patch("src.webhook.resolve_and_validate_webhook_url")
    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    @patch("http.client.HTTPSConnection")
    def test_redirect_refused(self, mock_conn_cls, mock_ssl, mock_sock, mock_val):
        """Regression test for S6: 3xx redirects are strictly rejected."""
        mock_val.return_value = ("https://example.com/webhook", "93.184.216.34", 443, "example.com")
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        mock_resp = MagicMock()
        mock_resp.status = 302
        mock_conn.getresponse.return_value = mock_resp

        ok = send_webhook("https://example.com/webhook", payload={})
        assert ok is False

    @patch.dict(os.environ, {"WEBHOOK_URL": "https://example.com/env_webhook"})
    @patch("src.webhook.resolve_and_validate_webhook_url")
    @patch("socket.create_connection")
    @patch("ssl.create_default_context")
    @patch("http.client.HTTPSConnection")
    def test_env_var_fallback(self, mock_conn_cls, mock_ssl, mock_sock, mock_val):
        """Uses WEBHOOK_URL env var when url argument is omitted."""
        mock_val.return_value = ("https://example.com/env_webhook", "93.184.216.34", 443, "example.com")
        mock_conn = MagicMock()
        mock_conn_cls.return_value = mock_conn
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_conn.getresponse.return_value = mock_resp

        ok = send_webhook(url=None, payload={"status": "done"})
        assert ok is True

    def test_insecure_webhook_fails_cleanly(self):
        """Insecure or invalid webhook returns False without crashing."""
        ok = send_webhook("http://insecure.local/webhook", payload={})
        assert ok is False
