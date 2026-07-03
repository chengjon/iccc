"""Metrics endpoint for Prometheus integration."""

import logging

from litestar import Controller, get

from iccc.observability import get_metrics, is_metrics_enabled

logger = logging.getLogger(__name__)


class MetricsController(Controller):
    """Controller for Prometheus metrics endpoints."""

    path = "/metrics"

    @get("/")
    async def get_metrics(self) -> str:
        """
        Get Prometheus metrics.

        Returns:
            Prometheus-formatted metrics text
        """
        if not is_metrics_enabled():
            logger.debug("Metrics collection is disabled")
            return "# Metrics collection is disabled\n"

        try:
            metrics_collector = get_metrics()
            metrics_data = metrics_collector.generate_metrics()
            return metrics_data.decode("utf-8")
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            return "# Failed to generate metrics\n"

    @get("/health")
    async def metrics_health(self) -> dict:
        """
        Health check for metrics endpoint.

        Returns:
            Health status information
        """
        return {
            "status": "healthy" if is_metrics_enabled() else "disabled",
            "metrics_enabled": is_metrics_enabled(),
            "prometheus_available": True
        }


# Create router instance
metrics_router = MetricsController