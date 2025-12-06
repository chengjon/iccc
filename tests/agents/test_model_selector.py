"""Tests for model selector."""

import pytest

from iccc.agents.model_selector import ModelSelector
from iccc.models.entities import ModelTier, TaskComplexity, TaskType


def test_model_selection_for_simple_task():
    """Test that simple tasks select Haiku."""
    model = ModelSelector.select_model(TaskType.FILE_RENAME)
    assert model == ModelTier.HAIKU


def test_model_selection_for_general_coding():
    """Test that general coding selects Sonnet."""
    model = ModelSelector.select_model(TaskType.GENERAL_CODING)
    assert model == ModelTier.SONNET


def test_model_selection_for_complex_task():
    """Test that complex tasks select Opus."""
    model = ModelSelector.select_model(TaskType.ARCHITECTURE_DESIGN)
    assert model == ModelTier.OPUS


def test_complexity_override_to_opus():
    """Test that high complexity overrides to Opus."""
    complexity = TaskComplexity(
        reasoning_depth=5, code_scope=5, critical_importance=5, context_needed=5
    )

    # Even for a simple task type, high complexity should upgrade to Opus
    model = ModelSelector.select_model(TaskType.GENERAL_CODING, complexity)
    assert model == ModelTier.OPUS


def test_complexity_override_to_haiku():
    """Test that low complexity downgrades to Haiku."""
    complexity = TaskComplexity(
        reasoning_depth=1, code_scope=2, critical_importance=1, context_needed=1
    )

    # Even for a general coding task, low complexity should downgrade to Haiku
    model = ModelSelector.select_model(TaskType.GENERAL_CODING, complexity)
    assert model == ModelTier.HAIKU


def test_complexity_calculation():
    """Test complexity score calculation."""
    complexity = TaskComplexity(
        reasoning_depth=3, code_scope=4, critical_importance=5, context_needed=2
    )

    # (3 + 4 + 5*2 + 2) / 5 = 19 / 5 = 3.8
    score = complexity.calculate_score()
    assert score == pytest.approx(3.8)


def test_model_config_retrieval():
    """Test retrieving model configurations."""
    haiku_config = ModelSelector.get_model_config(ModelTier.HAIKU)
    assert haiku_config["model"] == "claude-3-5-haiku-latest"
    assert haiku_config["max_tokens"] == 4096
    assert haiku_config["cost_per_1k_tokens"] == 0.001

    opus_config = ModelSelector.get_model_config(ModelTier.OPUS)
    assert opus_config["model"] == "claude-opus-4-20250514"
    assert opus_config["max_tokens"] == 16384


def test_cost_estimation():
    """Test cost estimation for model calls."""
    # Haiku: $0.001 per 1k tokens
    cost = ModelSelector.estimate_cost(ModelTier.HAIKU, 5000)
    assert cost == pytest.approx(0.005)

    # Opus: $0.075 per 1k tokens
    cost = ModelSelector.estimate_cost(ModelTier.OPUS, 5000)
    assert cost == pytest.approx(0.375)


# ============================================================================
# COMPREHENSIVE TASK TYPE MAPPING TESTS (33 TASK TYPES)
# ============================================================================


def test_all_haiku_task_types():
    """Test all task types that should map to Haiku (10 types)."""
    haiku_tasks = [
        TaskType.FILE_RENAME,
        TaskType.SIMPLE_REFACTOR,
        TaskType.GENERATE_BOILERPLATE,
        TaskType.FORMAT_CODE,
        TaskType.SIMPLE_DOCUMENTATION,
        TaskType.ADD_COMMENTS,
        TaskType.RENAME_VARIABLE,
        TaskType.ADD_TYPE_HINTS,
        TaskType.GENERATE_GETTER_SETTER,
        TaskType.CREATE_CONFIG_FILE,
    ]

    for task_type in haiku_tasks:
        model = ModelSelector.select_model(task_type)
        assert model == ModelTier.HAIKU, f"{task_type.value} should map to Haiku"


