"""Hook performance monitoring and metrics collection."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from iccc.hooks.executor import HookExecutionResult


@dataclass
class HookMetrics:
    """Metrics for a specific hook."""

    hook_name: str
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_time_ms: float = 0
    min_time_ms: float = float("inf")
    max_time_ms: float = 0
    avg_time_ms: float = 0
    p95_time_ms: float = 0
    p99_time_ms: float = 0
    timeout_count: int = 0
    retry_count: int = 0
    last_execution: Optional[datetime] = None
    execution_times: list[float] = field(default_factory=list)

    def update(self, result: HookExecutionResult) -> None:
        """Update metrics with a new execution result."""
        self.total_executions += 1
        self.last_execution = datetime.now()

        if result.success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1

        if result.timed_out:
            self.timeout_count += 1

        self.retry_count += result.retry_count

        # Update timing stats
        exec_time = result.execution_time_ms
        self.total_time_ms += exec_time
        self.min_time_ms = min(self.min_time_ms, exec_time)
        self.max_time_ms = max(self.max_time_ms, exec_time)
        self.avg_time_ms = self.total_time_ms / self.total_executions

        # Track execution times for percentile calculation
        self.execution_times.append(exec_time)

        # Limit stored execution times to last 1000 for memory efficiency
        if len(self.execution_times) > 1000:
            self.execution_times = self.execution_times[-1000:]

        # Calculate percentiles
        self._calculate_percentiles()

    def _calculate_percentiles(self) -> None:
        """Calculate P95 and P99 percentiles."""
        if not self.execution_times:
            return

        sorted_times = sorted(self.execution_times)
        n = len(sorted_times)

        # P95
        p95_idx = int(n * 0.95)
        self.p95_time_ms = sorted_times[min(p95_idx, n - 1)]

        # P99
        p99_idx = int(n * 0.99)
        self.p99_time_ms = sorted_times[min(p99_idx, n - 1)]

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_executions == 0:
            return 0.0
        return (self.successful_executions / self.total_executions) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "hook_name": self.hook_name,
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": round(self.success_rate, 2),
            "total_time_ms": round(self.total_time_ms, 2),
            "min_time_ms": round(self.min_time_ms, 2),
            "max_time_ms": round(self.max_time_ms, 2),
            "avg_time_ms": round(self.avg_time_ms, 2),
            "p95_time_ms": round(self.p95_time_ms, 2),
            "p99_time_ms": round(self.p99_time_ms, 2),
            "timeout_count": self.timeout_count,
            "retry_count": self.retry_count,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
        }


class HookPerformanceMonitor:
    """
    Monitors and tracks hook performance metrics.

    Provides real-time performance tracking, alerting for slow hooks,
    and historical performance data.
    """

    def __init__(
        self,
        p95_threshold_ms: float = 100,
        p99_threshold_ms: float = 200,
        failure_rate_threshold: float = 10.0,
    ) -> None:
        """
        Initialize performance monitor.

        Args:
            p95_threshold_ms: Alert threshold for P95 latency
            p99_threshold_ms: Alert threshold for P99 latency
            failure_rate_threshold: Alert threshold for failure rate (%)
        """
        self.metrics: dict[str, HookMetrics] = {}
        self.p95_threshold_ms = p95_threshold_ms
        self.p99_threshold_ms = p99_threshold_ms
        self.failure_rate_threshold = failure_rate_threshold
        self.alerts: list[dict[str, Any]] = []

    def record_execution(self, result: HookExecutionResult) -> None:
        """
        Record a hook execution result.

        Args:
            result: Hook execution result
        """
        hook_name = result.hook_name

        if hook_name not in self.metrics:
            self.metrics[hook_name] = HookMetrics(hook_name=hook_name)

        self.metrics[hook_name].update(result)

        # Check for performance issues
        self._check_performance_alerts(hook_name)

    def record_batch_execution(self, results: list[HookExecutionResult]) -> None:
        """
        Record multiple hook execution results.

        Args:
            results: List of hook execution results
        """
        for result in results:
            self.record_execution(result)

    def _check_performance_alerts(self, hook_name: str) -> None:
        """Check if hook performance violates thresholds."""
        metrics = self.metrics[hook_name]

        # Check P95 latency
        if metrics.p95_time_ms > self.p95_threshold_ms:
            self._add_alert(
                hook_name=hook_name,
                alert_type="high_p95_latency",
                message=f"P95 latency ({metrics.p95_time_ms:.2f}ms) exceeds threshold ({self.p95_threshold_ms}ms)",
                severity="warning",
            )

        # Check P99 latency
        if metrics.p99_time_ms > self.p99_threshold_ms:
            self._add_alert(
                hook_name=hook_name,
                alert_type="high_p99_latency",
                message=f"P99 latency ({metrics.p99_time_ms:.2f}ms) exceeds threshold ({self.p99_threshold_ms}ms)",
                severity="warning",
            )

        # Check failure rate
        if metrics.success_rate < (100 - self.failure_rate_threshold):
            self._add_alert(
                hook_name=hook_name,
                alert_type="high_failure_rate",
                message=f"Failure rate ({100 - metrics.success_rate:.2f}%) exceeds threshold ({self.failure_rate_threshold}%)",
                severity="error",
            )

    def _add_alert(
        self, hook_name: str, alert_type: str, message: str, severity: str
    ) -> None:
        """Add a performance alert."""
        alert = {
            "timestamp": datetime.now().isoformat(),
            "hook_name": hook_name,
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
        }
        self.alerts.append(alert)

        # Keep only last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]

    def get_hook_metrics(self, hook_name: str) -> Optional[dict[str, Any]]:
        """Get metrics for a specific hook."""
        if hook_name in self.metrics:
            return self.metrics[hook_name].to_dict()
        return None

    def get_all_metrics(self) -> list[dict[str, Any]]:
        """Get metrics for all hooks."""
        return [metrics.to_dict() for metrics in self.metrics.values()]

    def get_alerts(
        self, severity: Optional[str] = None, last_n: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """
        Get performance alerts.

        Args:
            severity: Filter by severity (error, warning)
            last_n: Return only last N alerts

        Returns:
            List of alerts
        """
        alerts = self.alerts

        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]

        if last_n:
            alerts = alerts[-last_n:]

        return alerts

    def get_summary(self) -> dict[str, Any]:
        """Get overall performance summary."""
        if not self.metrics:
            return {
                "total_hooks": 0,
                "total_executions": 0,
                "overall_success_rate": 0.0,
                "total_alerts": 0,
            }

        total_executions = sum(m.total_executions for m in self.metrics.values())
        total_successes = sum(m.successful_executions for m in self.metrics.values())
        success_rate = (total_successes / total_executions * 100) if total_executions > 0 else 0

        # Find slowest hooks
        slowest_hooks = sorted(
            self.metrics.values(), key=lambda m: m.p95_time_ms, reverse=True
        )[:5]

        # Find hooks with most failures
        failing_hooks = sorted(
            self.metrics.values(),
            key=lambda m: m.failed_executions,
            reverse=True,
        )[:5]

        return {
            "total_hooks": len(self.metrics),
            "total_executions": total_executions,
            "overall_success_rate": round(success_rate, 2),
            "total_alerts": len(self.alerts),
            "slowest_hooks": [
                {"name": h.hook_name, "p95_ms": round(h.p95_time_ms, 2)}
                for h in slowest_hooks
            ],
            "failing_hooks": [
                {
                    "name": h.hook_name,
                    "failures": h.failed_executions,
                    "success_rate": round(h.success_rate, 2),
                }
                for h in failing_hooks
            ],
        }

    def reset_metrics(self) -> None:
        """Reset all metrics (useful for testing)."""
        self.metrics.clear()
        self.alerts.clear()

    def export_metrics(self) -> dict[str, Any]:
        """Export all metrics and alerts for persistence."""
        return {
            "metrics": self.get_all_metrics(),
            "alerts": self.alerts,
            "summary": self.get_summary(),
            "exported_at": datetime.now().isoformat(),
        }
