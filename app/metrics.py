import time

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    disable_created_metrics,
)
from starlette.routing import Match


disable_created_metrics()

REGISTRY = CollectorRegistry()
EXCLUDED_ROUTES = frozenset({"/metrics", "/health"})
UNMATCHED_ROUTE = "__unmatched__"

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "route", "status"],
    registry=REGISTRY,
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "route", "status"],
    buckets=(
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.15,
        0.2,
        0.3,
        0.4,
        0.5,
        0.75,
        1.0,
        1.5,
        2.0,
    ),
    registry=REGISTRY,
)

REQUESTS_IN_FLIGHT = Gauge(
    "http_requests_in_flight",
    "HTTP requests currently being served.",
    ["method", "route"],
    registry=REGISTRY,
)


def resolve_route(scope, routes):
    partial_route = None

    for route in routes:
        match, _ = route.matches(scope)

        if match == Match.FULL:
            return route.path_format

        if match == Match.PARTIAL and partial_route is None:
            partial_route = route.path_format

    return partial_route or UNMATCHED_ROUTE


class PrometheusMiddleware:
    def __init__(self, app, router):
        self.app = app
        self.router = router

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        route = resolve_route(scope, self.router.routes)

        if route in EXCLUDED_ROUTES:
            return await self.app(scope, receive, send)

        method = scope["method"]

        REQUESTS_IN_FLIGHT.labels(
            method=method,
            route=route,
        ).inc()

        start = time.perf_counter()

        status = 500

        async def send_wrapper(message):
            nonlocal status

            if message["type"] == "http.response.start":
                status = message["status"]

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start

            REQUESTS_IN_FLIGHT.labels(
                method=method,
                route=route,
            ).dec()

            REQUEST_COUNT.labels(
                method=method,
                route=route,
                status=str(status),
            ).inc()

            REQUEST_DURATION.labels(
                method=method,
                route=route,
                status=str(status),
            ).observe(duration)