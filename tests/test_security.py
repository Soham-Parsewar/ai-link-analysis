"""Unit and integration tests for SSRF protection and security constraints."""

import pytest
from fastapi.testclient import TestClient

from app.exceptions import SSRFSecurityError
from app.utils.security import is_ip_restricted, validate_hostname_ssrf, validate_url_security
from app.utils.url_validator import normalize_and_validate_url
import ipaddress


@pytest.mark.parametrize("ip_str", [
    "127.0.0.1",
    "127.0.1.5",
    "10.0.0.1",
    "10.254.0.1",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "192.168.0.254",
    "169.254.169.254",  # AWS/GCP/Azure Metadata
    "169.254.170.2",    # AWS ECS Metadata
    "100.64.0.1",       # Carrier-grade NAT
    "0.0.0.0",
    "::1",              # IPv6 loopback
    "fe80::1",          # IPv6 link-local
    "fc00::1",          # IPv6 unique local
    "::ffff:127.0.0.1", # IPv4-mapped IPv6 loopback
])
def test_restricted_ip_detection(ip_str: str):
    """Verify is_ip_restricted blocks private, loopback, link-local, and metadata IPs."""
    ip = ipaddress.ip_address(ip_str)
    assert is_ip_restricted(ip) is True


@pytest.mark.parametrize("restricted_host", [
    "localhost",
    "test.localhost",
    "app.local",
    "db.internal",
    "metadata.google.internal",
    "instance-data",
    "kubernetes.default",
    "127.0.0.1",
    "10.0.0.5",
    "192.168.1.100",
    "169.254.169.254",
])
def test_validate_hostname_ssrf_blocks_restricted_hosts(restricted_host: str):
    """Verify validate_hostname_ssrf raises SSRFSecurityError for restricted hosts."""
    with pytest.raises(SSRFSecurityError):
        validate_hostname_ssrf(restricted_host)


@pytest.mark.parametrize("safe_host", [
    "example.com",
    "google.com",
    "cloudflare.com",
])
def test_validate_hostname_ssrf_allows_public_hosts(safe_host: str):
    """Verify public internet hostnames pass SSRF checks."""
    # Should not raise exception
    validate_hostname_ssrf(safe_host)


@pytest.mark.parametrize("malicious_url", [
    "http://localhost:8000/admin",
    "http://127.0.0.1:4000/metrics",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/internal-api",
    "http://192.168.0.1/router-login",
    "http://metadata.google.internal/computeMetadata/v1/",
])
def test_api_blocks_ssrf_targets(client: TestClient, malicious_url: str):
    """Verify POST /link-analysis returns HTTP 400 for SSRF targets."""
    response = client.post("/link-analysis", json={"url": malicious_url})
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert any(term in data["detail"].lower() for term in ("security", "internal", "restricted", "loopback", "prohibited"))