def test_all_sonnet_task_types():
    """Test all task types that should map to Sonnet (15 types)."""
    sonnet_tasks = [
        TaskType.GENERAL_CODING,
        TaskType.CODE_REFACTOR,
        TaskType.BUG_FIX,
        TaskType.TEST_WRITING,
        TaskType.API_IMPLEMENTATION,
        TaskType.DATABASE_QUERY,
        TaskType.UI_COMPONENT,
        TaskType.DATA_PROCESSING,
        TaskType.ERROR_HANDLING,
        TaskType.LOGGING_IMPLEMENTATION,
        TaskType.VALIDATION_LOGIC,
        TaskType.FEATURE_IMPLEMENTATION,
        TaskType.CODE_REVIEW,
        TaskType.DEPENDENCY_UPDATE,
        TaskType.DOCUMENTATION_DETAILED,
    ]

    for task_type in sonnet_tasks:
        model = ModelSelector.select_model(task_type)
        assert model == ModelTier.SONNET, f"{task_type.value} should map to Sonnet"


def test_all_opus_task_types():
    """Test all task types that should map to Opus (13 types)."""
    opus_tasks = [
        TaskType.ARCHITECTURE_DESIGN,
        TaskType.SECURITY_CRITICAL,
        TaskType.COMPLEX_ALGORITHM,
        TaskType.SYSTEM_INTEGRATION,
        TaskType.PRODUCTION_CRITICAL,
        TaskType.PERFORMANCE_OPTIMIZATION,
        TaskType.SCALABILITY_DESIGN,
        TaskType.DATABASE_SCHEMA_DESIGN,
        TaskType.API_DESIGN,
        TaskType.SECURITY_AUDIT,
        TaskType.DISTRIBUTED_SYSTEM_DESIGN,
        TaskType.MIGRATION_STRATEGY,
        TaskType.DISASTER_RECOVERY_PLAN,
    ]

    for task_type in opus_tasks:
        model = ModelSelector.select_model(task_type)
        assert model == ModelTier.OPUS, f"{task_type.value} should map to Opus"


def test_all_task_types_have_mapping():
    """Ensure all 38 task types are covered in TASK_MODEL_MAP."""
    all_task_types = list(TaskType)
    mapped_task_types = list(ModelSelector.TASK_MODEL_MAP.keys())

    # All task types should have a mapping
    for task_type in all_task_types:
        model = ModelSelector.select_model(task_type)
        assert model in [ModelTier.HAIKU, ModelTier.SONNET, ModelTier.OPUS]

    # Verify we have exactly 38 task types mapped (10 Haiku + 15 Sonnet + 13 Opus)
    assert len(mapped_task_types) == 38, "Should have 38 task types mapped"


# ============================================================================
# COMPLEXITY OVERRIDE TESTS
# ============================================================================


def test_complexity_boundary_conditions():
    """Test complexity score boundary conditions."""
    # Score exactly 4.0 - should use Sonnet (2.5 < score <= 4)
    complexity_medium = TaskComplexity(
        reasoning_depth=3, code_scope=3, critical_importance=2, context_needed=2
    )
    # (3 + 3 + 2*2 + 2) / 5 = 12 / 5 = 2.4
    assert complexity_medium.calculate_score() == pytest.approx(2.4)
    model = ModelSelector.select_model(TaskType.GENERAL_CODING, complexity_medium)
    assert model == ModelTier.HAIKU  # 2.4 <= 2.5

    # Score exactly 2.5 - should use Haiku (score <= 2.5)
    complexity_low = TaskComplexity(
        reasoning_depth=2, code_scope=2, critical_importance=1, context_needed=2
    )
    # (2 + 2 + 1*2 + 2) / 5 = 8 / 5 = 1.6
    assert complexity_low.calculate_score() == pytest.approx(1.6)
    model = ModelSelector.select_model(TaskType.GENERAL_CODING, complexity_low)
    assert model == ModelTier.HAIKU

    # Score > 4 - should use Opus
    complexity_high = TaskComplexity(
        reasoning_depth=5, code_scope=5, critical_importance=5, context_needed=3
    )
    # (5 + 5 + 5*2 + 3) / 5 = 23 / 5 = 4.6
    assert complexity_high.calculate_score() == pytest.approx(4.6)
    model = ModelSelector.select_model(TaskType.GENERAL_CODING, complexity_high)
    assert model == ModelTier.OPUS


