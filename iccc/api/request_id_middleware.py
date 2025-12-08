"""Request ID middleware for distributed tracing."""

import logging
import uuid
from typing import Any

from litestar import Request, Response

logger = logging.getLogger(__name__)


def create_request_id_middleware(app: Any) -> Any:
    """
    Create request ID middleware for distributed tracing.

    Generates or extracts a unique request ID and adds it to:
    - Request state (accessible by handlers)
    - Response headers (X-Request-ID)
    - All log messages (via request context)

    Args:
        app: The ASGI application

    Returns:
        ASGI middleware callable
    """
    async def middleware(scope: Any, receive: Any, send: Any) -> None:
        """ASGI middleware for request ID tracking."""
        # Only process HTTP requests
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        # Build request from scope
        request = Request(scope=scope, receive=receive)

        # Get request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")

        if not request_id:
            # Generate UUID v4 for new request
            request_id = str(uuid.uuid4())

        # Store in scope for access by handlers and subsequent middleware
        scope.setdefault("state", {})["request_id"] = request_id

        logger.debug(
            f"Request ID assigned: {request_id}",
            extra={"request_id": request_id},
        )

        # Create response wrapper to add header
        async def send_wrapper(message: Any) -> None:
            """Wrap send to add request ID header."""
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        # Process request
        await app(scope, receive, send_wrapper)

    return middleware
