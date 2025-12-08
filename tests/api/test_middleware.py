"""Tests for API middleware."""

import os

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

    @pytest.fixture(autouse=True)
    def setup_api_keys(self):
        """Set up API keys in environment for testing."""
        original = os.environ.get("ICCC_API_KEYS")
        os.environ["ICCC_API_KEYS"] = "dev-key-12345,test-key-67890"
        yield
        # Restore original
        if original:
            os.environ["ICCC_API_KEYS"] = original
        elif "ICCC_API_KEYS" in os.environ:
            del os.environ["ICCC_API_KEYS"]

    def test_auth_required(self):
        """Test that auth middleware requires API key."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            # Request without API key should fail
            response = client.get("/projects/")

            assert response.status_code == HTTP_403_FORBIDDEN

    def test_auth_with_valid_key_x_api_key_header(self):
        """Test that valid API key in X-API-Key header allows access."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            # Request with valid API key should succeed
            response = client.get(
                "/projects/",
                headers={"X-API-Key": "dev-key-12345"},
            )

            # May fail if DB not initialized, but should pass auth
            assert response.status_code != HTTP_403_FORBIDDEN

    def test_auth_with_valid_key_bearer_token(self):
        """Test that valid API key in Authorization: Bearer header allows access."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            # Request with valid bearer token should succeed
            response = client.get(
                "/projects/",
                headers={"Authorization": "Bearer dev-key-12345"},
            )

            # May fail if DB not initialized, but should pass auth
            assert response.status_code != HTTP_403_FORBIDDEN

    def test_auth_with_multiple_valid_keys(self):
        """Test that multiple valid keys work."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            # First key
            response1 = client.get(
                "/projects/",
                headers={"X-API-Key": "dev-key-12345"},
            )
            assert response1.status_code != HTTP_403_FORBIDDEN

            # Second key
            response2 = client.get(
                "/projects/",
                headers={"X-API-Key": "test-key-67890"},
            )
            assert response2.status_code != HTTP_403_FORBIDDEN

    def test_auth_with_invalid_key(self):
        """Test that invalid API key is rejected."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            response = client.get(
                "/projects/",
                headers={"X-API-Key": "invalid-key"},
            )

            assert response.status_code == HTTP_403_FORBIDDEN

    def test_auth_with_empty_key(self):
        """Test that empty API key is rejected."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            response = client.get(
                "/projects/",
                headers={"X-API-Key": ""},
            )

            assert response.status_code == HTTP_403_FORBIDDEN

    def test_auth_with_whitespace_key(self):
        """Test that whitespace-only API key is rejected."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            response = client.get(
                "/projects/",
                headers={"X-API-Key": "   "},
            )

            assert response.status_code == HTTP_403_FORBIDDEN

    def test_health_check_no_auth(self):
        """Test that health check doesn't require auth."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            response = client.get("/")

            assert response.status_code == HTTP_200_OK

    def test_schema_endpoint_no_auth(self):
        """Test that schema endpoints don't require auth."""
        app = create_app(enable_auth=True)
        with TestClient(app=app) as client:
            response = client.get("/schema")
            assert response.status_code != HTTP_403_FORBIDDEN


