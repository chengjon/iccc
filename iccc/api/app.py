"""Main Litestar API application."""

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.openapi import OpenAPIConfig

from iccc.api.middleware import (
    api_key_auth_middleware,
    error_handler,
    logging_middleware,
)
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


def create_app(enable_auth: bool = False) -> Litestar:
    """
    Create and configure the Litestar application.

    Args:
        enable_auth: Whether to enable API key authentication

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

    # Build middleware stack
    middleware = [logging_middleware]
    if enable_auth:
        middleware.append(api_key_auth_middleware)

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
        middleware=middleware,
        exception_handlers={Exception: error_handler},
        debug=True,  # Disable in production
    )

    return app


# Create default app instance
app = create_app(enable_auth=False)
