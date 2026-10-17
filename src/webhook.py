"""
Webhook dispatcher: securely dispatch manifests to external URLs.

Security features:
- HTTPS only (rejects http://, file://, etc.)
- SSRF defense: DNS resolution check rejecting loopback, RFC 1918 private, link-local IPs
- Query string redaction in logs to prevent token leaks
- HMAC-SHA256 signature when WEBHOOK_SECRET is configured (X-Signature-256 header)
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def is_forbidden_ip(ip_str: str) -> bool:
    """
    Check if an IP address is private, loopback, link-local, or reserved (SSRF defense).
    """
    try:
        ip = ipaddress.ip_address(ip_str)
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
    """Strip query strings and userinfo from URLs to prevent leaking tokens."""
    try:
        parsed = urllib.parse.urlparse(url)
        clean_netloc = parsed.hostname or ""
        if parsed.port:
            clean_netloc += f":{parsed.port}"
        return urllib.parse.urlunparse((parsed.scheme, clean_netloc, parsed.path, "", "", ""))
    except Exception:
        return "<invalid-url>"


def validate_webhook_url(url: str) -> str:
    """
    Validate that URL uses HTTPS and does not resolve to private/loopback/link-local IPs.
    Returns cleaned URL or raises ValueError.
    """
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme.lower() != "https":
        raise ValueError(
            f"Insecure webhook scheme: {parsed.scheme!r}. Webhook URLs MUST use https://"
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Invalid webhook URL: missing hostname in {url!r}")

    try:
        addr_info = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve webhook hostname {hostname!r}: {e}")

    for entry in addr_info:
        ip_str = entry[4][0]
        if is_forbidden_ip(ip_str):
            raise ValueError(
                f"Webhook URL resolves to forbidden internal IP address {ip_str} (SSRF blocked)"
            )

    return url.strip()


def send_webhook(
    url: str | None = None,
    payload: dict[str, Any] | None = None,
    secret: str | None = None,
    timeout: int = 10,
) -> bool:
    """
    Securely POST payload to webhook URL.
    Returns True on success, False on failure.
    """
    target_url = url or os.environ.get("WEBHOOK_URL")
    if not target_url:
        return False

    payload_data = payload or {}
    webhook_secret = secret or os.environ.get("WEBHOOK_SECRET")

    safe_url = sanitize_url_for_logging(target_url)

    try:
        validated_url = validate_webhook_url(target_url)
    except ValueError as e:
        logger.error(f"Webhook URL validation failed for {safe_url}: {e}")
        return False

    body_bytes = json.dumps(payload_data).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "DevVideo-Webhook/1.0",
    }

    if webhook_secret:
        sig = hmac.new(webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        headers["X-Signature-256"] = f"sha256={sig}"

    try:
        req = urllib.request.Request(
            validated_url,
            data=body_bytes,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            logger.info(f"Webhook successfully delivered to {safe_url} (HTTP {resp.status})")
            return True
    except Exception as e:
        logger.warning(f"Webhook POST failed to {safe_url}: {e}")
        return False
