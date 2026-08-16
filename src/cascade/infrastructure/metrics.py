from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram
from prometheus_client import generate_latest as _generate_latest

REGISTRY = CollectorRegistry(auto_describe=True)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests handled.",
    labelnames=("method", "path", "status"),
    registry=REGISTRY,
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    labelnames=("method", "path"),
    registry=REGISTRY,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


def render_metrics() -> tuple[bytes, str]:
    return _generate_latest(REGISTRY), CONTENT_TYPE_LATEST
