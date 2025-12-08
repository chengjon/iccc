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
    async def middleware(scope: Any, receive: Any, send: Any) -> None:
        """ASGI middleware for request logging."""
        # Only process HTTP requests
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        start_time = datetime.now()
        request = Request(scope=scope, receive=receive)
        request_id = scope.get("state", {}).get("request_id")

        # Log request
        extra = {
            "method": scope.get("method"),
            "path": scope.get("path"),
            "client": request.client.host if request.client else None,
        }
        if request_id:
            extra["request_id"] = request_id

        logger.info(
            f"Request: {scope.get('method')} {scope.get('path')}",
            extra=extra,
        )

        # Track response status
        status_code = [200]  # Default

        async def send_wrapper(message: Any) -> None:
            """Wrap send to log response."""
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status", 200)
            elif message["type"] == "http.response.body":
                # Log response after headers sent
                duration = (datetime.now() - start_time).total_seconds() * 1000  # ms
                extra_resp = {
                    "status": status_code[0],
                    "duration_ms": duration,
                }
                if request_id:
                    extra_resp["request_id"] = request_id

                logger.info(
                    f"Response: {status_code[0]} ({duration:.2f}ms)",
                    extra=extra_resp,
                )
            await send(message)

        await app(scope, receive, send_wrapper)

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


# Rate limiting middleware factory
def rate_limit_middleware(app: Any) -> Any:
    """
    Create rate limiting middleware.

    Args:
        app: The ASGI application

    Returns:
        Middleware wrapper
    """
    async def middleware(scope: Any, receive: Any, send: Any) -> None:
        """ASGI middleware for rate limiting."""
        # Only process HTTP requests
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        config = get_config()
        rate_config = config.rate_limit

        # Build request from scope
        request = Request(scope=scope, receive=receive)

        # Skip if rate limiting is disabled
        if not rate_config.enabled:
            await app(scope, receive, send)
            return

        # Skip exempt paths
        if request.url.path in rate_config.exempt_paths:
            await app(scope, receive, send)
            return

        # Get rate limiter instance
        limiter = get_rate_limiter()
        if not limiter:
            logger.warning("Rate limiter not initialized - allowing request")
            await app(scope, receive, send)
            return

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

            if result.allowed:
                # Request is within limits - proceed with headers
                async def send_wrapper(message: Any) -> None:
                    """Wrap send to add rate limit headers."""
                    if message["type"] == "http.response.start":
                        headers = list(message.get("headers", []))
                        headers.append((b"x-ratelimit-limit", str(result.limit).encode()))
                        headers.append((b"x-ratelimit-remaining", str(result.remaining).encode()))
                        headers.append((b"x-ratelimit-reset", str(int(result.reset_timestamp)).encode()))
                        message["headers"] = headers
                    await send(message)

                await app(scope, receive, send_wrapper)
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

                # Send 429 response
                response_body = error_response.model_dump_json().encode()
                await send({
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(response_body)).encode()),
                        (b"retry-after", str(result.reset_after_seconds).encode()),
                        (b"x-ratelimit-limit", str(result.limit).encode()),
                        (b"x-ratelimit-remaining", str(result.remaining).encode()),
                        (b"x-ratelimit-reset", str(int(result.reset_timestamp)).encode()),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": response_body,
                })

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
            await app(scope, receive, send)

    return middleware
