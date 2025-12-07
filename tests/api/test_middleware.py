"""Tests for API middleware."""

import pytest

pytest.importorskip("litestar")

from litestar.status_codes import HTTP_200_OK, HTTP_403_FORBIDDEN
from litestar.testing import TestClient

from iccc.api.app import create_app


class TestErrorHandling:
    """Tests for error handling middleware."""

    def test_not_found_error(self):
        """Test 404 error handling."""
        app = create_app(enable_auth=False)
        with TestClient(app=app) as client:
            response = client.get("/nonexistent")

            assert response.status_code == 404
            # Litestar handles 404 differently, may not use custom error handler

    def test_validation_error(self):
        """Test validation error handling."""
        app = create_app(enable_auth=False)
        with TestClient(app=app) as client:
            # Send invalid data (missing required fields)
            response = client.post("/projects/", json={})

            assert response.status_code == 400 or response.status_code == 422


class TestAuthentication:
    """Tests for API key authentication."""

    def test_auth_required(self):
        """Test that auth middleware requires API key."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            # Request without API key should fail
            response = client.get("/projects/")

            assert response.status_code == HTTP_403_FORBIDDEN

    def test_auth_with_valid_key(self):
        """Test that valid API key allows access."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            # Request with valid API key should succeed
            response = client.get(
                "/projects/",
                headers={"X-API-Key": "dev-key-12345"},
            )

            # May fail if DB not initialized, but should pass auth
            assert response.status_code != HTTP_403_FORBIDDEN

    def test_auth_with_invalid_key(self):
        """Test that invalid API key is rejected."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            response = client.get(
                "/projects/",
                headers={"X-API-Key": "invalid-key"},
            )

            assert response.status_code == HTTP_403_FORBIDDEN

    def test_health_check_no_auth(self):
        """Test that health check doesn't require auth."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            response = client.get("/")

            assert response.status_code == HTTP_200_OK
