"""SSRF validation for URLs fetched by the web layer."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def check_url_ssrf(url: str) -> str | None:
    """Return an error message if *url* targets a private/internal host.

    Validates scheme (http/https only) and resolves the hostname to check
    against all RFC 1918, loopback, link-local, and reserved IP ranges
    using :func:`ipaddress.ip_address`.

    Returns ``None`` if the URL is safe to fetch.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Unsupported URL scheme: {parsed.scheme}"
    hostname = parsed.hostname or ""
    if not hostname:
        return "URL has no hostname"
    # Try parsing hostname as a literal IP address first
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # It's a domain name — resolve to IP
        try:
            info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            addr = ipaddress.ip_address(info[0][4][0])
        except (socket.gaierror, OSError, IndexError):
            # Fail closed: if we cannot resolve the hostname we cannot verify
            # it is safe to fetch.  Allowing unresolvable hosts through would
            # create a fail-open SSRF gate — an attacker could register a
            # domain whose DNS is transiently unavailable, bypassing the check.
            return f"Cannot resolve hostname (SSRF check requires successful DNS resolution): {hostname}"
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return f"Blocked internal/private URL: {hostname}"
    return None


def is_safe_url(url: str) -> bool:
    """Return True if *url* is safe to fetch (not an internal/private address)."""
    return check_url_ssrf(url) is None
