"""Model selection strategy for Claude agents."""


from iccc.models.entities import ModelTier, TaskComplexity, TaskType


class ModelSelector:
    """Selects appropriate Claude model based on task type and complexity."""

    # Task type to model mapping (30+ task types)
    TASK_MODEL_MAP: dict[TaskType, ModelTier] = {
        # Haiku tasks (fast, cheap, simple)
        TaskType.FILE_RENAME: ModelTier.HAIKU,
        TaskType.SIMPLE_REFACTOR: ModelTier.HAIKU,
        TaskType.GENERATE_BOILERPLATE: ModelTier.HAIKU,
        TaskType.FORMAT_CODE: ModelTier.HAIKU,
        TaskType.SIMPLE_DOCUMENTATION: ModelTier.HAIKU,
        TaskType.ADD_COMMENTS: ModelTier.HAIKU,
        TaskType.RENAME_VARIABLE: ModelTier.HAIKU,
        TaskType.ADD_TYPE_HINTS: ModelTier.HAIKU,
        TaskType.GENERATE_GETTER_SETTER: ModelTier.HAIKU,
        TaskType.CREATE_CONFIG_FILE: ModelTier.HAIKU,

        # Sonnet tasks (balanced, general development)
        TaskType.GENERAL_CODING: ModelTier.SONNET,
        TaskType.CODE_REFACTOR: ModelTier.SONNET,
        TaskType.BUG_FIX: ModelTier.SONNET,
        TaskType.TEST_WRITING: ModelTier.SONNET,
        TaskType.API_IMPLEMENTATION: ModelTier.SONNET,
        TaskType.DATABASE_QUERY: ModelTier.SONNET,
        TaskType.UI_COMPONENT: ModelTier.SONNET,
        TaskType.DATA_PROCESSING: ModelTier.SONNET,
        TaskType.ERROR_HANDLING: ModelTier.SONNET,
        TaskType.LOGGING_IMPLEMENTATION: ModelTier.SONNET,
        TaskType.VALIDATION_LOGIC: ModelTier.SONNET,
        TaskType.FEATURE_IMPLEMENTATION: ModelTier.SONNET,
        TaskType.CODE_REVIEW: ModelTier.SONNET,
        TaskType.DEPENDENCY_UPDATE: ModelTier.SONNET,
        TaskType.DOCUMENTATION_DETAILED: ModelTier.SONNET,

        # Opus tasks (complex, critical, architectural)
        TaskType.ARCHITECTURE_DESIGN: ModelTier.OPUS,
        TaskType.SECURITY_CRITICAL: ModelTier.OPUS,
        TaskType.COMPLEX_ALGORITHM: ModelTier.OPUS,
        TaskType.SYSTEM_INTEGRATION: ModelTier.OPUS,
        TaskType.PRODUCTION_CRITICAL: ModelTier.OPUS,
        TaskType.PERFORMANCE_OPTIMIZATION: ModelTier.OPUS,
        TaskType.SCALABILITY_DESIGN: ModelTier.OPUS,
        TaskType.DATABASE_SCHEMA_DESIGN: ModelTier.OPUS,
        TaskType.API_DESIGN: ModelTier.OPUS,
        TaskType.SECURITY_AUDIT: ModelTier.OPUS,
        TaskType.DISTRIBUTED_SYSTEM_DESIGN: ModelTier.OPUS,
        TaskType.MIGRATION_STRATEGY: ModelTier.OPUS,
        TaskType.DISASTER_RECOVERY_PLAN: ModelTier.OPUS,
    }

    # Model configurations
    MODEL_CONFIGS: dict[ModelTier, dict] = {
        ModelTier.HAIKU: {
            "model": "claude-3-5-haiku-latest",
            "max_tokens": 4096,
            "timeout": 30,
            "cost_per_1k_tokens": 0.001,
        },
        ModelTier.SONNET: {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 8192,
            "timeout": 120,
            "cost_per_1k_tokens": 0.015,
        },
        ModelTier.OPUS: {
            "model": "claude-opus-4-20250514",
            "max_tokens": 16384,
            "timeout": 300,
            "cost_per_1k_tokens": 0.075,
        },
    }

    @classmethod
    def select_model(
        cls, task_type: TaskType, complexity: TaskComplexity | None = None
    ) -> ModelTier:
        """
        Select the appropriate model for a task.

        Args:
            task_type: Type of task to perform
            complexity: Optional complexity scoring to override base recommendation

        Returns:
            ModelTier enum value
        """
        # Get base model from task type
        base_model = cls.TASK_MODEL_MAP.get(task_type, ModelTier.SONNET)

        # If complexity provided, potentially override based on score
        if complexity:
            score = complexity.calculate_score()

            # High complexity (>4): Use Opus
            if score > 4:
                return ModelTier.OPUS
            # Medium complexity (2.5-4): Use Sonnet
            elif score > 2.5:
                return ModelTier.SONNET
            # Low complexity (<=2.5): Use Haiku
            else:
                return ModelTier.HAIKU

        return base_model

    @classmethod
    def get_model_config(cls, model: ModelTier) -> dict:
        """Get configuration for a model tier."""
        return cls.MODEL_CONFIGS[model]

    @classmethod
    def estimate_cost(cls, model: ModelTier, tokens: int) -> float:
        """Estimate cost for a model call."""
        config = cls.get_model_config(model)
        return (tokens / 1000) * config["cost_per_1k_tokens"]
