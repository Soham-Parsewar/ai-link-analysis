"""SSRF Protection and Network Security Utilities."""

import ipaddress
import logging
import socket
from urllib.parse import urlsplit
from app.exceptions import SSRFSecurityError

logger = logging.getLogger(__name__)

# Restricted hostnames that must be blocked outright
RESTRICTED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
    "metadata",
    "kubernetes.default",
    "kubernetes.default.svc",
}

# Restricted domain suffixes
RESTRICTED_DOMAIN_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".cluster.local",
    ".corp",
    ".home.arpa",
)

# Known Cloud Metadata IP Addresses
CLOUD_METADATA_IPS = {
    "169.254.169.254",     # AWS / GCP / Azure / OpenStack metadata
    "169.254.170.2",       # AWS ECS task metadata
    "fd00:ec2::254",       # AWS IPv6 metadata
}


def is_ip_restricted(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address belongs to private, loopback, link-local, or reserved ranges."""
    # Check for IPv6 mapped IPv4 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped

    ip_str = str(ip)
    if ip_str in CLOUD_METADATA_IPS:
        return True

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    # Carrier-grade NAT (100.64.0.0/10)
    if isinstance(ip, ipaddress.IPv4Address):
        cgnat_net = ipaddress.IPv4Network("100.64.0.0/10")
        if ip in cgnat_net:
            return True

    return False


def validate_hostname_ssrf(hostname: str) -> None:
    """
    Validate that a hostname does not resolve to private, loopback, or cloud metadata IPs.

    Raises:
        SSRFSecurityError: If hostname is restricted or resolves to a disallowed IP.
    """
    if not hostname:
        raise SSRFSecurityError("Hostname cannot be empty.")

    lower_host = hostname.lower().strip()

    # Check against restricted hostnames
    if lower_host in RESTRICTED_HOSTNAMES or any(
        lower_host.endswith(suffix) for suffix in RESTRICTED_DOMAIN_SUFFIXES
    ):
        logger.warning(f"SSRF Attempt: Blocked restricted hostname '{lower_host}'")
        raise SSRFSecurityError("Access to internal, loopback, or private hostnames is prohibited.")

    # Check if the hostname itself is directly a numeric IP address
    try:
        ip = ipaddress.ip_address(lower_host)
        if is_ip_restricted(ip):
            logger.warning(f"SSRF Attempt: Direct restricted IP requested: {ip}")
            raise SSRFSecurityError("Access to internal, private, or metadata IP addresses is prohibited.")
        return
    except ValueError:
        # Not a raw IP literal, proceed to DNS resolution
        pass

    # Resolve hostname via DNS
    try:
        addr_info = socket.getaddrinfo(lower_host, None)
    except socket.gaierror as e:
        logger.warning(f"DNS resolution failure for host '{lower_host}': {e}")
        raise SSRFSecurityError(f"Could not resolve website host '{lower_host}'.")

    if not addr_info:
        raise SSRFSecurityError(f"Could not resolve IP address for '{lower_host}'.")

    # Verify every resolved address
    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
            if is_ip_restricted(ip):
                logger.warning(
                    f"SSRF Attempt: Hostname '{lower_host}' resolved to restricted IP: {ip_str}"
                )
                raise SSRFSecurityError("Resolved IP address points to an internal or restricted network.")
        except ValueError:
            raise SSRFSecurityError("Invalid resolved IP address.")


def validate_url_security(url: str) -> None:
    """Parse and validate the URL for SSRF vulnerabilities."""
    try:
        parsed = urlsplit(url)
    except Exception as e:
        raise SSRFSecurityError(f"Malformed URL: {e}")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityError("URL is missing a valid hostname.")

    validate_hostname_ssrf(hostname)
