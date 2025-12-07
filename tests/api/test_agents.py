"""Tests for agent API endpoints."""

import pytest

pytest.importorskip("litestar")

from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from litestar.testing import TestClient

from iccc.api.app import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app(enable_auth=False)
    with TestClient(app=app) as client:
        yield client


class TestAgentEndpoints:
    """Tests for agent management endpoints."""

    def test_register_agent(self, client):
        """Test registering a new agent."""
        agent_data = {
            "agent_id": "agent-001",
            "agent_type": "worker",
            "model": "sonnet",
            "specialization": "frontend",
            "worktree_path": "/tmp/worktree-001",
            "metadata": {"key": "value"},
        }

        response = client.post("/agents/", json=agent_data)

        assert response.status_code == HTTP_201_CREATED
        data = response.json()
        assert data["agent_id"] == "agent-001"
        assert data["agent_type"] == "worker"
        assert "id" in data

    def test_list_agents(self, client):
        """Test listing agents."""
        # Register an agent first
        client.post(
            "/agents/",
            json={
                "agent_id": "agent-002",
                "agent_type": "worker",
                "model": "haiku",
            },
        )

        # List agents
        response = client.get("/agents/")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)

    def test_filter_agents_by_type(self, client):
        """Test filtering agents by type."""
        # Register agents of different types
        client.post(
            "/agents/",
            json={
                "agent_id": "master-001",
                "agent_type": "master",
                "model": "opus",
            },
        )

        # Filter by type
        response = client.get("/agents/?agent_type=master")

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert all(a["agent_type"] == "master" for a in data)

    def test_update_agent_status(self, client):
        """Test updating agent status."""
        # Register an agent
        create_response = client.post(
            "/agents/",
            json={
                "agent_id": "agent-003",
                "agent_type": "worker",
                "model": "sonnet",
            },
        )
        agent_id = create_response.json()["id"]

        # Update status
        update_data = {"status": "busy"}
        response = client.put(f"/agents/{agent_id}", json=update_data)

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["status"] == "busy"
