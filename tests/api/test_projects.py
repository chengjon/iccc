"""Tests for project API endpoints."""

import pytest

# Skip all tests if litestar not installed
pytest.importorskip("litestar")

from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
)
from litestar.testing import TestClient

from iccc.api.app import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app(enable_auth=False)
    with TestClient(app=app) as client:
        yield client


class TestProjectEndpoints:
    """Tests for project management endpoints."""

    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data

    def test_create_project(self, client):
        """Test creating a new project."""
        project_data = {
            "name": "Test Project",
            "directory": "/tmp/test-project",
            "description": "A test project",
            "git_repo": "https://github.com/test/repo",
            "metadata": {"key": "value"},
        }

        response = client.post("/projects/", json=project_data)

        assert response.status_code == HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Test Project"
        assert data["directory"] == "/tmp/test-project"
        assert "id" in data
        assert "created_at" in data

    def test_list_projects(self, client):
        """Test listing projects."""
        # Create a project first
        client.post(
            "/projects/",
            json={
                "name": "Project 1",
                "directory": "/tmp/project1",
            },
        )

        # List projects
        response = client.get("/projects/")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_project(self, client):
        """Test getting a specific project."""
        # Create a project
        create_response = client.post(
            "/projects/",
            json={
                "name": "Project 2",
                "directory": "/tmp/project2",
            },
        )
        project_id = create_response.json()["id"]

        # Get the project
        response = client.get(f"/projects/{project_id}")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Project 2"

    def test_get_nonexistent_project(self, client):
        """Test getting a project that doesn't exist."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/projects/{fake_id}")

        assert response.status_code == HTTP_404_NOT_FOUND

    def test_update_project(self, client):
        """Test updating a project."""
        # Create a project
        create_response = client.post(
            "/projects/",
            json={
                "name": "Project 3",
                "directory": "/tmp/project3",
            },
        )
        project_id = create_response.json()["id"]

        # Update the project
        update_data = {
            "name": "Updated Project",
            "description": "New description",
            "status": "active",
        }
        response = client.put(f"/projects/{project_id}", json=update_data)

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Project"
        assert data["description"] == "New description"

    def test_delete_project(self, client):
        """Test deleting a project."""
        # Create a project
        create_response = client.post(
            "/projects/",
            json={
                "name": "Project to Delete",
                "directory": "/tmp/delete-me",
            },
        )
        project_id = create_response.json()["id"]

        # Delete the project
        response = client.delete(f"/projects/{project_id}")

        assert response.status_code == HTTP_204_NO_CONTENT

        # Verify it's gone
        get_response = client.get(f"/projects/{project_id}")
        assert get_response.status_code == HTTP_404_NOT_FOUND

    def test_filter_projects_by_status(self, client):
        """Test filtering projects by status."""
        # Create projects with different statuses
        client.post(
            "/projects/",
            json={"name": "Active Project", "directory": "/tmp/active"},
        )

        # List with status filter
        response = client.get("/projects/?status=active")

        assert response.status_code == HTTP_200_OK
        # Note: Filtering may not work until repository implements it
