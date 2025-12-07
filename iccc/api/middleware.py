"""API middleware for error handling, authentication, and logging."""

import logging
from datetime import datetime
from typing import Any, Optional

from litestar import Request, Response
from litestar.exceptions import (
    HTTPException,
    NotFoundException,
    PermissionDeniedException,
    ValidationException,
)
from litestar.middleware import DefineMiddleware
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR

from iccc.api.auth import APIKeyManager
from iccc.api.rate_limiter import RedisRateLimiter
from iccc.api.schemas import ErrorResponse
from iccc.config import get_config

logger = logging.getLogger(__name__)

# Global API key manager instance
_api_key_manager: APIKeyManager | None = None

# Global rate limiter instance
_rate_limiter: Optional[RedisRateLimiter] = None


def set_api_key_manager(manager: APIKeyManager) -> None:
    """Set the global API key manager instance."""
    global _api_key_manager
    _api_key_manager = manager


def get_api_key_manager() -> APIKeyManager:
    """Get or create the global API key manager instance."""
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager


def set_rate_limiter(limiter: RedisRateLimiter) -> None:
    """Set the global rate limiter instance."""
    global _rate_limiter
    _rate_limiter = limiter


def get_rate_limiter() -> Optional[RedisRateLimiter]:
    """Get the global rate limiter instance."""
    return _rate_limiter


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


# API Key authentication middleware factory
def api_key_auth_middleware(app: Any) -> Any:
    """
    Create API key authentication middleware.

    Supports both X-API-Key header and Authorization: Bearer token formats.

    Args:
        app: The ASGI application

    Returns:
        ASGI middleware callable
    """
    async def middleware(scope: Any, receive: Any, send: Any) -> None:
        """ASGI middleware for API key authentication."""
        # Only process HTTP requests
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        # Build request from scope
        request = Request(scope=scope, receive=receive)

        # Skip auth for health/docs endpoints
        if request.url.path in ["/", "/health", "/schema", "/schema/openapi.json"]:
            await app(scope, receive, send)
            return

        # Check for API key in X-API-Key header
        api_key = request.headers.get("X-API-Key")

        # Also check Authorization header (Bearer format)
        if not api_key:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                api_key = auth_header[7:]  # Remove "Bearer " prefix

        if not api_key:
            logger.warning(
                "API request missing authentication",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "client": request.client.host if request.client else None,
                },
            )
            raise PermissionDeniedException(
                detail="Missing API key. Provide X-API-Key header or Authorization: Bearer <token>"
            )

        # Validate API key using APIKeyManager
        manager = get_api_key_manager()
        is_valid, metadata = await manager.validate_key(api_key)

        if not is_valid:
            logger.warning(
                "API request with invalid key",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "client": request.client.host if request.client else None,
                    "key_prefix": api_key[:4] if len(api_key) >= 4 else "****",
                },
            )
            raise PermissionDeniedException(detail="Invalid or expired API key")

        # Log successful authentication with masked key
        if metadata:
            logger.debug(
                f"Authenticated request with key: {metadata.mask_for_logging()}",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "key_id": metadata.key_id,
                },
            )

        # API key is valid - continue
        await app(scope, receive, send)

    return middleware


# Rate limiting middleware
async def rate_limit_middleware(request: Request, next_handler: Any) -> Response:
    """
    Apply rate limiting to API requests using Redis sliding window algorithm.

    Rate limits are applied per API key (if authenticated) or per client IP.
    Returns 429 Too Many Requests when limit is exceeded.

    Args:
        request: Incoming request
        next_handler: Next middleware/handler in chain

    Returns:
        Response from handler with rate limit headers
    """
    config = get_config()
    rate_config = config.rate_limit

    # Skip if rate limiting is disabled
    if not rate_config.enabled:
        return await next_handler(request)

    # Skip exempt paths
    if request.url.path in rate_config.exempt_paths:
        return await next_handler(request)

    # Get rate limiter instance
    limiter = get_rate_limiter()
    if not limiter:
        logger.warning("Rate limiter not initialized - allowing request")
        return await next_handler(request)

    # Determine rate limit key (API key preferred, fallback to IP)
    limit_key = None

    # Try to get API key from headers
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header[7:]

    if api_key:
        # Use API key as limit key
        limit_key = f"apikey:{api_key[:16]}"  # Use prefix to avoid key exposure
    else:
        # Fallback to client IP
        client_ip = request.client.host if request.client else "unknown"
        limit_key = f"ip:{client_ip}"

    # Check rate limit
    try:
        result = await limiter.check_rate_limit(limit_key, increment=True)

        # Add rate limit headers to response
        if result.allowed:
            # Request is within limits - proceed
            response = await next_handler(request)
        else:
            # Rate limit exceeded - return 429
            logger.warning(
                f"Rate limit exceeded for key '{limit_key}' on path {request.url.path}",
                extra={
                    "limit_key": limit_key,
                    "path": request.url.path,
                    "method": request.method,
                },
            )

            error_response = ErrorResponse(
                error="rate_limit_exceeded",
                message=f"Rate limit exceeded. Maximum {result.limit} requests per {rate_config.window_seconds} seconds.",
                details={
                    "limit": result.limit,
                    "window_seconds": rate_config.window_seconds,
                    "retry_after": result.reset_after_seconds,
                },
                timestamp=datetime.now(),
            )

            response = Response(
                content=error_response.model_dump(mode="json"),
                status_code=429,  # Too Many Requests
                media_type="application/json",
                headers={
                    "Retry-After": str(result.reset_after_seconds),
                },
            )

        # Add rate limit headers to all responses
        response.headers.update(
            {
                "X-RateLimit-Limit": str(result.limit),
                "X-RateLimit-Remaining": str(result.remaining),
                "X-RateLimit-Reset": str(int(result.reset_timestamp)),
            }
        )

        return response

    except Exception as e:
        # On any error, fail open (allow request) but log the error
        logger.error(
            f"Rate limiting error for key '{limit_key}': {e}",
            exc_info=True,
            extra={
                "limit_key": limit_key,
                "path": request.url.path,
            },
        )
        logger.warning(f"Rate limiting bypassed due to error - allowing request")
        return await next_handler(request)
