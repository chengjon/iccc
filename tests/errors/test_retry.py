"""Tests for retry mechanisms and circuit breaker."""

import asyncio
import pytest
from datetime import datetime, timedelta

from iccc.errors.retry import (
    RetryStrategy,
    CircuitBreakerState,
    RetryConfig,
    CircuitBreakerConfig,
    CircuitBreaker,
    RetryExecutor,
    CircuitBreakerOpenError,
    RetryExhaustedError,
    get_circuit_breaker,
    with_retry,
    with_circuit_breaker,
)


class TestRetryConfig:
    """Test RetryConfig model."""

    def test_retry_config_defaults(self):
        """Test RetryConfig with default values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.strategy == RetryStrategy.EXPONENTIAL
        assert ConnectionError in config.retryable_exceptions
        assert TimeoutError in config.retryable_exceptions

    def test_retry_config_custom(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            max_attempts=5,
            initial_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0,
            strategy=RetryStrategy.LINEAR,
            retryable_exceptions=[ValueError],
        )
        assert config.max_attempts == 5
        assert config.initial_delay == 2.0
        assert config.max_delay == 120.0
        assert config.exponential_base == 3.0
        assert config.strategy == RetryStrategy.LINEAR
        assert config.retryable_exceptions == [ValueError]


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig model."""

    def test_circuit_breaker_config_defaults(self):
        """Test CircuitBreakerConfig with default values."""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 60.0
        assert config.half_open_max_calls == 3

    def test_circuit_breaker_config_custom(self):
        """Test CircuitBreakerConfig with custom values."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            success_threshold=3,
            timeout=120.0,
            half_open_max_calls=5,
        )
        assert config.failure_threshold == 10
        assert config.success_threshold == 3
        assert config.timeout == 120.0
        assert config.half_open_max_calls == 5


@pytest.mark.asyncio
class TestCircuitBreaker:
    """Test CircuitBreaker functionality."""

    async def test_initial_state_closed(self):
        """Test circuit breaker starts in CLOSED state."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0

    async def test_successful_call(self):
        """Test successful function call."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker(config)

        async def success_func():
            return "success"

        result = await breaker.call(success_func)
        assert result == "success"
        assert breaker.failure_count == 0
        assert breaker.state == CircuitBreakerState.CLOSED

    async def test_failed_call_increments_counter(self):
        """Test failed call increments failure counter."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config)

        async def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await breaker.call(failing_func)

        assert breaker.failure_count == 1
        assert breaker.state == CircuitBreakerState.CLOSED

    async def test_opens_after_threshold(self):
        """Test circuit breaker opens after failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config)

        async def failing_func():
            raise ValueError("Test error")

        # First 3 failures should open the circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.failure_count == 3

    async def test_rejects_calls_when_open(self):
        """Test circuit breaker rejects calls when OPEN."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker(config)

        async def failing_func():
            raise ValueError("Test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitBreakerState.OPEN

        # Next call should be rejected
        async def success_func():
            return "success"

        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(success_func)

    async def test_transitions_to_half_open(self):
        """Test circuit breaker transitions to HALF_OPEN after timeout."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=0.1)
        breaker = CircuitBreaker(config)

        async def failing_func():
            raise ValueError("Test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        assert breaker.state == CircuitBreakerState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Next call should transition to HALF_OPEN
        async def success_func():
            return "success"

        result = await breaker.call(success_func)
        assert result == "success"
        assert breaker.state == CircuitBreakerState.HALF_OPEN

    async def test_half_open_to_closed_on_success(self):
        """Test HALF_OPEN transitions to CLOSED after success threshold."""
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, timeout=0.1
        )
        breaker = CircuitBreaker(config)

        async def failing_func():
            raise ValueError("Test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        await asyncio.sleep(0.15)

        # Successful calls should close the circuit
        async def success_func():
            return "success"

        # First success
        await breaker.call(success_func)
        assert breaker.state == CircuitBreakerState.HALF_OPEN
        assert breaker.success_count == 1

        # Second success should close the circuit
        await breaker.call(success_func)
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.success_count == 0

    async def test_half_open_to_open_on_failure(self):
        """Test HALF_OPEN transitions back to OPEN on failure."""
        config = CircuitBreakerConfig(failure_threshold=2, timeout=0.1)
        breaker = CircuitBreaker(config)

        async def failing_func():
            raise ValueError("Test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        await asyncio.sleep(0.15)

        # Failure in HALF_OPEN should reopen
        with pytest.raises(ValueError):
            await breaker.call(failing_func)

        assert breaker.state == CircuitBreakerState.OPEN

    async def test_half_open_call_limit(self):
        """Test HALF_OPEN enforces max calls limit."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=5,  # Higher than half_open_max_calls
            timeout=0.1,
            half_open_max_calls=2,
        )
        breaker = CircuitBreaker(config)

        async def failing_func():
            raise ValueError("Test error")

        # Open the circuit
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(failing_func)

        await asyncio.sleep(0.15)

        async def success_func():
            return "success"

        # First two calls allowed
        await breaker.call(success_func)
        await breaker.call(success_func)

        # Third call should be rejected
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.call(success_func)


