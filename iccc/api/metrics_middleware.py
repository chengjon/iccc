"""Metrics middleware for automatic HTTP request tracking."""

import logging
import time
from typing import TYPE_CHECKING, Any

from litestar.connection import Request
from litestar.middleware import ASGIMiddleware
from litestar.response import Response

from iccc.observability import get_metrics, is_metrics_enabled

if TYPE_CHECKING:
    from litestar.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


def create_metrics_middleware(app: "ASGIApp") -> "ASGIApp":
    """
    Create metrics middleware for Prometheus collection.

    Args:
        app: The ASGI application

    Returns:
        ASGI middleware callable
    """
    async def middleware(scope: "Scope", receive: "Receive", send: "Send") -> None:
        """ASGI3 application interface."""
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        if not is_metrics_enabled():
            await app(scope, receive, send)
            return

        # Extract request information
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        query = scope.get("query_string", b"").decode("utf-8")

        # Extract route pattern (simplified approach)
        route_pattern = path
        # Replace numeric IDs with placeholder
        import re
        route_pattern = re.sub(r'/\d+', '/{id}', route_pattern)
        route_pattern = re.sub(r'/[0-9a-fA-F-]{8,}', '/{uuid}', route_pattern)

        # Record request start time
        start_time = time.monotonic()

        # Collect request size if available
        request_size = 0
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length:
            try:
                request_size = int(content_length.decode())
            except (ValueError, UnicodeDecodeError):
                pass

        # Track response
        response_size = 0
        status_code = [200]  # Use list to allow modification in nested function

        # Create wrapper send function to capture response data
        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status", 200)

                # Extract content-length from response headers
                response_headers = message.get("headers", [])
                for name, value in response_headers:
                    if name.lower() == b"content-length":
                        try:
                            response_size = int(value.decode())
                        except (ValueError, UnicodeDecodeError):
                            pass

            await send(message)

        # Extract agent ID from headers if present
        agent_id = "anonymous"
        agent_header = headers.get(b"x-agent-id")
        if agent_header:
            try:
                agent_id = agent_header.decode()
            except UnicodeDecodeError:
                pass

        # Process request
        try:
            await app(scope, receive, send_wrapper)

            # Calculate duration
            duration = time.monotonic() - start_time

            # Record metrics
            metrics_collector = get_metrics()
            metrics_collector.record_http_request(
                method=method,
                route=route_pattern,
                status_code=status_code[0],
                duration=duration,
                request_size=request_size,
                response_size=response_size,
                agent_id=agent_id,
            )

        except Exception as e:
            # Calculate duration even on error
            duration = time.monotonic() - start_time

            # Record error metrics
            metrics_collector = get_metrics()
            metrics_collector.record_http_request(
                method=method,
                route=route_pattern,
                status_code=500,
                duration=duration,
                request_size=request_size,
                response_size=response_size,
                agent_id="error",
            )

            # Re-raise the exception
            raise

    return middleware