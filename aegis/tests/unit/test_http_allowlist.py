"""
Aegis — Unit Tests: Domain Allowlist & SSRF Hardening

Validates SSRF prevention (localhost, private RFC 1918 IPs, cloud metadata),
domain allowlist enforcement, scheme restrictions, and rate limiting.
"""

from __future__ import annotations

import pytest
from connectors.web.http_connector import (
    DomainNotAllowedError,
    RestrictedHttpClient,
    SSRFValidationError,
    TokenBucketRateLimiter,
)


@pytest.fixture
def secure_client() -> RestrictedHttpClient:
    return RestrictedHttpClient(
        domain_allowlist=["example.com", "api.greenhouse.io", "lever.co"],
        rate_limit_per_sec=10.0,
    )


def test_ssrf_rejects_localhost(secure_client: RestrictedHttpClient) -> None:
    """Outbound requests targeting localhost are rejected immediately."""
    with pytest.raises(SSRFValidationError, match="SSRF blocked"):
        secure_client.validate_url("http://localhost:8000/api")


def test_ssrf_rejects_loopback_ip(secure_client: RestrictedHttpClient) -> None:
    """Outbound requests targeting 127.0.0.1 are rejected."""
    with pytest.raises(SSRFValidationError, match="SSRF blocked"):
        secure_client.validate_url("http://127.0.0.1:9200/_cat/indices")


def test_ssrf_rejects_cloud_metadata(secure_client: RestrictedHttpClient) -> None:
    """Outbound requests targeting cloud metadata 169.254.169.254 are rejected."""
    with pytest.raises(SSRFValidationError, match="SSRF blocked"):
        secure_client.validate_url("http://169.254.169.254/latest/meta-data/")


def test_ssrf_rejects_private_ip_ranges(secure_client: RestrictedHttpClient) -> None:
    """Outbound requests to private class A/B/C ranges are rejected."""
    with pytest.raises(SSRFValidationError):
        secure_client.validate_url("http://10.0.0.5/internal")

    with pytest.raises(SSRFValidationError):
        secure_client.validate_url("http://192.168.1.100/status")

    with pytest.raises(SSRFValidationError):
        secure_client.validate_url("http://172.16.0.1/admin")


def test_ssrf_rejects_non_http_schemes(secure_client: RestrictedHttpClient) -> None:
    """Schemes like file://, gopher://, ftp:// are rejected."""
    with pytest.raises(SSRFValidationError, match="only HTTP/HTTPS allowed"):
        secure_client.validate_url("file:///etc/passwd")


def test_domain_allowlist_enforcement(secure_client: RestrictedHttpClient) -> None:
    """Unapproved domains not in allowlist are rejected with DomainNotAllowedError."""
    with pytest.raises(DomainNotAllowedError, match="not in the configured domain allowlist"):
        secure_client.validate_url("https://malicious-external-site.com/exploit")


def test_domain_allowlist_permits_whitelisted_and_subdomains(
    secure_client: RestrictedHttpClient,
) -> None:
    """Approved domains and subdomains pass validation."""
    assert secure_client.validate_url("https://example.com/jobs") == "https://example.com/jobs"
    assert (
        secure_client.validate_url("https://boards.api.greenhouse.io/v1/jobs")
        == "https://boards.api.greenhouse.io/v1/jobs"
    )


def test_rate_limiter_exhaustion() -> None:
    """Burst exceeding capacity within 0 seconds exhausts tokens and rejects."""
    limiter = TokenBucketRateLimiter(rate=1.0, capacity=2.0)
    domain = "api.test.com"

    # Consume available tokens
    assert limiter.acquire(domain) is True
    assert limiter.acquire(domain) is True

    # Third attempt without time elapsed fails
    assert limiter.acquire(domain) is False