@pytest.mark.asyncio
class TestRetryExecutor:
    """Test RetryExecutor functionality."""

    async def test_successful_first_attempt(self):
        """Test function succeeds on first attempt."""
        config = RetryConfig(max_attempts=3)
        executor = RetryExecutor(config)

        async def success_func():
            return "success"

        result = await executor.execute(success_func)
        assert result == "success"

    async def test_retry_on_retryable_exception(self):
        """Test retry on retryable exception."""
        config = RetryConfig(
            max_attempts=3,
            initial_delay=0.01,
            retryable_exceptions=[ValueError],
        )
        executor = RetryExecutor(config)

        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"

        result = await executor.execute(flaky_func)
        assert result == "success"
        assert call_count == 3

    async def test_no_retry_on_non_retryable_exception(self):
        """Test no retry on non-retryable exception."""
        config = RetryConfig(
            max_attempts=3,
            retryable_exceptions=[ConnectionError],
        )
        executor = RetryExecutor(config)

        call_count = 0

        async def non_retryable_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Non-retryable error")

        with pytest.raises(ValueError):
            await executor.execute(non_retryable_func)

        assert call_count == 1  # Should not retry

    async def test_retry_exhausted_error(self):
        """Test RetryExhaustedError after max attempts."""
        config = RetryConfig(
            max_attempts=3,
            initial_delay=0.01,
            retryable_exceptions=[ValueError],
        )
        executor = RetryExecutor(config)

        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await executor.execute(always_fails)

        assert call_count == 3
        assert "3 attempts" in str(exc_info.value)

    async def test_exponential_backoff(self):
        """Test exponential backoff strategy."""
        config = RetryConfig(
            max_attempts=4,
            initial_delay=0.01,
            exponential_base=2.0,
            strategy=RetryStrategy.EXPONENTIAL,
            retryable_exceptions=[ValueError],
        )
        executor = RetryExecutor(config)

        delays = []
        original_sleep = asyncio.sleep

        async def track_sleep(delay):
            delays.append(delay)
            await original_sleep(delay)

        with pytest.MonkeyPatch.context() as m:
            m.setattr(asyncio, "sleep", track_sleep)

            call_count = 0

            async def always_fails():
                nonlocal call_count
                call_count += 1
                raise ValueError("Fail")

            with pytest.raises(RetryExhaustedError):
                await executor.execute(always_fails)

        # Check delays: 0.01, 0.02, 0.04
        assert len(delays) == 3
        assert delays[0] == 0.01
        assert delays[1] == 0.02
        assert delays[2] == 0.04

    async def test_linear_backoff(self):
        """Test linear backoff strategy."""
        config = RetryConfig(
            max_attempts=4,
            initial_delay=0.01,
            strategy=RetryStrategy.LINEAR,
            retryable_exceptions=[ValueError],
        )
        executor = RetryExecutor(config)

        delays = []
        original_sleep = asyncio.sleep

        async def track_sleep(delay):
            delays.append(delay)
            await original_sleep(delay)

        with pytest.MonkeyPatch.context() as m:
            m.setattr(asyncio, "sleep", track_sleep)

            async def always_fails():
                raise ValueError("Fail")

            with pytest.raises(RetryExhaustedError):
                await executor.execute(always_fails)

        # Check delays: 0.01, 0.02, 0.03
        assert len(delays) == 3
        assert delays[0] == 0.01
        assert delays[1] == 0.02
        assert delays[2] == 0.03

    async def test_fixed_backoff(self):
        """Test fixed backoff strategy."""
        config = RetryConfig(
            max_attempts=4,
            initial_delay=0.01,
            strategy=RetryStrategy.FIXED,
            retryable_exceptions=[ValueError],
        )
        executor = RetryExecutor(config)

        delays = []
        original_sleep = asyncio.sleep

        async def track_sleep(delay):
            delays.append(delay)
            await original_sleep(delay)

        with pytest.MonkeyPatch.context() as m:
            m.setattr(asyncio, "sleep", track_sleep)

            async def always_fails():
                raise ValueError("Fail")

            with pytest.raises(RetryExhaustedError):
                await executor.execute(always_fails)

        # Check all delays are the same
        assert len(delays) == 3
        assert all(d == 0.01 for d in delays)

    async def test_max_delay_cap(self):
        """Test max delay cap is enforced."""
        config = RetryConfig(
            max_attempts=5,
            initial_delay=10.0,
            max_delay=20.0,
            exponential_base=2.0,
            strategy=RetryStrategy.EXPONENTIAL,
            retryable_exceptions=[ValueError],
        )
        executor = RetryExecutor(config)

        delays = []
        original_sleep = asyncio.sleep

        async def track_sleep(delay):
            delays.append(delay)
            # Don't actually sleep in test
            await original_sleep(0.001)

        with pytest.MonkeyPatch.context() as m:
            m.setattr(asyncio, "sleep", track_sleep)

            async def always_fails():
                raise ValueError("Fail")

            with pytest.raises(RetryExhaustedError):
                await executor.execute(always_fails)

        # Delays: 10, 20, 20, 20 (capped)
        assert len(delays) == 4
        assert delays[0] == 10.0
        assert delays[1] == 20.0  # 10 * 2 = 20 (at cap)
        assert delays[2] == 20.0  # Capped
        assert delays[3] == 20.0  # Capped


