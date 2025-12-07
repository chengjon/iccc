"""API route modules."""

from iccc.api.routes.projects import project_router
from iccc.api.routes.agents import agent_router
from iccc.api.routes.tasks import task_router
from iccc.api.routes.observability import observability_router
from iccc.api.routes.prompts import prompt_router

__all__ = [
    "project_router",
    "agent_router",
    "task_router",
    "observability_router",
    "prompt_router",
]
