"""Prompt library API endpoints."""

from uuid import UUID

from litestar import Controller, get, post
from litestar.di import Provide

from iccc.api.schemas import PromptCreate, PromptResponse


# Mock prompt storage (in production, use database)
_prompt_storage: dict[UUID, dict] = {}


async def provide_prompt_service() -> dict:
    """Dependency injection for prompt service."""
    return _prompt_storage


class PromptController(Controller):
    """Controller for prompt library endpoints."""

    path = "/prompts"
    tags = ["prompts"]
    dependencies = {"storage": Provide(provide_prompt_service)}

    @post("/")
    async def create_prompt(
        self, data: PromptCreate, storage: dict
    ) -> PromptResponse:
        """
        Create a new prompt template.

        Args:
            data: Prompt creation data
            storage: Prompt storage

        Returns:
            Created prompt
        """
        from uuid import uuid4

        prompt_id = uuid4()
        prompt_data = {
            "id": prompt_id,
            "name": data.name,
            "template": data.template,
            "category": data.category,
            "variables": data.variables,
            "created_at": datetime.now(),
            "metadata": data.metadata,
        }

        storage[prompt_id] = prompt_data
        return PromptResponse.model_validate(prompt_data)

    @get("/")
    async def list_prompts(
        self,
        storage: dict,
        category: str | None = None,
    ) -> list[PromptResponse]:
        """
        List all prompt templates.

        Args:
            storage: Prompt storage
            category: Filter by category

        Returns:
            List of prompts
        """
        prompts = list(storage.values())

        if category:
            prompts = [p for p in prompts if p.get("category") == category]

        return [PromptResponse.model_validate(p) for p in prompts]

    @get("/{prompt_id:uuid}")
    async def get_prompt(
        self, prompt_id: UUID, storage: dict
    ) -> PromptResponse:
        """
        Get a specific prompt template.

        Args:
            prompt_id: Prompt UUID
            storage: Prompt storage

        Returns:
            Prompt template

        Raises:
            NotFoundException: If prompt not found
        """
        from litestar.exceptions import NotFoundException

        prompt = storage.get(prompt_id)
        if not prompt:
            raise NotFoundException(detail=f"Prompt {prompt_id} not found")

        return PromptResponse.model_validate(prompt)


# Export router
prompt_router = PromptController