@pytest.mark.asyncio
class TestConvenienceFunctions:
    """Test convenience functions."""

    async def test_with_retry_default_config(self):
        """Test with_retry with default config."""
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Temporary error")
            return "success"

        result = await with_retry(flaky_func)
        assert result == "success"
        assert call_count == 2

    async def test_with_retry_custom_config(self):
        """Test with_retry with custom config."""
        config = RetryConfig(max_attempts=5, initial_delay=0.01)

        async def success_func():
            return "success"

        result = await with_retry(success_func, config=config)
        assert result == "success"

    async def test_get_circuit_breaker(self):
        """Test get_circuit_breaker creates and caches breakers."""
        breaker1 = get_circuit_breaker("service1")
        breaker2 = get_circuit_breaker("service1")
        breaker3 = get_circuit_breaker("service2")

        assert breaker1 is breaker2  # Same instance
        assert breaker1 is not breaker3  # Different instance

    async def test_with_circuit_breaker(self):
        """Test with_circuit_breaker convenience function."""
        async def success_func():
            return "success"

        result = await with_circuit_breaker("test-service", success_func)
        assert result == "success"

    async def test_with_circuit_breaker_custom_config(self):
        """Test with_circuit_breaker with custom config."""
        config = CircuitBreakerConfig(failure_threshold=2)

        async def success_func():
            return "success"

        result = await with_circuit_breaker(
            "test-service-2", success_func, cb_config=config
        )
        assert result == "success"
