"""Performance monitoring middleware for request timing and slow request detection."""

import logging
import os
import time
from typing import Any

from litestar import Request, Response

logger = logging.getLogger(__name__)


def create_performance_middleware(app: Any) -> Any:
    """
    Create performance monitoring middleware.

    Tracks request duration and:
    - Adds X-Response-Time header to all responses
    - Logs slow requests exceeding threshold
    - Provides timing metrics for observability

    Args:
        app: The ASGI application

    Returns:
        ASGI middleware callable
    """
    # Get configuration from environment
    log_slow_requests = os.getenv("ICCC_LOG_SLOW_REQUESTS", "true").lower() in (
        "true",
        "1",
        "yes",
    )
    slow_threshold_ms = float(
        os.getenv("ICCC_SLOW_REQUEST_THRESHOLD_MS", "1000")
    )  # Default 1 second

    async def middleware(scope: Any, receive: Any, send: Any) -> None:
        """ASGI middleware for performance monitoring."""
        # Only process HTTP requests
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        # Record start time
        start_time = time.perf_counter()

        # Build request from scope
        request = Request(scope=scope, receive=receive)

        # Get request ID if available
        request_id = scope.get("state", {}).get("request_id")

        # Track response status
        status_code = [200]  # Default, will be updated

        # Create response wrapper to add header
        async def send_wrapper(message: Any) -> None:
            """Wrap send to add performance header."""
            if message["type"] == "http.response.start":
                # Calculate duration
                end_time = time.perf_counter()
                duration_ms = (end_time - start_time) * 1000  # Convert to milliseconds

                # Capture status code
                status_code[0] = message.get("status", 200)

                # Add response time header
                headers = list(message.get("headers", []))
                headers.append((b"x-response-time", f"{duration_ms:.2f}ms".encode()))
                message["headers"] = headers

                # Log performance metrics
                extra = {
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_code[0],
                    "duration_ms": duration_ms,
                }

                if request_id:
                    extra["request_id"] = request_id

                # Log slow requests
                if log_slow_requests and duration_ms > slow_threshold_ms:
                    logger.warning(
                        f"Slow request detected: {scope.get('method')} {scope.get('path')} "
                        f"took {duration_ms:.2f}ms (threshold: {slow_threshold_ms}ms)",
                        extra=extra,
                    )
                else:
                    logger.debug(
                        f"Request completed: {scope.get('method')} {scope.get('path')} "
                        f"in {duration_ms:.2f}ms",
                        extra=extra,
                    )

            await send(message)

        # Process request
        await app(scope, receive, send_wrapper)

    return middleware
