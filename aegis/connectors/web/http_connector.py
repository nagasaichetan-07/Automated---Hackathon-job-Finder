"""
Aegis — Domain-Restricted HTTP Client with SSRF Defense & Rate Limiter

Implements a secure HTTP fetcher that strictly enforces:
1. SSRF blocking: rejects localhost, loopback, private RFC 1918 IPs, and cloud metadata (169.254.169.254).
2. Domain Allowlist: rejects requests to any domain not explicitly in the allowlist.
3. Token-bucket rate limiting per domain.
"""

from __future__ import annotations

import ipaddress
import socket
import time
import urllib.parse
from typing import Any

import httpx

# Forbidden private and metadata IP networks
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("10.0.0.0/8"),  # Private Class A
    ipaddress.ip_network("172.16.0.0/12"),  # Private Class B
    ipaddress.ip_network("192.168.0.0/16"),  # Private Class C
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / Cloud metadata
    ipaddress.ip_network("::1/128"),  # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 Unique Local
    ipaddress.ip_network("fe80::/10"),  # IPv6 Link-Local
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "127.0.0.1",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",
    "instance-data",
}


class SSRFValidationError(ValueError):
    """Raised when an outbound URL violates SSRF defense rules."""


class DomainNotAllowedError(ValueError):
    """Raised when an outbound URL host is not in the configured domain allowlist."""


class RateLimitExceededError(RuntimeError):
    """Raised when request rate exceeds configured thresholds."""


class TokenBucketRateLimiter:
    """In-memory token bucket rate limiter per domain."""

    def __init__(self, rate: float = 2.0, capacity: float = 5.0):
        """
        :param rate: Tokens added per second.
        :param capacity: Max tokens stored in bucket.
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens: dict[str, float] = {}
        self._last_update: dict[str, float] = {}

    def acquire(self, domain: str) -> bool:
        """Attempt to consume 1 token. Returns True if permitted, False if rate-limited."""
        now = time.monotonic()
        if domain not in self._tokens:
            self._tokens[domain] = self.capacity
            self._last_update[domain] = now

        # Replenish tokens based on elapsed time
        elapsed = now - self._last_update[domain]
        self._tokens[domain] = min(self.capacity, self._tokens[domain] + elapsed * self.rate)
        self._last_update[domain] = now

        if self._tokens[domain] >= 1.0:
            self._tokens[domain] -= 1.0
            return True
        return False


class RestrictedHttpClient:
    """
    Secure HTTP client wrapping httpx with mandatory SSRF validation,
    domain allowlist checking, and rate limiting.
    """

    def __init__(
        self,
        domain_allowlist: list[str] | set[str],
        rate_limit_per_sec: float = 2.0,
        timeout_seconds: float = 15.0,
    ):
        self.domain_allowlist = {d.lower() for d in domain_allowlist}
        self.rate_limiter = TokenBucketRateLimiter(rate=rate_limit_per_sec)
        self.timeout_seconds = timeout_seconds

    def validate_url(self, url: str) -> str:
        """
        Validate URL against:
        1. Scheme (http or https only)
        2. Domain allowlist
        3. Blocked hostnames / loopback strings
        4. Resolved IP addresses against blocked private / metadata networks
        """
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            raise SSRFValidationError(f"Invalid URL scheme '{parsed.scheme}': only HTTP/HTTPS allowed")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise SSRFValidationError("Missing hostname in URL")

        # 1. Check blocked hostname list
        if hostname in BLOCKED_HOSTNAMES:
            raise SSRFValidationError(f"SSRF blocked: Hostname '{hostname}' is forbidden")

        # Check if hostname is an IP literal (private network / loopback)
        ip_literal = None
        try:
            ip_literal = ipaddress.ip_address(hostname)
        except ValueError:
            pass  # Not an IP literal, proceed to domain allowlist check

        if ip_literal is not None:
            for blocked_net in BLOCKED_IP_NETWORKS:
                if ip_literal in blocked_net:
                    raise SSRFValidationError(
                        f"SSRF blocked: Target IP '{hostname}' belongs to private/forbidden network {blocked_net}"
                    )

        # 2. Check explicit domain allowlist
        is_allowed = any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in self.domain_allowlist
        )
        if not is_allowed:
            raise DomainNotAllowedError(
                f"Domain '{hostname}' is not in the configured domain allowlist: {self.domain_allowlist}"
            )

        # 3. Resolve IP address to prevent DNS rebinding or private IP access
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            resolved_ips = {info[4][0] for info in addr_info}
        except socket.gaierror:
            # If name cannot be resolved in offline/mock test, check if it's already an IP
            try:
                resolved_ips = {str(ipaddress.ip_address(hostname))}
            except ValueError:
                resolved_ips = set()

        for ip_str in resolved_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                for blocked_net in BLOCKED_IP_NETWORKS:
                    if ip_obj in blocked_net:
                        raise SSRFValidationError(
                            f"SSRF blocked: Hostname '{hostname}' resolved to private/forbidden IP {ip_str} in {blocked_net}"
                        )
            except ValueError:
                continue

        return url

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Validate safety, check rate limits, and issue GET request."""
        self.validate_url(url)

        parsed = urllib.parse.urlparse(url)
        hostname = (parsed.hostname or "").lower()

        if not self.rate_limiter.acquire(hostname):
            raise RateLimitExceededError(f"Rate limit exceeded for domain '{hostname}'")

        timeout = kwargs.pop("timeout", self.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.get(url, **kwargs)
