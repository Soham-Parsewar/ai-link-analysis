"""Shared pytest fixtures and test utilities."""

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings
from app.main import app
from app.utils.cache import analysis_cache

SAMPLE_TECH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>CloudPulse Technologies | Unified Cloud Observability & APM</title>
    <meta name="description" content="CloudPulse provides automated real-time cloud observability, metric streaming, and APM for Kubernetes and distributed microservices.">
    <meta name="keywords" content="cloud observability, APM, kubernetes monitoring, log analytics">
    <meta property="og:site_name" content="CloudPulse Technologies">
    <meta property="og:title" content="Unified Cloud Observability">
    <meta property="og:description" content="Automated real-time cloud observability.">
    <style>body { font-family: sans-serif; background: #fff; }</style>
    <script>console.log("analytics tracker loaded");</script>
</head>
<body>
    <div id="cookie-banner" class="cookie-consent modal-backdrop">
        <p>We use cookies to improve your browsing experience. <button>Accept All</button></p>
    </div>
    <header>
        <nav><a href="/">Home</a> | <a href="/services">Services</a> | <a href="/pricing">Pricing</a></nav>
    </header>
    <main>
        <h1>Unified Cloud Observability for Distributed Systems</h1>
        <p>CloudPulse helps engineering and DevOps teams detect outages 10x faster with AI-powered telemetry streaming.</p>

        <h2>Our Core Platform Services</h2>
        <div class="service-card">
            <h3>Kubernetes Cluster Monitoring</h3>
            <p>Full-stack live container monitoring with automated anomaly alerts and cluster resource utilization charts.</p>
        </div>
        <div class="service-card">
            <h3>Distributed APM Tracing</h3>
            <p>End-to-end request tracing across microservice boundaries with zero-configuration instrumentation.</p>
        </div>
        <div class="service-card">
            <h3>Automated Log Analytics</h3>
            <p>High-throughput structured log ingestion with sub-second search and anomaly detection algorithms.</p>
        </div>
        <div class="service-card">
            <h3>DevOps Incident Management</h3>
            <p>Automated root-cause analysis and seamless bi-directional integration with Slack and PagerDuty.</p>
        </div>
        <div class="service-card">
            <h3>Cloud Security Posture Compliance</h3>
            <p>Continuous compliance monitoring against SOC2, ISO27001, and HIPAA benchmarks.</p>
        </div>

        <h2>Why Leading Engineering Teams Choose CloudPulse</h2>
        <p>Our distributed agent architecture reduces compute overhead while processing millions of events per second with 99.99% uptime.</p>
    </main>
    <footer>
        <p>Contact our solution architects: <a href="mailto:support@cloudpulse.io">support@cloudpulse.io</a> or call <a href="tel:+18005550199">+1-800-555-0199</a>.</p>
        <p>&copy; 2026 CloudPulse Technologies Inc. All rights reserved.</p>
    </footer>
</body>
</html>
"""


@pytest.fixture(autouse=True)
def clean_cache():
    """Clear cache before and after every test."""
    analysis_cache.clear()
    yield
    analysis_cache.clear()


@pytest.fixture
def client():
    """Synchronous test client."""
    return TestClient(app)


@pytest.fixture
async def async_client():
    """Asynchronous test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_tech_html():
    """Returns sample tech company HTML."""
    return SAMPLE_TECH_HTML
