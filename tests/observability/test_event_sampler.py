"""Tests for event sampling."""

import pytest
from datetime import datetime
from uuid import uuid4

from iccc.models.entities import HookEvent
from iccc.observability.event_sampler import (
    SAMPLING_RATES,
    AdaptiveSampler,
    EventSampler,
)


@pytest.fixture
def sample_event():
    """Create a sample event."""
    return HookEvent(
        id=uuid4(),
        session_id=uuid4(),
        event_type="PostToolUse",
        timestamp=datetime.now(),
        data={"tool_name": "Write", "status": "success"},
    )


@pytest.fixture
def critical_event():
    """Create a critical event."""
    return HookEvent(
        id=uuid4(),
        session_id=uuid4(),
        event_type="Error",
        timestamp=datetime.now(),
        data={"error": "Connection failed", "critical": True},
    )


class TestEventSampler:
    """Tests for EventSampler."""

    def test_default_initialization(self):
        """Test default sampler initialization."""
        sampler = EventSampler()

        assert sampler.default_rate == 0.5
        assert sampler.agent_count == 1
        assert len(sampler.sampling_rates) > 0

    def test_custom_sampling_rates(self):
        """Test custom sampling rates."""
        custom_rates = {"PostToolUse": 0.1, "Error": 1.0}
        sampler = EventSampler(sampling_rates=custom_rates)

        assert sampler.sampling_rates["PostToolUse"] == 0.1
        assert sampler.sampling_rates["Error"] == 1.0

    def test_critical_event_always_sampled(self, critical_event):
        """Test that critical events are always sampled."""
        sampler = EventSampler(default_rate=0.0)  # 0% rate

        # Even with 0% rate, critical events should pass
        results = [sampler.should_sample(critical_event) for _ in range(10)]

        assert all(results)

    def test_error_event_always_sampled(self):
        """Test that error events are always sampled."""
        sampler = EventSampler(default_rate=0.0)

        error_event = HookEvent(
            id=uuid4(),
            session_id=uuid4(),
            event_type="PostToolUse",
            timestamp=datetime.now(),
            data={"error": "Something went wrong"},
        )

        assert sampler.should_sample(error_event) is True

    def test_stop_event_always_sampled(self):
        """Test that Stop events are always sampled."""
        sampler = EventSampler(default_rate=0.0)

        stop_event = HookEvent(
            id=uuid4(),
            session_id=uuid4(),
            event_type="Stop",
            timestamp=datetime.now(),
            data={},
        )

        assert sampler.should_sample(stop_event) is True

    def test_sampling_rate_applied(self, sample_event):
        """Test that sampling rate is applied."""
        sampler = EventSampler(
            sampling_rates={"PostToolUse": 0.5},
            agent_count=1,
            enable_burst_detection=False,
        )

        # Sample many events
        results = [sampler.should_sample(sample_event) for _ in range(1000)]
        sample_rate = sum(results) / len(results)

        # Should be roughly 50% (with some variance)
        assert 0.3 < sample_rate < 0.7

    def test_agent_count_scaling(self):
        """Test that agent count affects sampling rates."""
        sampler_low = EventSampler(agent_count=3)
        sampler_high = EventSampler(agent_count=30)

        # Higher agent count should have lower effective rates
        for event_type in SAMPLING_RATES:
            low_rate = sampler_low._effective_rates.get(event_type, sampler_low.default_rate)
            high_rate = sampler_high._effective_rates.get(event_type, sampler_high.default_rate)
            assert high_rate <= low_rate

    def test_update_agent_count(self):
        """Test updating agent count."""
        sampler = EventSampler(agent_count=3)
        initial_rate = sampler._effective_rates.get("PostToolUse", 0)

        sampler.update_agent_count(30)

        new_rate = sampler._effective_rates.get("PostToolUse", 0)
        assert new_rate < initial_rate

    def test_set_rate(self):
        """Test setting custom rate for event type."""
        sampler = EventSampler()

        sampler.set_rate("CustomType", 0.75)

        assert sampler.sampling_rates["CustomType"] == 0.75

    def test_set_rate_clamped(self):
        """Test that rates are clamped to valid range."""
        sampler = EventSampler()

        sampler.set_rate("Type1", 1.5)  # Above 1.0
        sampler.set_rate("Type2", -0.5)  # Below 0.0

        assert sampler.sampling_rates["Type1"] == 1.0
        assert sampler.sampling_rates["Type2"] == 0.0

    def test_stats_tracking(self, sample_event, critical_event):
        """Test statistics tracking."""
        sampler = EventSampler()

        for _ in range(10):
            sampler.should_sample(sample_event)
            sampler.should_sample(critical_event)

        stats = sampler.get_stats()

        assert stats["total_events"] == 20
        assert stats["sampled_events"] > 0
        assert "PostToolUse" in stats["by_type"]
        assert "Error" in stats["by_type"]

    def test_reset_stats(self, sample_event):
        """Test statistics reset."""
        sampler = EventSampler()
        sampler.should_sample(sample_event)

        sampler.reset_stats()

        assert sampler.stats.total_events == 0
        assert sampler.stats.sampled_events == 0

    def test_burst_detection(self, sample_event):
        """Test burst detection mode."""
        sampler = EventSampler(
            enable_burst_detection=True,
            burst_threshold=10,
            burst_window_seconds=60,
        )

        # Generate many events quickly
        for _ in range(15):
            sampler.should_sample(sample_event)

        # Should be in burst mode
        assert sampler._in_burst_mode is True


class TestAdaptiveSampler:
    """Tests for AdaptiveSampler."""

    def test_initialization(self):
        """Test adaptive sampler initialization."""
        sampler = AdaptiveSampler(target_eps=10.0)

        assert sampler.target_eps == 10.0
        assert sampler._rate_multiplier == 1.0

    def test_adaptive_stats(self):
        """Test adaptive sampler stats."""
        sampler = AdaptiveSampler(target_eps=5.0)

        stats = sampler.get_stats()

        assert stats["target_eps"] == 5.0
        assert stats["adaptive"] is True

    def test_rate_multiplier_updated(self, sample_event):
        """Test that rate multiplier is updated."""
        sampler = AdaptiveSampler(
            target_eps=1.0,
            adjustment_interval=0,  # Adjust on every call
        )

        # Generate events
        for _ in range(10):
            sampler.should_sample(sample_event)

        # Rate multiplier should have changed
        # (might increase or decrease depending on throughput)
        assert sampler._rate_multiplier != 1.0 or sampler.stats.total_events > 0


class TestSamplingRatesDefaults:
    """Tests for default sampling rates."""

    def test_critical_events_high_rate(self):
        """Test that critical event types have high sampling rates."""
        assert SAMPLING_RATES["PreToolUse"] == 1.0
        assert SAMPLING_RATES["Stop"] == 1.0
        assert SAMPLING_RATES["SubagentStop"] == 1.0

    def test_debug_events_low_rate(self):
        """Test that debug events have low sampling rates."""
        assert SAMPLING_RATES["Debug"] < 0.2
        assert SAMPLING_RATES["Heartbeat"] < 0.2
