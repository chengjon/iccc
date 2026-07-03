"""Tests for task API endpoints."""

import pytest

pytest.importorskip("litestar")

from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.testing import TestClient

from iccc.api.app import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app(enable_auth=False, enable_rate_limit=False)
    with TestClient(app=app) as client:
        yield client


@pytest.fixture
def project_id(client):
    """Create a test project and return its ID."""
    response = client.post(
        "/projects/",
        json={
            "name": "Test Project",
            "directory": "/tmp/test",
        },
    )
    return response.json()["id"]


class TestTaskEndpoints:
    """Tests for task management endpoints."""

    def test_create_task(self, client, project_id):
        """Test creating a new task."""
        task_data = {
            "project_id": project_id,
            "description": "Implement login feature",
            "task_type": "feature",
            "priority": 2,
            "metadata": {"complexity": "high"},
        }

        response = client.post("/tasks/", json=task_data)

        assert response.status_code == HTTP_201_CREATED
        data = response.json()
        assert data["description"] == "Implement login feature"
        assert data["task_type"] == "feature"
        assert data["priority"] == 2

    def test_list_tasks(self, client, project_id):
        """Test listing tasks."""
        # Create a task
        client.post(
            "/tasks/",
            json={
                "project_id": project_id,
                "description": "Fix bug",
                "task_type": "bug_fix",
            },
        )

        # List tasks
        response = client.get("/tasks/")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_filter_tasks_by_project(self, client, project_id):
        """Test filtering tasks by project."""
        # Create a task for the project
        client.post(
            "/tasks/",
            json={
                "project_id": project_id,
                "description": "Task 1",
                "task_type": "feature",
            },
        )

        # Filter by project
        response = client.get(f"/tasks/?project_id={project_id}")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert all(t["project_id"] == project_id for t in data)

    def test_update_task_status(self, client, project_id):
        """Test updating task status."""
        # Create a task
        create_response = client.post(
            "/tasks/",
            json={
                "project_id": project_id,
                "description": "Task to update",
                "task_type": "feature",
            },
        )
        task_id = create_response.json()["id"]

        # Update status
        update_data = {
            "status": "in_progress",
            "assigned_agent_id": "agent-001",
        }
        response = client.put(f"/tasks/{task_id}", json=update_data)

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["assigned_agent_id"] == "agent-001"
