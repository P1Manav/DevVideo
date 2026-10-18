"""
Webhook dispatcher: securely dispatch manifests to external URLs.

Security features:
- HTTPS only (rejects http://, file://, ftp://, etc.)
- SSRF defense: DNS resolution check rejecting loopback, RFC 1918 private, link-local,
  reserved, multicast, and IPv4-mapped IPv6 addresses
- DNS pinning: resolves once and connects directly to the validated IP to prevent DNS rebinding
- Enforces SNI (server_hostname) and Host header matching the original hostname
- Redirects strictly prohibited (3xx = failure)
- Query string and userinfo redacted in logging
- HMAC-SHA256 signature when WEBHOOK_SECRET is configured (X-Signature-256 header)
- Ensures all paths in the payload manifest are relative POSIX paths (no absolute local paths leaked)
- Supports events: video.generated, video.rejected, video.failed
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import logging
import os
import socket
import ssl
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)


def is_forbidden_ip(ip_str: str) -> bool:
    """
    Check if an IP address is private, loopback, link-local, reserved,
    or an IPv4-mapped IPv6 address representing a forbidden address (SSRF defense).
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        # Check IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            return is_forbidden_ip(str(ip.ipv4_mapped))

        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return True


def sanitize_url_for_logging(url: str) -> str:
    """Strip query strings and userinfo from URLs to prevent leaking tokens in logs."""
    try:
        parsed = urllib.parse.urlparse(url)
        clean_netloc = parsed.hostname or ""
        if parsed.port:
            clean_netloc += f":{parsed.port}"
        return urllib.parse.urlunparse((parsed.scheme, clean_netloc, parsed.path, "", "", ""))
    except Exception:
        return "<invalid-url>"


def resolve_and_validate_webhook_url(url: str) -> tuple[str, str, int, str]:
    """
    Validate that URL uses HTTPS and does not resolve to private/loopback/link-local IPs.
    Returns (clean_url, validated_ip, port, hostname) or raises ValueError.
    """
    clean_url = url.strip()
    parsed = urllib.parse.urlparse(clean_url)
    if parsed.scheme.lower() != "https":
        raise ValueError(
            f"Insecure webhook scheme: {parsed.scheme!r}. Webhook URLs MUST use https://"
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid webhook URL: missing hostname in {url!r}")

    port = parsed.port or 443

    try:
        addr_info = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve webhook hostname {hostname!r}: {e}")

    if not addr_info:
        raise ValueError(f"Could not resolve webhook hostname {hostname!r}: no records found")

    validated_ip: str | None = None
    for entry in addr_info:
        ip_str = entry[4][0]
        if is_forbidden_ip(ip_str):
            raise ValueError(
                f"Webhook URL resolves to forbidden internal IP address {ip_str} (SSRF blocked)"
            )
        if validated_ip is None:
            validated_ip = ip_str

    return clean_url, validated_ip or "", port, hostname


def validate_webhook_url(url: str) -> str:
    """
    Validate webhook URL and return clean URL string.
    Maintains backward compatibility with test callers.
    """
    clean_url, _, _, _ = resolve_and_validate_webhook_url(url)
    return clean_url


def sanitize_payload_paths(obj: Any) -> Any:
    """
    Recursively sanitize manifest/payload to ensure no local absolute paths are leaked.
    Converts Windows and absolute paths to clean relative POSIX paths.
    """
    if isinstance(obj, dict):
        return {k: sanitize_payload_paths(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_payload_paths(item) for item in obj]
    elif isinstance(obj, str):
        # If it looks like a local absolute path (e.g. C:\... or /home/...)
        if (len(obj) > 2 and obj[1] == ":" and obj[2] in ("\\", "/")) or obj.startswith("/"):
            # Return only basename or relative filename
            name = os.path.basename(obj.replace("\\", "/"))
            return f"out/{name}" if name else obj
        return obj.replace("\\", "/")
    return obj


def send_webhook(
    url: str | None = None,
    payload: dict[str, Any] | None = None,
    secret: str | None = None,
    timeout: int = 10,
    event: str = "video.generated",
) -> bool:
    """
    Securely POST payload to webhook URL using DNS pinning and redirect rejection.
    Returns True on success, False on failure.
    """
    target_url = url or os.environ.get("WEBHOOK_URL")
    if not target_url:
        return False

    webhook_secret = secret or os.environ.get("WEBHOOK_SECRET")
    safe_url = sanitize_url_for_logging(target_url)

    try:
        clean_url, validated_ip, port, hostname = resolve_and_validate_webhook_url(target_url)
    except ValueError as e:
        logger.error(f"Webhook URL validation failed for {safe_url}: {e}")
        return False

    # Clean payload of any local absolute paths
    raw_payload = payload or {}
    clean_payload = sanitize_payload_paths(raw_payload)
    if "event" not in clean_payload:
        clean_payload["event"] = event

    body_bytes = json.dumps(clean_payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DevVideo-Webhook/2.0",
        "Host": hostname,
    }

    if webhook_secret:
        sig = hmac.new(webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        headers["X-Signature-256"] = f"sha256={sig}"

    # Connect directly to validated IP (DNS rebinding defense) with SNI set to hostname
    parsed = urllib.parse.urlparse(clean_url)
    request_path = parsed.path or "/"
    if parsed.query:
        request_path += f"?{parsed.query}"

    try:
        # Create standard SSL context
        ssl_ctx = ssl.create_default_context()

        # Connect directly to the validated IP with host set to validated_ip
        # and server_hostname set to hostname
        sock = socket.create_connection((validated_ip, port), timeout=timeout)
        tls_sock = ssl_ctx.wrap_socket(sock, server_hostname=hostname)

        conn = http.client.HTTPSConnection(hostname, port=port, timeout=timeout)
        conn.sock = tls_sock

        conn.request("POST", request_path, body=body_bytes, headers=headers)
        resp = conn.getresponse()

        # Security check: redirects are strictly prohibited
        if 300 <= resp.status < 400:
            logger.warning(f"Webhook received redirect status {resp.status} to {safe_url} - rejected")
            conn.close()
            return False

        if 200 <= resp.status < 300:
            logger.info(f"Webhook successfully delivered to {safe_url} (HTTP {resp.status})")
            conn.close()
            return True
        else:
            logger.warning(f"Webhook responded with non-2xx status: {resp.status}")
            conn.close()
            return False

    except Exception as e:
        logger.warning(f"Webhook POST failed to {safe_url}: {e}")
        return False
