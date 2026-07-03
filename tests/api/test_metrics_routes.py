"""Tests for metrics API routes."""

import json
from unittest.mock import MagicMock, patch

import pytest
from litestar.testing import TestClient

from iccc.api.app import create_app
from iccc.observability import get_metrics, is_metrics_enabled


class TestMetricsRoutes:
    """Test suite for metrics endpoints."""

    @pytest.fixture
    def app(self) -> TestClient:
        """Create test client with metrics enabled."""
        return TestClient(
            create_app(
                enable_auth=False,
                enable_rate_limit=False,
                enable_metrics=True,
                enable_logging=False,
                enable_performance=False,
            )
        )

    @pytest.fixture
    def app_metrics_disabled(self) -> TestClient:
        """Create test client with metrics disabled."""
        return TestClient(
            create_app(
                enable_auth=False,
                enable_rate_limit=False,
                enable_metrics=False,
                enable_logging=False,
                enable_performance=False,
            )
        )

    def test_metrics_endpoint_returns_prometheus_format(self, app: TestClient) -> None:
        """Test that /metrics endpoint returns Prometheus-formatted data."""
        response = app.get("/metrics/")

        assert response.status_code == 200

        # Check that response contains metric definitions
        metrics_text = response.text
        assert "# HELP" in metrics_text
        assert "# TYPE" in metrics_text
        assert "iccc_" in metrics_text  # Our metric namespace

    def test_metrics_endpoint_includes_http_metrics(self, app: TestClient) -> None:
        """Test that HTTP request metrics are tracked."""
        # Make some requests to generate metrics
        app.get("/")
        app.get("/projects")
        app.post("/projects", json={"name": "test", "directory": "/tmp"})

        # Get metrics
        response = app.get("/metrics/")

        assert response.status_code == 200

        metrics_text = response.text
        # Check for HTTP request metrics
        assert "iccc_http_requests_total" in metrics_text
        assert "iccc_http_request_duration_seconds" in metrics_text

    def test_metrics_endpoint_when_disabled(self, app_metrics_disabled: TestClient) -> None:
        """Test metrics endpoint behavior when metrics are disabled."""
        response = app_metrics_disabled.get("/metrics/")

        assert response.status_code == 503
        assert "# Metrics collection is disabled" in response.text

    def test_metrics_health_endpoint(self, app: TestClient) -> None:
        """Test /metrics/health endpoint."""
        response = app.get("/metrics/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["metrics_enabled"] is True
        assert data["prometheus_available"] is True

    def test_metrics_health_endpoint_when_disabled(self, app_metrics_disabled: TestClient) -> None:
        """Test /metrics/health endpoint when metrics disabled."""
        response = app_metrics_disabled.get("/metrics/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "disabled"
        assert data["metrics_enabled"] is False
        assert data["prometheus_available"] is True

    @patch("iccc.observability.metrics.get_metrics")
    def test_metrics_endpoint_handles_exception(self, mock_get_metrics: MagicMock) -> None:
        """Test that metrics endpoint handles exceptions gracefully."""
        mock_get_metrics.side_effect = Exception("Test error")

        app = TestClient(
            create_app(
                enable_auth=False,
                enable_rate_limit=False,
                enable_metrics=True,
                enable_logging=False,
                enable_performance=False,
            )
        )

        response = app.get("/metrics/")

        assert response.status_code == 500
        assert "# Failed to generate metrics" in response.text

    def test_metrics_middleware_tracks_requests(self, app: TestClient) -> None:
        """Test that metrics middleware tracks HTTP requests."""
        # Make a request
        response = app.get("/")
        assert response.status_code == 200

        # Get metrics to verify tracking
        metrics_response = app.get("/metrics/")
        metrics_text = metrics_response.text

        # Should have tracked the request
        assert 'iccc_http_requests_total{method="GET",route="/",status_code="200"' in metrics_text
        assert 'iccc_http_request_duration_seconds' in metrics_text

    def test_metrics_middleware_tracks_different_methods(self, app: TestClient) -> None:
        """Test that metrics middleware tracks different HTTP methods."""
        # Make requests with different methods
        app.get("/")

        # POST request will likely fail validation but should still be tracked
        app.post("/projects", json={"name": "test", "directory": "/tmp"})

        # Get metrics
        metrics_response = app.get("/metrics/")
        metrics_text = metrics_response.text

        # Should have tracked both GET and POST requests
        assert 'method="GET"' in metrics_text
        assert 'method="POST"' in metrics_text

    def test_metrics_middleware_tracks_status_codes(self, app: TestClient) -> None:
        """Test that metrics middleware tracks different status codes."""
        # Make requests that return different status codes
        app.get("/")  # Should return 200
        app.get("/nonexistent")  # Should return 404

        # Get metrics
        metrics_response = app.get("/metrics/")
        metrics_text = metrics_response.text

        # Should have tracked both status codes
        assert 'status_code="200"' in metrics_text
        assert 'status_code="404"' in metrics_text

    def test_metrics_middleware_tracks_agent_id(self, app: TestClient) -> None:
        """Test that metrics middleware tracks agent ID from headers."""
        # Make request with agent ID header
        headers = {"x-agent-id": "test-agent-123"}
        app.get("/", headers=headers)

        # Get metrics
        metrics_response = app.get("/metrics/")
        metrics_text = metrics_response.text

        # Should have tracked the agent ID
        assert 'agent_id="test-agent-123"' in metrics_text

    @patch("iccc.observability.metrics.PROMETHEUS_AVAILABLE", False)
    def test_metrics_without_prometheus_client(self) -> None:
        """Test behavior when prometheus_client is not installed."""
        from iccc.observability.metrics import get_metrics, is_metrics_enabled

        # Should still be able to get metrics collector
        collector = get_metrics()
        assert collector is not None

        # Metrics should generate fallback content
        metrics_data = collector.generate_metrics()
        assert metrics_data == b"# prometheus_client not installed\n"

        # Content type should be text/plain
        assert collector.content_type == "text/plain"

    def test_metrics_collector_singleton() -> None:
        """Test that metrics collector is a singleton."""
        from iccc.observability.metrics import PrometheusCollector, get_metrics

        # Get multiple instances
        collector1 = get_metrics()
        collector2 = PrometheusCollector()

        # Should be the same instance
        assert collector1 is collector2
        assert isinstance(collector1, PrometheusCollector)

    def test_business_metrics_recording() -> None:
        """Test recording of business metrics."""
        from iccc.observability.metrics import get_metrics

        collector = get_metrics()

        # Test agent status updates
        collector.update_agent_status("idle", 5)
        collector.update_agent_status("busy", 3)

        # Test task status updates
        collector.update_task_status("pending", 10)
        collector.update_task_status("completed", 25)

        # Test project status updates
        collector.update_project_status("active", 8)
        collector.update_project_status("completed", 15)

        # Test task duration recording
        collector.record_task_duration("feature_development", "backend_expert", "completed", 120.5)

        # Test quality gate results
        collector.record_quality_gate("mypy", "passed")
        collector.record_quality_gate("test_coverage", "failed")

        # Test planning operations
        collector.record_planning_operation("decompose", "htn", "success")

        # Test hook events
        collector.record_hook_event("pre_tool_use", "file_lock_acquired")

        # Test system health
        collector.update_system_health("redis", True)
        collector.update_system_health("mongodb", False)

        # Test database status
        collector.update_redis_status(True)
        collector.update_mongodb_status(False)

        # Test active sessions
        collector.update_active_sessions("agent-1", 3)
        collector.update_active_sessions("agent-2", 1)

        # Test token usage
        collector.record_token_usage("claude-sonnet-4", "agent-1", "completion", 1000)

        # Test file locks
        collector.update_file_locks(5)

        # Test database operations
        collector.record_db_operation("find", "projects", "success", 0.025)
        collector.record_db_operation("insert", "tasks", "error")

        # Should not raise any exceptions
        assert True

    def test_metrics_with_disabled_collection() -> None:
        """Test that metrics methods handle disabled collection gracefully."""
        from unittest.mock import patch
        from iccc.observability.metrics import get_metrics

        # Mock is_metrics_enabled to return False
        with patch("iccc.observability.metrics.PROMETHEUS_AVAILABLE", False):
            collector = get_metrics()

            # All these should not raise exceptions
            collector.record_http_request("GET", "/", 200, 0.1)
            collector.update_agent_status("idle", 5)
            collector.update_task_status("pending", 10)
            collector.update_project_status("active", 8)
            collector.record_task_duration("feature", "backend", "completed", 100)
            collector.record_quality_gate("mypy", "passed")
            collector.record_planning_operation("decompose", "htn", "success")
            collector.record_hook_event("pre_tool_use", "lock")
            collector.update_system_health("redis", True)
            collector.update_redis_status(True)
            collector.update_mongodb_status(True)
            collector.update_active_sessions("agent-1", 2)
            collector.record_token_usage("sonnet", "agent-1", "completion", 100)
            collector.update_file_locks(3)
            collector.record_db_operation("find", "projects", "success", 0.01)

            # Should not raise any exceptions
            assert True

    def test_metrics_endpoint_performance(self, app: TestClient) -> None:
        """Test that metrics endpoint has acceptable performance."""
        import time

        # Generate some load
        for _ in range(10):
            app.get("/")

        # Time the metrics endpoint
        start_time = time.time()
        response = app.get("/metrics/")
        duration = time.time() - start_time

        assert response.status_code == 200
        # Should be fast (< 50ms)
        assert duration < 0.05, f"Metrics endpoint took {duration:.3f}s"

    def test_metrics_namespace_prefix(self, app: TestClient) -> None:
        """Test that all metrics have the correct namespace prefix."""
        response = app.get("/metrics/")
        metrics_text = response.text

        # Check for various metric types with namespace
        expected_metrics = [
            "iccc_http_requests_total",
            "iccc_http_request_duration_seconds",
            "iccc_agents_active",
            "iccc_tasks_total",
            "iccc_projects_total",
        ]

        for metric in expected_metrics:
            assert metric in metrics_text, f"Missing metric: {metric}"