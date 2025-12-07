"""API middleware for error handling, authentication, and logging."""

import logging
from datetime import datetime
from typing import Any

from litestar import Request, Response
from litestar.exceptions import (
    HTTPException,
    NotFoundException,
    PermissionDeniedException,
    ValidationException,
)
from litestar.middleware import DefineMiddleware
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR

from iccc.api.schemas import ErrorResponse

logger = logging.getLogger(__name__)


def error_handler(request: Request, exc: Exception) -> Response[ErrorResponse]:
    """
    Global error handler for all API exceptions.

    Converts exceptions to standardized ErrorResponse format.

    Args:
        request: The request that caused the error
        exc: The exception that was raised

    Returns:
        Response with ErrorResponse body
    """
    # Log the error
    logger.error(
        f"API Error: {type(exc).__name__} - {str(exc)}",
        extra={
            "path": request.url.path,
            "method": request.method,
            "client": request.client.host if request.client else None,
        },
        exc_info=exc,
    )

    # Handle known HTTP exceptions
    if isinstance(exc, NotFoundException):
        status_code = 404
        error_type = "not_found"
        message = str(exc.detail)
    elif isinstance(exc, PermissionDeniedException):
        status_code = 403
        error_type = "permission_denied"
        message = str(exc.detail)
    elif isinstance(exc, ValidationException):
        status_code = 422
        error_type = "validation_error"
        message = "Request validation failed"
        # Include validation details
        details = {"validation_errors": exc.extra if hasattr(exc, "extra") else None}
    elif isinstance(exc, HTTPException):
        status_code = exc.status_code
        error_type = "http_error"
        message = str(exc.detail)
    else:
        # Unknown error - return 500
        status_code = HTTP_500_INTERNAL_SERVER_ERROR
        error_type = "internal_error"
        message = "An internal server error occurred"

    # Build error response
    error_response = ErrorResponse(
        error=error_type,
        message=message,
        details=details if "details" in locals() else None,
        timestamp=datetime.now(),
    )

    return Response(
        content=error_response.model_dump(mode="json"),
        status_code=status_code,
        media_type="application/json",
    )


def create_error_middleware() -> DefineMiddleware:
    """
    Create error handling middleware.

    Returns:
        Middleware configuration
    """
    # In Litestar, exception handlers are configured at app level
    # This function returns the handler for configuration
    return error_handler


# Request logging middleware
def logging_middleware(app: Any) -> Any:
    """
    Create request logging middleware.

    Args:
        app: The ASGI application

    Returns:
        Middleware wrapper
    """
    async def middleware(request: Request, next_handler: Any) -> Response:
        """Log all incoming requests and their responses."""
        start_time = datetime.now()

        # Log request
        logger.info(
            f"Request: {request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None,
            },
        )

        # Process request
        response = await next_handler(request)

        # Log response
        duration = (datetime.now() - start_time).total_seconds() * 1000  # ms
        logger.info(
            f"Response: {response.status_code} ({duration:.2f}ms)",
            extra={
                "status": response.status_code,
                "duration_ms": duration,
            },
        )

        return response

    return middleware


# API Key authentication middleware
def api_key_auth_middleware(app: Any) -> Any:
    """
    Create API key authentication middleware.

    Args:
        app: The ASGI application

    Returns:
        Middleware wrapper
    """
    async def middleware(request: Request, next_handler: Any) -> Response:
        """Verify API key authentication."""
        # Skip auth for health/docs endpoints
        if request.url.path in ["/", "/health", "/schema", "/schema/openapi.json"]:
            return await next_handler(request)

        # Check for API key header
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            raise PermissionDeniedException(detail="Missing API key (X-API-Key header required)")

        # Validate API key
        # TODO: Implement actual validation against database/config
        valid_keys = ["dev-key-12345"]  # Placeholder

        if api_key not in valid_keys:
            raise PermissionDeniedException(detail="Invalid API key")

        # API key is valid - continue
        return await next_handler(request)

    return middleware


# Rate limiting middleware (placeholder)
async def rate_limit_middleware(request: Request, next_handler: Any) -> Response:
    """
    Apply rate limiting to API requests.

    TODO: Implement actual rate limiting using Redis.

    Args:
        request: Incoming request
        next_handler: Next middleware/handler in chain

    Returns:
        Response from handler
    """
    # Placeholder - implement with Redis in production
    return await next_handler(request)
