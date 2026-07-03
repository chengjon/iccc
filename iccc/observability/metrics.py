"""Prometheus metrics collection for iCCC observability."""

import logging
import time
from typing import ClassVar

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Summary,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    CollectorRegistry = object
    generate_latest = None
    CONTENT_TYPE_LATEST = None

from iccc.config import get_config

logger = logging.getLogger(__name__)


class PrometheusCollector:
    """Prometheus metrics collector for iCCC system."""

    _instance: ClassVar["PrometheusCollector | None"] = None

    def __new__(cls) -> "PrometheusCollector":
        """Singleton pattern for metrics collector."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialize Prometheus metrics."""
        if not PROMETHEUS_AVAILABLE:
            logger.warning(
                "prometheus_client not installed. Install with: "
                "pip install prometheus_client"
            )
            return

        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._registry = CollectorRegistry()

        # HTTP Request Metrics
        self._init_http_metrics()

        # Business Metrics
        self._init_business_metrics()

        # System Metrics
        self._init_system_metrics()

        # Database Metrics
        self._init_database_metrics()

        logger.info("Prometheus metrics collector initialized")

    def _init_http_metrics(self) -> None:
        """Initialize HTTP request metrics."""
        # Request count by method, route, and status
        self.http_requests_total = Counter(
            "iccc_http_requests_total",
            "Total HTTP requests",
            ["method", "route", "status_code", "agent_id"],
            registry=self._registry
        )

        # Request duration histogram
        self.http_request_duration_seconds = Histogram(
            "iccc_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "route", "status_code", "agent_id"],
            buckets=[
                0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5,
                1.0, 2.5, 5.0, 10.0, float("inf")
            ],
            registry=self._registry
        )

        # Request size in bytes
        self.http_request_size_bytes = Summary(
            "iccc_http_request_size_bytes",
            "HTTP request size in bytes",
            ["method", "route"],
            registry=self._registry
        )

        # Response size in bytes
        self.http_response_size_bytes = Summary(
            "iccc_http_response_size_bytes",
            "HTTP response size in bytes",
            ["method", "route", "status_code"],
            registry=self._registry
        )

    def _init_business_metrics(self) -> None:
        """Initialize business metrics."""
        # Active agents by status
        self.agents_active = Gauge(
            "iccc_agents_active",
            "Number of active agents by status",
            ["status"],
            registry=self._registry
        )

        # Tasks by status
        self.tasks_total = Gauge(
            "iccc_tasks_total",
            "Total tasks by status",
            ["status"],
            registry=self._registry
        )

        # Task duration histogram
        self.task_duration_seconds = Histogram(
            "iccc_task_duration_seconds",
            "Task execution duration in seconds",
            ["task_type", "agent_type", "status"],
            buckets=[
                1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0, 1800.0,
                3600.0, 7200.0, float("inf")
            ],
            registry=self._registry
        )

        # Projects by status
        self.projects_total = Gauge(
            "iccc_projects_total",
            "Total projects by status",
            ["status"],
            registry=self._registry
        )

        # Quality gate results
        self.quality_gate_results = Counter(
            "iccc_quality_gate_results_total",
            "Quality gate results",
            ["gate_type", "result"],
            registry=self._registry
        )

        # Planning operations
        self.planning_operations = Counter(
            "iccc_planning_operations_total",
            "Planning operations",
            ["operation_type", "planner", "result"],
            registry=self._registry
        )

        # Hook events
        self.hook_events = Counter(
            "iccc_hook_events_total",
            "Hook events",
            ["hook_type", "event_type"],
            registry=self._registry
        )

    def _init_system_metrics(self) -> None:
        """Initialize system metrics."""
        # System health status
        self.system_healthy = Gauge(
            "iccc_system_healthy",
            "System health status (1 = healthy, 0 = unhealthy)",
            ["component"],
            registry=self._registry
        )

        # Redis connection status
        self.redis_connected = Gauge(
            "iccc_redis_connected",
            "Redis connection status (1 = connected, 0 = disconnected)",
            registry=self._registry
        )

        # MongoDB connection status
        self.mongodb_connected = Gauge(
            "iccc_mongodb_connected",
            "MongoDB connection status (1 = connected, 0 = disconnected)",
            registry=self._registry
        )

        # Active sessions
        self.active_sessions = Gauge(
            "iccc_active_sessions",
            "Number of active sessions",
            ["agent_id"],
            registry=self._registry
        )

        # Token usage
        self.token_usage = Counter(
            "iccc_token_usage_total",
            "Token usage by model",
            ["model", "agent_id", "operation"],
            registry=self._registry
        )

        # File lock status
        self.file_locks_active = Gauge(
            "iccc_file_locks_active",
            "Number of active file locks",
            registry=self._registry
        )

    def _init_database_metrics(self) -> None:
        """Initialize database operation metrics."""
        # Database operation counts
        self.db_operations_total = Counter(
            "iccc_db_operations_total",
            "Database operations",
            ["operation", "collection", "status"],
            registry=self._registry
        )

        # Database operation duration
        self.db_operation_duration_seconds = Histogram(
            "iccc_db_operation_duration_seconds",
            "Database operation duration in seconds",
            ["operation", "collection"],
            buckets=[
                0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5,
                1.0, 2.5, 5.0, 10.0, float("inf")
            ],
            registry=self._registry
        )

    def record_http_request(
        self,
        method: str,
        route: str,
        status_code: int,
        duration: float,
        request_size: int = 0,
        response_size: int = 0,
        agent_id: str = "anonymous",
    ) -> None:
        """Record HTTP request metrics."""
        if not PROMETHEUS_AVAILABLE:
            return

        status_str = str(status_code)

        self.http_requests_total.labels(
            method=method,
            route=route,
            status_code=status_str,
            agent_id=agent_id
        ).inc()

        self.http_request_duration_seconds.labels(
            method=method,
            route=route,
            status_code=status_str,
            agent_id=agent_id
        ).observe(duration)

        if request_size > 0:
            self.http_request_size_bytes.labels(
                method=method,
                route=route
            ).observe(request_size)

        if response_size > 0:
            self.http_response_size_bytes.labels(
                method=method,
                route=route,
                status_code=status_str
            ).observe(response_size)

    def update_agent_status(self, status: str, count: int) -> None:
        """Update agent status gauge."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.agents_active.labels(status=status).set(count)

    def update_task_status(self, status: str, count: int) -> None:
        """Update task status gauge."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.tasks_total.labels(status=status).set(count)

    def update_project_status(self, status: str, count: int) -> None:
        """Update project status gauge."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.projects_total.labels(status=status).set(count)

    def record_task_duration(
        self,
        task_type: str,
        agent_type: str,
        status: str,
        duration: float,
    ) -> None:
        """Record task completion duration."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.task_duration_seconds.labels(
            task_type=task_type,
            agent_type=agent_type,
            status=status
        ).observe(duration)

    def record_quality_gate(self, gate_type: str, result: str) -> None:
        """Record quality gate result."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.quality_gate_results.labels(gate_type=gate_type, result=result).inc()

    def record_planning_operation(self, operation_type: str, planner: str, result: str) -> None:
        """Record planning operation."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.planning_operations.labels(
            operation_type=operation_type,
            planner=planner,
            result=result
        ).inc()

    def record_hook_event(self, hook_type: str, event_type: str) -> None:
        """Record hook event."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.hook_events.labels(hook_type=hook_type, event_type=event_type).inc()

    def update_system_health(self, component: str, healthy: bool) -> None:
        """Update system health status."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.system_healthy.labels(component=component).set(1 if healthy else 0)

    def update_redis_status(self, connected: bool) -> None:
        """Update Redis connection status."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.redis_connected.set(1 if connected else 0)

    def update_mongodb_status(self, connected: bool) -> None:
        """Update MongoDB connection status."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.mongodb_connected.set(1 if connected else 0)

    def update_active_sessions(self, agent_id: str, count: int) -> None:
        """Update active sessions count."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.active_sessions.labels(agent_id=agent_id).set(count)

    def record_token_usage(self, model: str, agent_id: str, operation: str, count: int) -> None:
        """Record token usage."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.token_usage.labels(
            model=model,
            agent_id=agent_id,
            operation=operation
        ).inc(count)

    def update_file_locks(self, count: int) -> None:
        """Update active file locks count."""
        if not PROMETHEUS_AVAILABLE:
            return
        self.file_locks_active.set(count)

    def record_db_operation(
        self,
        operation: str,
        collection: str,
        status: str,
        duration: float | None = None,
    ) -> None:
        """Record database operation."""
        if not PROMETHEUS_AVAILABLE:
            return

        self.db_operations_total.labels(
            operation=operation,
            collection=collection,
            status=status
        ).inc()

        if duration is not None:
            self.db_operation_duration_seconds.labels(
                operation=operation,
                collection=collection
            ).observe(duration)

    def generate_metrics(self) -> bytes:
        """Generate Prometheus metrics output."""
        if not PROMETHEUS_AVAILABLE:
            return b"# prometheus_client not installed\n"
        return generate_latest(self._registry)

    @property
    def content_type(self) -> str:
        """Get content type for metrics endpoint."""
        return CONTENT_TYPE_LATEST or "text/plain"


# Global metrics collector instance
_metrics: PrometheusCollector | None = None


def get_metrics() -> PrometheusCollector:
    """Get the global metrics collector instance."""
    global _metrics
    if _metrics is None:
        _metrics = PrometheusCollector()
    return _metrics


def is_metrics_enabled() -> bool:
    """Check if metrics collection is enabled."""
    try:
        config = get_config()
        return config.observability.enable_metrics if hasattr(config, "observability") else True
    except Exception:
        return True