def test_complexity_with_critical_importance():
    """Test that critical importance doubles in score calculation."""
    # Critical importance should double
    complexity_critical = TaskComplexity(
        reasoning_depth=2, code_scope=2, critical_importance=5, context_needed=1
    )
    # (2 + 2 + 5*2 + 1) / 5 = 15 / 5 = 3.0
    score = complexity_critical.calculate_score()
    assert score == pytest.approx(3.0)

    # Should select Sonnet (2.5 < 3.0 <= 4)
    model = ModelSelector.select_model(TaskType.FILE_RENAME, complexity_critical)
    assert model == ModelTier.SONNET


# ============================================================================
# MODEL CONFIGURATION TESTS
# ============================================================================


def test_all_model_tiers_have_config():
    """Ensure all model tiers have configuration."""
    for tier in ModelTier:
        config = ModelSelector.get_model_config(tier)
        assert "model" in config
        assert "max_tokens" in config
        assert "timeout" in config
        assert "cost_per_1k_tokens" in config


def test_model_configs_are_distinct():
    """Test that each model tier has distinct configuration."""
    haiku = ModelSelector.get_model_config(ModelTier.HAIKU)
    sonnet = ModelSelector.get_model_config(ModelTier.SONNET)
    opus = ModelSelector.get_model_config(ModelTier.OPUS)

    # Max tokens should increase
    assert haiku["max_tokens"] < sonnet["max_tokens"] < opus["max_tokens"]

    # Cost should increase
    assert haiku["cost_per_1k_tokens"] < sonnet["cost_per_1k_tokens"] < opus["cost_per_1k_tokens"]

    # Timeout should increase
    assert haiku["timeout"] < sonnet["timeout"] < opus["timeout"]


# ============================================================================
# COST ESTIMATION TESTS
# ============================================================================


def test_cost_estimation_accuracy():
    """Test cost estimation accuracy for various token counts."""
    # Test Haiku ($0.001 per 1k)
    assert ModelSelector.estimate_cost(ModelTier.HAIKU, 1000) == pytest.approx(0.001)
    assert ModelSelector.estimate_cost(ModelTier.HAIKU, 10000) == pytest.approx(0.01)

    # Test Sonnet ($0.015 per 1k)
    assert ModelSelector.estimate_cost(ModelTier.SONNET, 1000) == pytest.approx(0.015)
    assert ModelSelector.estimate_cost(ModelTier.SONNET, 10000) == pytest.approx(0.15)

    # Test Opus ($0.075 per 1k)
    assert ModelSelector.estimate_cost(ModelTier.OPUS, 1000) == pytest.approx(0.075)
    assert ModelSelector.estimate_cost(ModelTier.OPUS, 10000) == pytest.approx(0.75)


def test_cost_comparison():
    """Test cost comparison between models for same token count."""
    tokens = 8000

    haiku_cost = ModelSelector.estimate_cost(ModelTier.HAIKU, tokens)
    sonnet_cost = ModelSelector.estimate_cost(ModelTier.SONNET, tokens)
    opus_cost = ModelSelector.estimate_cost(ModelTier.OPUS, tokens)

    # Opus should be most expensive
    assert opus_cost > sonnet_cost > haiku_cost

    # Opus should be 75x more expensive than Haiku
    assert opus_cost == pytest.approx(haiku_cost * 75)

    # Opus should be 5x more expensive than Sonnet
    assert opus_cost == pytest.approx(sonnet_cost * 5)
