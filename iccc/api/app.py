"""Main Litestar API application."""

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.middleware import DefineMiddleware
from litestar.openapi import OpenAPIConfig

from iccc.api.middleware import api_key_auth_middleware, error_handler, rate_limit_middleware
from iccc.api.routes import (
    agent_router,
    observability_router,
    project_router,
    prompt_router,
    task_router,
)


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


def create_app(enable_auth: bool = False, enable_rate_limit: bool = True) -> Litestar:
    """
    Create and configure the Litestar application.

    Args:
        enable_auth: Whether to enable API key authentication
        enable_rate_limit: Whether to enable rate limiting

    Returns:
        Configured Litestar app
    """
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

    # Configure middleware (order matters: rate limit -> auth -> routes)
    middleware = []

    # Add rate limiting first (apply to all requests)
    if enable_rate_limit:
        middleware.append(DefineMiddleware(rate_limit_middleware))

    # Add authentication after rate limiting
    if enable_auth:
        middleware.append(DefineMiddleware(api_key_auth_middleware))

    # Create app
    app = Litestar(
        route_handlers=[
            health_check,
            project_router,
            agent_router,
            task_router,
            observability_router,
            prompt_router,
        ],
        cors_config=cors_config,
        openapi_config=openapi_config,
        exception_handlers={Exception: error_handler},
        middleware=middleware,
        debug=True,  # Disable in production
    )

    return app


# Create default app instance
app = create_app(enable_auth=False)
