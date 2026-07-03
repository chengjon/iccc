"""Unit tests for Role mapping logic."""

import pytest
from uuid import uuid4
from iccc.orchestrator import Orchestrator
from iccc.models.entities import TaskType, RoleType

class TestRoleLogic:
    """Test Role Mapping Logic in Orchestrator."""
    
    @pytest.fixture
    def orchestrator(self, tmp_path):
        """Create a minimal orchestrator."""
        return Orchestrator(
            project_id=uuid4(),
            project_dir=str(tmp_path)
        )

    def test_manager_tasks(self, orchestrator):
        """Test tasks that should be assigned to MANAGER."""
        manager_types = [
            TaskType.CODE_REVIEW,
            TaskType.ARCHITECTURE_DESIGN,
            TaskType.SECURITY_AUDIT
        ]
        
        for t_type in manager_types:
            role = orchestrator._get_role_for_task_type(t_type)
            assert role == RoleType.MANAGER, f"{t_type} should be assigned to MANAGER"

    def test_worker_tasks(self, orchestrator):
        """Test tasks that should be assigned to WORKER."""
        worker_types = [
            TaskType.GENERAL_CODING,
            TaskType.FEATURE_IMPLEMENTATION,
            TaskType.BUG_FIX,
            TaskType.CODE_REFACTOR  # REFACTORING -> CODE_REFACTOR
        ]
        
        for t_type in worker_types:
            role = orchestrator._get_role_for_task_type(t_type)
            assert role == RoleType.WORKER, f"{t_type} should be assigned to WORKER"

    def test_fallback_logic(self, orchestrator):
        """Test that unknown/default types fall back to WORKER."""
        # Assuming any type not explicitly in the MANAGER list falls to WORKER
        # Let's check a few others
        role = orchestrator._get_role_for_task_type(TaskType.DOCUMENTATION_DETAILED)
        assert role == RoleType.WORKER
