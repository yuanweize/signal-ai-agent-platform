"""
MCP Security and Governance controls: SSRF protection, timeout, and response limits.
"""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

logger = logging.getLogger("ai.mcp.security")

MAX_MCP_RESPONSE_BYTES = 500 * 1024  # 500 KB limit
DEFAULT_MCP_TIMEOUT_SECONDS = 10.0


def is_ssrf_safe_url(url: str, allow_localhost: bool = False) -> tuple[bool, str | None]:
    """
    Validate that an HTTP MCP server URL is not pointing to forbidden private/link-local networks.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Unsupported scheme: {parsed.scheme}"

        hostname = parsed.hostname
        if not hostname:
            return False, "Missing hostname in URL"

        if hostname == "localhost" or hostname.startswith("127."):
            if allow_localhost:
                return True, None
            return False, "Localhost endpoints forbidden by SSRF policy"

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private and not allow_localhost:
                return False, f"Private IP address {hostname} forbidden by SSRF policy"
            if ip.is_loopback and not allow_localhost:
                return False, f"Loopback IP address {hostname} forbidden by SSRF policy"
            if ip.is_link_local:
                return False, f"Link-local IP address {hostname} forbidden by SSRF policy"
        except ValueError:
            # Hostname is a domain name, not a raw IP
            pass

        return True, None
    except Exception as e:
        return False, f"Invalid URL: {e}"
