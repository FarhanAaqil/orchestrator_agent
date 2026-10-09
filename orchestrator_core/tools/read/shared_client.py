"""
orchestrator_core/tools/read/shared_client.py

Shared, hardened HTTP client for all read-only external tool operations (Section 5.5).
Guarantees:
  1. GET and HEAD methods ONLY. POST, PUT, DELETE, etc. are rejected with SSRFViolationError.
  2. SSRF Guard: Blocks loopback, private IPv4/IPv6, link-local (cloud metadata 169.254.169.254),
     multicast, and non-HTTP schemes.
  3. Domain allowlists enforced per tool spec.
  4. Max payload size capped at 1 MB by default.
  5. Timeout bounds (default 10s).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

import requests

from orchestrator_core.exceptions import SSRFViolationError

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 1024 * 1024  # 1 MB
DEFAULT_TIMEOUT_S = 10.0

# Denylisted host patterns
_DENYLISTED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "instance-data",
}


def _validate_url_ssrf(url: str, allowed_domains: tuple[str, ...] = ()) -> None:
    """Validate that the given URL does not target loopback, private IPs, or cloud metadata."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme not in ("http", "https"):
        raise SSRFViolationError(f"Scheme '{scheme}' is not permitted. Only HTTP/HTTPS allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFViolationError(f"URL '{url}' does not contain a valid hostname.")

    hostname_clean = hostname.lower().strip(".")
    if hostname_clean in _DENYLISTED_HOSTS or hostname_clean.endswith(".local") or hostname_clean.endswith(".internal"):
        raise SSRFViolationError(f"Access to host '{hostname}' is blocked by SSRF policy.")

    # Domain allowlist check if specified
    if allowed_domains:
        norm_host = hostname_clean.removeprefix("www.")
        normalized_allowed = {d.lower().strip(".").removeprefix("www.") for d in allowed_domains}
        if norm_host not in normalized_allowed:
            raise SSRFViolationError(
                f"Host '{hostname}' is not on the allowed domain list: {sorted(allowed_domains)}"
            )

    # DNS Resolution and IP validation
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise SSRFViolationError(f"DNS resolution failed for host '{hostname}': {e}") from e

    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise SSRFViolationError(
                f"Host '{hostname}' resolved to prohibited address {ip_str} (private, loopback, or link-local)."
            )


def safe_get(
    url: str,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, str]] = None,
    allowed_domains: tuple[str, ...] = (),
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> requests.Response:
    """
    Execute an SSRF-safe HTTP GET request.
    Validates target URL and IP boundaries, streams content, and aborts if max_bytes is exceeded.
    """
    _validate_url_ssrf(url, allowed_domains=allowed_domains)

    default_headers = {
        "User-Agent": "AaqilOrchestratorBot/1.0 (+https://github.com/FarhanAaqil/orchestrater_agent)",
        "Accept": "*/*",
    }
    if headers:
        default_headers.update(headers)

    response = requests.get(
        url,
        headers=default_headers,
        params=params,
        timeout=timeout_s,
        allow_redirects=False,
        stream=True,
    )

    # If redirect, validate target URL recursively
    if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
        redirect_url = response.headers.get("Location")
        if not redirect_url:
            raise SSRFViolationError("Redirect response missing Location header.")
        # Resolve relative redirect URLs if needed
        if redirect_url.startswith("/"):
            parsed = urlparse(url)
            redirect_url = f"{parsed.scheme}://{parsed.netloc}{redirect_url}"
        _validate_url_ssrf(redirect_url, allowed_domains=allowed_domains)
        return safe_get(
            redirect_url,
            headers=headers,
            params=params,
            allowed_domains=allowed_domains,
            timeout_s=timeout_s,
            max_bytes=max_bytes,
        )

    # Validate size bounds
    content_length = response.headers.get("Content-Length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        raise SSRFViolationError(
            f"Response payload {content_length} bytes exceeds maximum size of {max_bytes} bytes."
        )

    # Stream chunks up to max_bytes
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=16384):
        total += len(chunk)
        if total > max_bytes:
            raise SSRFViolationError(
                f"Response exceeded maximum payload limit of {max_bytes} bytes while reading."
            )
        chunks.append(chunk)

    response._content = b"".join(chunks)
    return response


def safe_head(
    url: str,
    headers: Optional[dict[str, str]] = None,
    allowed_domains: tuple[str, ...] = (),
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> requests.Response:
    """Execute an SSRF-safe HTTP HEAD request."""
    _validate_url_ssrf(url, allowed_domains=allowed_domains)
    return requests.head(url, headers=headers, timeout=timeout_s, allow_redirects=False)


def assert_safe_method(method: str) -> None:
    """Ensure HTTP method is GET or HEAD only."""
    upper = method.upper().strip()
    if upper not in ("GET", "HEAD"):
        raise SSRFViolationError(f"HTTP method '{upper}' is strictly forbidden on read tools. Only GET/HEAD allowed.")
