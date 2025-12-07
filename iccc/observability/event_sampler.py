"""Event sampling for scalable observability."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from iccc.models.entities import HookEvent


# Default sampling rates by event type
# Higher rate = more events sampled (1.0 = 100%, 0.1 = 10%)
SAMPLING_RATES: dict[str, float] = {
    # Critical events - always sample
    "PreToolUse": 1.0,  # Security checks
    "Stop": 1.0,  # Agent stops
    "SubagentStop": 1.0,  # Subagent completions
    "Error": 1.0,  # Errors
    # High importance
    "PostToolUse": 0.8,  # Tool results
    "Notification": 0.5,  # Status updates
    # Lower importance (high volume)
    "Heartbeat": 0.1,  # Regular heartbeats
    "Progress": 0.3,  # Progress updates
    "Debug": 0.05,  # Debug messages
}

# Agent count scaling factors
AGENT_SCALING: dict[int, float] = {
    3: 1.0,  # 1-3 agents: full rate
    10: 0.7,  # 4-10 agents: 70% rate
    30: 0.4,  # 11-30 agents: 40% rate
    100: 0.2,  # 31-100 agents: 20% rate
}


@dataclass
class SamplerStats:
    """Statistics for sampling operations."""

    total_events: int = 0
    sampled_events: int = 0
    dropped_events: int = 0
    by_type: dict[str, tuple[int, int]] = field(default_factory=dict)  # (sampled, total)

    @property
    def overall_rate(self) -> float:
        """Calculate overall sampling rate achieved."""
        if self.total_events == 0:
            return 1.0
        return self.sampled_events / self.total_events


class EventSampler:
    """
    Intelligent event sampler for scalable observability.

    Features:
    - Configurable per-event-type sampling rates
    - Automatic scaling based on agent count
    - Priority-based sampling (critical events always pass)
    - Burst detection and handling
    - Statistics tracking
    """

    def __init__(
        self,
        sampling_rates: dict[str, float] | None = None,
        default_rate: float = 0.5,
        agent_count: int = 1,
        enable_burst_detection: bool = True,
        burst_threshold: int = 100,
        burst_window_seconds: int = 5,
    ) -> None:
        """
        Initialize the event sampler.

        Args:
            sampling_rates: Per-event-type sampling rates (0.0 to 1.0)
            default_rate: Default rate for unknown event types
            agent_count: Number of active agents (affects scaling)
            enable_burst_detection: Whether to detect and handle bursts
            burst_threshold: Events per window to trigger burst mode
            burst_window_seconds: Time window for burst detection
        """
        self.sampling_rates = sampling_rates or SAMPLING_RATES.copy()
        self.default_rate = default_rate
        self.agent_count = agent_count
        self.enable_burst_detection = enable_burst_detection
        self.burst_threshold = burst_threshold
        self.burst_window_seconds = burst_window_seconds

        # Burst detection state
        self._event_timestamps: list[datetime] = []
        self._in_burst_mode = False

        # Statistics
        self.stats = SamplerStats()

        # Calculate effective rates based on agent count
        self._effective_rates = self._calculate_effective_rates()

    def _calculate_effective_rates(self) -> dict[str, float]:
        """Calculate effective sampling rates based on agent count."""
        # Find scaling factor
        scale = 1.0
        for threshold, factor in sorted(AGENT_SCALING.items()):
            if self.agent_count <= threshold:
                scale = factor
                break
        else:
            scale = min(AGENT_SCALING.values())  # Use lowest for very high counts

        # Apply scaling to all rates
        return {
            event_type: min(1.0, rate * scale)
            for event_type, rate in self.sampling_rates.items()
        }

    def update_agent_count(self, count: int) -> None:
        """Update agent count and recalculate rates."""
        self.agent_count = count
        self._effective_rates = self._calculate_effective_rates()

    def should_sample(self, event: HookEvent) -> bool:
        """
        Decide if an event should be sampled.

        Args:
            event: The event to evaluate

        Returns:
            True if event should be sampled
        """
        self.stats.total_events += 1

        # Initialize type stats if needed
        event_type = event.event_type
        if event_type not in self.stats.by_type:
            self.stats.by_type[event_type] = (0, 0)

        # Update type total
        sampled, total = self.stats.by_type[event_type]
        self.stats.by_type[event_type] = (sampled, total + 1)

        # Check for critical events (always sample)
        if self._is_critical(event):
            self._record_sampled(event_type)
            return True

        # Check burst mode
        if self.enable_burst_detection:
            self._update_burst_state()
            if self._in_burst_mode:
                # In burst mode, apply additional 50% reduction
                rate = self._get_rate(event_type) * 0.5
            else:
                rate = self._get_rate(event_type)
        else:
            rate = self._get_rate(event_type)

        # Apply probabilistic sampling
        if random.random() < rate:
            self._record_sampled(event_type)
            return True

        self.stats.dropped_events += 1
        return False

    def _is_critical(self, event: HookEvent) -> bool:
        """Check if an event is critical and should always be sampled."""
        # Check data flags
        if event.data.get("critical", False):
            return True

        # Check for errors
        if event.data.get("error"):
            return True
        if event.data.get("status") == "failed":
            return True

        # Check event type
        if event.event_type in ("Error", "Stop", "SubagentStop"):
            return True

        return False

    def _get_rate(self, event_type: str) -> float:
        """Get effective sampling rate for an event type."""
        return self._effective_rates.get(event_type, self.default_rate)

    def _record_sampled(self, event_type: str) -> None:
        """Record that an event was sampled."""
        self.stats.sampled_events += 1
        sampled, total = self.stats.by_type.get(event_type, (0, 0))
        self.stats.by_type[event_type] = (sampled + 1, total)

        if self.enable_burst_detection:
            self._event_timestamps.append(datetime.now())

    def _update_burst_state(self) -> None:
        """Update burst detection state."""
        now = datetime.now()
        window_start = now - timedelta(seconds=self.burst_window_seconds)

        # Remove old timestamps
        self._event_timestamps = [
            ts for ts in self._event_timestamps if ts > window_start
        ]

        # Check if in burst
        self._in_burst_mode = len(self._event_timestamps) >= self.burst_threshold

    def set_rate(self, event_type: str, rate: float) -> None:
        """Set sampling rate for an event type."""
        self.sampling_rates[event_type] = max(0.0, min(1.0, rate))
        self._effective_rates = self._calculate_effective_rates()

    def get_stats(self) -> dict[str, Any]:
        """Get sampling statistics."""
        return {
            "total_events": self.stats.total_events,
            "sampled_events": self.stats.sampled_events,
            "dropped_events": self.stats.dropped_events,
            "overall_rate": f"{self.stats.overall_rate:.1%}",
            "agent_count": self.agent_count,
            "in_burst_mode": self._in_burst_mode,
            "by_type": {
                event_type: {
                    "sampled": sampled,
                    "total": total,
                    "rate": f"{sampled/total:.1%}" if total > 0 else "N/A",
                }
                for event_type, (sampled, total) in self.stats.by_type.items()
            },
        }

    def reset_stats(self) -> None:
        """Reset all statistics."""
        self.stats = SamplerStats()
        self._event_timestamps.clear()
        self._in_burst_mode = False


class AdaptiveSampler(EventSampler):
    """
    Adaptive sampler that automatically adjusts rates based on load.

    Monitors event throughput and adjusts sampling rates to maintain
    a target events-per-second rate for the dashboard.
    """

    def __init__(
        self,
        target_eps: float = 10.0,  # Target events per second
        adjustment_interval: int = 30,  # Seconds between adjustments
        **kwargs: Any,
    ) -> None:
        """
        Initialize adaptive sampler.

        Args:
            target_eps: Target events per second to maintain
            adjustment_interval: How often to adjust rates (seconds)
            **kwargs: Passed to parent EventSampler
        """
        super().__init__(**kwargs)
        self.target_eps = target_eps
        self.adjustment_interval = adjustment_interval

        self._adjustment_start = datetime.now()
        self._events_since_adjustment = 0
        self._rate_multiplier = 1.0

    def should_sample(self, event: HookEvent) -> bool:
        """
        Sample with adaptive rate adjustment.

        Args:
            event: Event to evaluate

        Returns:
            True if event should be sampled
        """
        # Check if adjustment needed
        elapsed = (datetime.now() - self._adjustment_start).total_seconds()
        if elapsed >= self.adjustment_interval:
            self._adjust_rates()

        result = super().should_sample(event)
        if result:
            self._events_since_adjustment += 1
        return result

    def _adjust_rates(self) -> None:
        """Adjust sampling rates based on observed throughput."""
        elapsed = (datetime.now() - self._adjustment_start).total_seconds()
        if elapsed == 0:
            return

        current_eps = self._events_since_adjustment / elapsed

        if current_eps > 0:
            # Calculate needed adjustment
            ratio = self.target_eps / current_eps

            # Apply with dampening to avoid oscillation
            self._rate_multiplier = max(0.1, min(2.0, self._rate_multiplier * (0.5 + 0.5 * ratio)))

            # Update effective rates
            self._effective_rates = {
                event_type: min(1.0, rate * self._rate_multiplier)
                for event_type, rate in self._calculate_effective_rates().items()
            }

        # Reset tracking
        self._adjustment_start = datetime.now()
        self._events_since_adjustment = 0

    def get_stats(self) -> dict[str, Any]:
        """Get adaptive sampler statistics."""
        base_stats = super().get_stats()
        base_stats.update({
            "target_eps": self.target_eps,
            "rate_multiplier": f"{self._rate_multiplier:.2f}",
            "adaptive": True,
        })
        return base_stats