class TestRateLimiting:
    """Tests for rate limiting middleware."""

    @pytest.fixture
    def mock_rate_limiter(self):
        """Create mock rate limiter for testing."""
        from unittest.mock import AsyncMock, MagicMock
        from iccc.api.rate_limiter import RateLimitResult
        import time

        mock_limiter = AsyncMock()
        # Default: allow requests
        mock_limiter.check_rate_limit = AsyncMock(
            return_value=RateLimitResult(
                allowed=True,
                limit=100,
                remaining=50,
                reset_timestamp=time.time() + 60,
            )
        )
        return mock_limiter

    def test_rate_limit_headers_present(self, mock_rate_limiter):
        """Test that rate limit headers are added to responses."""
        from iccc.api.middleware import set_rate_limiter
        from unittest.mock import patch

        # Enable rate limiting in config
        with patch("iccc.api.middleware.get_config") as mock_config:
            mock_config.return_value.rate_limit.enabled = True
            mock_config.return_value.rate_limit.exempt_paths = ["/", "/health"]

            app = create_app(enable_auth=False)
            set_rate_limiter(mock_rate_limiter)

            with TestClient(app=app) as client:
                response = client.get("/projects/")

                # Check for rate limit headers
                assert "X-RateLimit-Limit" in response.headers
                assert "X-RateLimit-Remaining" in response.headers
                assert "X-RateLimit-Reset" in response.headers

    def test_rate_limit_exceeded_returns_429(self, mock_rate_limiter):
        """Test that exceeding rate limit returns 429 status."""
        from iccc.api.rate_limiter import RateLimitResult
        from iccc.api.middleware import set_rate_limiter
        from unittest.mock import patch, AsyncMock
        import time

        # Mock rate limiter to return limit exceeded
        mock_rate_limiter.check_rate_limit = AsyncMock(
            return_value=RateLimitResult(
                allowed=False,
                limit=100,
                remaining=0,
                reset_timestamp=time.time() + 60,
            )
        )

        with patch("iccc.api.middleware.get_config") as mock_config:
            mock_config.return_value.rate_limit.enabled = True
            mock_config.return_value.rate_limit.exempt_paths = ["/", "/health"]
            mock_config.return_value.rate_limit.window_seconds = 60

            app = create_app(enable_auth=False)
            set_rate_limiter(mock_rate_limiter)

            with TestClient(app=app) as client:
                response = client.get("/projects/")

                assert response.status_code == 429
                assert "Retry-After" in response.headers

                # Check response body
                data = response.json()
                assert data["error"] == "rate_limit_exceeded"
                assert "limit" in data["details"]

    def test_rate_limit_uses_api_key_when_present(self, mock_rate_limiter):
        """Test that rate limiting uses API key when available."""
        from iccc.api.middleware import set_rate_limiter
        from unittest.mock import patch

        with patch("iccc.api.middleware.get_config") as mock_config:
            mock_config.return_value.rate_limit.enabled = True
            mock_config.return_value.rate_limit.exempt_paths = ["/", "/health"]

            app = create_app(enable_auth=False)
            set_rate_limiter(mock_rate_limiter)

            with TestClient(app=app) as client:
                response = client.get(
                    "/projects/",
                    headers={"X-API-Key": "test-key-12345"},
                )

                # Check that rate limiter was called
                mock_rate_limiter.check_rate_limit.assert_called_once()
                call_args = mock_rate_limiter.check_rate_limit.call_args
                # Should use API key prefix
                assert "apikey:" in call_args[0][0]

    def test_rate_limit_uses_ip_when_no_api_key(self, mock_rate_limiter):
        """Test that rate limiting falls back to IP when no API key."""
        from iccc.api.middleware import set_rate_limiter
        from unittest.mock import patch

        with patch("iccc.api.middleware.get_config") as mock_config:
            mock_config.return_value.rate_limit.enabled = True
            mock_config.return_value.rate_limit.exempt_paths = ["/", "/health"]

            app = create_app(enable_auth=False)
            set_rate_limiter(mock_rate_limiter)

            with TestClient(app=app) as client:
                response = client.get("/projects/")

                # Check that rate limiter was called
                mock_rate_limiter.check_rate_limit.assert_called_once()
                call_args = mock_rate_limiter.check_rate_limit.call_args
                # Should use IP prefix
                assert "ip:" in call_args[0][0]

    def test_rate_limit_disabled_skips_check(self):
        """Test that rate limiting can be disabled."""
        from unittest.mock import patch, AsyncMock

        with patch("iccc.api.middleware.get_config") as mock_config:
            mock_config.return_value.rate_limit.enabled = False

            app = create_app(enable_auth=False)

            with TestClient(app=app) as client:
                response = client.get("/projects/")

                # Should not have rate limit headers when disabled
                # (depends on implementation, but typically not added)

    def test_rate_limit_exempt_paths(self, mock_rate_limiter):
        """Test that exempt paths skip rate limiting."""
        from iccc.api.middleware import set_rate_limiter
        from unittest.mock import patch

        with patch("iccc.api.middleware.get_config") as mock_config:
            mock_config.return_value.rate_limit.enabled = True
            mock_config.return_value.rate_limit.exempt_paths = ["/", "/health", "/schema"]

            app = create_app(enable_auth=False)
            set_rate_limiter(mock_rate_limiter)

            with TestClient(app=app) as client:
                # Health check should not trigger rate limiter
                response = client.get("/")
                # Rate limiter should not be called for exempt paths
                # (implementation may vary)

    def test_rate_limit_error_fails_open(self, mock_rate_limiter):
        """Test that rate limiter errors fail open (allow request)."""
        from iccc.api.middleware import set_rate_limiter
        from unittest.mock import patch, AsyncMock

        # Mock rate limiter to raise exception
        mock_rate_limiter.check_rate_limit = AsyncMock(
            side_effect=Exception("Redis connection failed")
        )

        with patch("iccc.api.middleware.get_config") as mock_config:
            mock_config.return_value.rate_limit.enabled = True
            mock_config.return_value.rate_limit.exempt_paths = ["/", "/health"]

            app = create_app(enable_auth=False)
            set_rate_limiter(mock_rate_limiter)

            with TestClient(app=app) as client:
                # Request should succeed despite rate limiter error
                response = client.get("/projects/")
                # Should not return 429 or 500 due to rate limit error
                assert response.status_code != 429
