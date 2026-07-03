"""Main Litestar API application."""

import logging
import os

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.middleware import DefineMiddleware
from litestar.openapi import OpenAPIConfig

from iccc.api.middleware import (
    api_key_auth_middleware,
    error_handler,
    logging_middleware,
    rate_limit_middleware,
)
from iccc.api.metrics_middleware import create_metrics_middleware
from iccc.api.performance_middleware import create_performance_middleware
from iccc.api.request_id_middleware import create_request_id_middleware
from iccc.api.routes import (
    agent_router,
    metrics_router,
    observability_router,
    prompt_router,
    project_router,
    quality_router,
    task_router,
)
from iccc.db.repositories import MongoDBClient

logger = logging.getLogger(__name__)


@get("/")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        Status information
    """
    return {
        "status": "healthy",
        "service": "iCCC API",
        "version": "0.1.0",
    }


async def on_startup(app: Litestar) -> None:
    """Initialize database connection on startup."""
    db_client = MongoDBClient()
    await db_client.connect()
    app.state.db_client = db_client
    logger.info("MongoDB connected")


async def on_shutdown(app: Litestar) -> None:
    """Close database connection on shutdown."""
    if hasattr(app.state, "db_client"):
        await app.state.db_client.disconnect()
        logger.info("MongoDB disconnected")


def create_app(
    enable_auth: bool | None = None,
    enable_rate_limit: bool | None = None,
    enable_performance: bool | None = None,
    enable_logging: bool | None = None,
    enable_metrics: bool | None = None,
) -> Litestar:
    """
    Create and configure the Litestar application.

    Args:
        enable_auth: Whether to enable API key authentication (defaults to ICCC_ENABLE_AUTH env var)
        enable_rate_limit: Whether to enable rate limiting (defaults to ICCC_ENABLE_RATE_LIMIT env var)
        enable_performance: Whether to enable performance monitoring (defaults to ICCC_ENABLE_PERFORMANCE env var)
        enable_logging: Whether to enable request logging (defaults to ICCC_ENABLE_LOGGING env var)
        enable_metrics: Whether to enable Prometheus metrics (defaults to ICCC_ENABLE_METRICS env var)

    Returns:
        Configured Litestar app
    """
    # Read configuration from environment if not explicitly provided
    if enable_auth is None:
        enable_auth = os.getenv("ICCC_ENABLE_AUTH", "false").lower() in ("true", "1", "yes")

    if enable_rate_limit is None:
        enable_rate_limit = os.getenv("ICCC_ENABLE_RATE_LIMIT", "true").lower() in ("true", "1", "yes")

    if enable_performance is None:
        enable_performance = os.getenv("ICCC_ENABLE_PERFORMANCE", "true").lower() in ("true", "1", "yes")

    if enable_logging is None:
        enable_logging = os.getenv("ICCC_ENABLE_LOGGING", "true").lower() in ("true", "1", "yes")

    if enable_metrics is None:
        enable_metrics = os.getenv("ICCC_ENABLE_METRICS", "true").lower() in ("true", "1", "yes")

    logger.info(
        f"Creating Litestar app with middleware: "
        f"auth={enable_auth}, rate_limit={enable_rate_limit}, "
        f"performance={enable_performance}, logging={enable_logging}, "
        f"metrics={enable_metrics}"
    )

    # Configure CORS
    cors_config = CORSConfig(
        allow_origins=["*"],  # Configure for production
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    # Configure OpenAPI documentation
    openapi_config = OpenAPIConfig(
        title="iCCC Multi-Agent Orchestration API",
        version="0.1.0",
        description="REST API for managing multi-agent AI development workflows",
        contact={
            "name": "iCCC Team",
            "url": "https://github.com/yourusername/iccc",
        },
    )

    # Configure middleware in correct order (first in list = outermost layer)
    # Order: Request ID -> Logging -> Performance -> Metrics -> Rate Limiting -> Authentication
    middleware = []

    # 1. Request ID middleware (first - for tracing all other middleware)
    middleware.append(DefineMiddleware(create_request_id_middleware))

    # 2. Logging middleware (second - logs all requests with request ID)
    if enable_logging:
        middleware.append(DefineMiddleware(logging_middleware))

    # 3. Performance middleware (third - timing includes rate limiting and auth)
    if enable_performance:
        middleware.append(DefineMiddleware(create_performance_middleware))

    # 4. Metrics middleware (fourth - collects Prometheus metrics)
    if enable_metrics:
        middleware.append(DefineMiddleware(create_metrics_middleware))

    # 5. Rate limiting middleware (fifth - before auth to prevent brute force)
    if enable_rate_limit:
        middleware.append(DefineMiddleware(rate_limit_middleware))

    # 6. Authentication middleware (sixth - protect routes)
    if enable_auth:
        middleware.append(DefineMiddleware(api_key_auth_middleware))

    logger.info(f"Middleware stack configured with {len(middleware)} middleware layers")

    # Create app
    app = Litestar(
        route_handlers=[
            health_check,
            project_router,
            agent_router,
            task_router,
            observability_router,
            prompt_router,
            quality_router,
            metrics_router,
        ],
        cors_config=cors_config,
        openapi_config=openapi_config,
        exception_handlers={Exception: error_handler},
        middleware=middleware,
        on_startup=[on_startup],
        on_shutdown=[on_shutdown],
        debug=True,  # Disable in production
    )

    return app


# Create default app instance with environment-based configuration
app = create_app()
