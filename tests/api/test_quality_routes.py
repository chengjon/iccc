"""Tests for quality gate API endpoints."""

import pytest

# Skip all tests if litestar not installed
pytest.importorskip("litestar")

from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
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


@pytest.fixture
def test_project(client):
    """Create a test project for quality checks."""
    project_data = {
        "name": "Quality Test Project",
        "directory": "/opt/iflow/iccc",  # Use current project directory
        "description": "Project for testing quality gates",
    }

    response = client.post("/projects/", json=project_data)
    assert response.status_code == HTTP_201_CREATED
    return response.json()


class TestQualityGateEndpoints:
    """Tests for quality gate management endpoints."""

    def test_list_quality_gates(self, client):
        """Test listing available quality gates."""
        response = client.get("/quality/gates")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Check gate structure
        gate = data[0]
        assert "name" in gate
        assert "required" in gate
        assert "description" in gate

        # Check expected gates
        gate_names = {gate["name"] for gate in data}
        assert "Lint" in gate_names
        assert "Test" in gate_names

    def test_run_quality_check_all_gates(self, client, test_project):
        """Test running all quality gates for a project."""
        project_id = test_project["id"]

        check_data = {
            "project_id": project_id,
            "gate_names": None,  # Run all gates
            "task_id": None,
        }

        response = client.post("/quality/check", json=check_data)

        assert response.status_code == HTTP_201_CREATED
        data = response.json()

        # Validate response structure
        assert "id" in data
        assert data["project_id"] == project_id
        assert data["task_id"] is None
        assert "status" in data
        assert data["status"] in ["running", "passed", "failed"]
        assert "gate_results" in data
        assert isinstance(data["gate_results"], list)
        assert "passed" in data
        assert "created_at" in data
        assert "duration_seconds" in data

        # Validate gate results
        assert len(data["gate_results"]) > 0
        for gate_result in data["gate_results"]:
            assert "gate_name" in gate_result
            assert "status" in gate_result
            assert gate_result["status"] in ["passed", "failed", "skipped"]
            assert "message" in gate_result

    def test_run_quality_check_specific_gates(self, client, test_project):
        """Test running specific quality gates."""
        project_id = test_project["id"]

        check_data = {
            "project_id": project_id,
            "gate_names": ["Lint"],  # Only run lint gate
            "task_id": None,
        }

        response = client.post("/quality/check", json=check_data)

        assert response.status_code == HTTP_201_CREATED
        data = response.json()

        # Should only have one gate result
        assert len(data["gate_results"]) == 1
        assert data["gate_results"][0]["gate_name"] == "Lint"

    def test_run_quality_check_project_not_found(self, client):
        """Test running quality check for non-existent project."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        check_data = {
            "project_id": fake_id,
            "gate_names": None,
            "task_id": None,
        }

        response = client.post("/quality/check", json=check_data)

        assert response.status_code == HTTP_404_NOT_FOUND

    def test_get_quality_check_by_id(self, client, test_project):
        """Test retrieving quality check results by ID."""
        project_id = test_project["id"]

        # First, create a quality check
        check_data = {
            "project_id": project_id,
            "gate_names": ["Lint"],
            "task_id": None,
        }

        create_response = client.post("/quality/check", json=check_data)
        assert create_response.status_code == HTTP_201_CREATED
        check_id = create_response.json()["id"]

        # Now retrieve it
        response = client.get(f"/quality/check/{check_id}")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["id"] == check_id
        assert data["project_id"] == project_id

    def test_get_quality_check_not_found(self, client):
        """Test retrieving a non-existent quality check."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        response = client.get(f"/quality/check/{fake_id}")

        assert response.status_code == HTTP_404_NOT_FOUND

    def test_list_quality_checks(self, client, test_project):
        """Test listing quality checks for a project."""
        project_id = test_project["id"]

        # Create a few quality checks
        for i in range(3):
            check_data = {
                "project_id": project_id,
                "gate_names": ["Lint"],
                "task_id": None,
            }
            response = client.post("/quality/check", json=check_data)
            assert response.status_code == HTTP_201_CREATED

        # List checks for the project
        response = client.get(f"/quality/checks?project_id={project_id}")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3

    def test_list_quality_checks_with_status_filter(self, client, test_project):
        """Test listing quality checks filtered by status."""
        project_id = test_project["id"]

        # Create a quality check
        check_data = {
            "project_id": project_id,
            "gate_names": ["Lint"],
            "task_id": None,
        }
        create_response = client.post("/quality/check", json=check_data)
        assert create_response.status_code == HTTP_201_CREATED
        status = create_response.json()["status"]

        # List with status filter
        response = client.get(
            f"/quality/checks?project_id={project_id}&status={status}"
        )

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

        # All returned checks should have the filtered status
        for check in data:
            assert check["status"] == status

    def test_list_quality_checks_pagination(self, client, test_project):
        """Test pagination of quality check listings."""
        project_id = test_project["id"]

        # Create several quality checks
        for i in range(5):
            check_data = {
                "project_id": project_id,
                "gate_names": ["Lint"],
                "task_id": None,
            }
            client.post("/quality/check", json=check_data)

        # Test limit
        response = client.get(f"/quality/checks?project_id={project_id}&limit=2")
        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert len(data) <= 2

        # Test offset
        response = client.get(f"/quality/checks?project_id={project_id}&offset=2&limit=2")
        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert len(data) <= 2

    def test_list_quality_checks_no_project_id(self, client):
        """Test listing quality checks without project_id returns empty list."""
        response = client.get("/quality/checks")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_quality_check_with_task_id(self, client, test_project):
        """Test running quality check linked to a task."""
        project_id = test_project["id"]
        fake_task_id = "11111111-1111-1111-1111-111111111111"

        check_data = {
            "project_id": project_id,
            "gate_names": ["Lint"],
            "task_id": fake_task_id,
        }

        response = client.post("/quality/check", json=check_data)

        assert response.status_code == HTTP_201_CREATED
        data = response.json()
        assert data["task_id"] == fake_task_id

    def test_quality_check_duration_recorded(self, client, test_project):
        """Test that quality check duration is recorded."""
        project_id = test_project["id"]

        check_data = {
            "project_id": project_id,
            "gate_names": ["Lint"],
            "task_id": None,
        }

        response = client.post("/quality/check", json=check_data)

        assert response.status_code == HTTP_201_CREATED
        data = response.json()

        # Duration should be recorded
        assert "duration_seconds" in data
        assert data["duration_seconds"] is not None
        assert data["duration_seconds"] >= 0

    def test_quality_check_timestamps(self, client, test_project):
        """Test that quality check has proper timestamps."""
        project_id = test_project["id"]

        check_data = {
            "project_id": project_id,
            "gate_names": ["Lint"],
            "task_id": None,
        }

        response = client.post("/quality/check", json=check_data)

        assert response.status_code == HTTP_201_CREATED
        data = response.json()

        assert "created_at" in data
        assert data["created_at"] is not None
        assert "completed_at" in data
        # completed_at should be set after execution
        assert data["completed_at"] is not None
