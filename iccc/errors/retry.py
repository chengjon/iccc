"""Retry mechanisms with exponential backoff and circuit breaker patterns."""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryStrategy(str, Enum):
    """Retry strategy types."""

    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


class CircuitBreakerState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures exceed threshold, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class RetryConfig(BaseModel):
    """Configuration for retry behavior."""

    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay: float = Field(default=1.0, gt=0)
    max_delay: float = Field(default=60.0, gt=0)
    exponential_base: float = Field(default=2.0, gt=1)
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    retryable_exceptions: list[type[Exception]] = Field(
        default_factory=lambda: [ConnectionError, TimeoutError]
    )


class CircuitBreakerConfig(BaseModel):
    """Configuration for circuit breaker."""

    failure_threshold: int = Field(default=5, ge=1)
    success_threshold: int = Field(default=2, ge=1)
    timeout: float = Field(default=60.0, gt=0)  # Seconds to wait before half-open
    half_open_max_calls: int = Field(default=3, ge=1)


class CircuitBreaker:
    """Circuit breaker for external service calls."""

    def __init__(self, config: CircuitBreakerConfig) -> None:
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                logger.info("Circuit breaker transitioning to HALF_OPEN")
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker is OPEN. Last failure: {self.last_failure_time}"
                )

        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.half_open_calls >= self.config.half_open_max_calls:
                raise CircuitBreakerOpenError("Circuit breaker HALF_OPEN call limit reached")
            self.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        elapsed = datetime.now() - self.last_failure_time
        return elapsed.total_seconds() >= self.config.timeout

    def _on_success(self) -> None:
        """Handle successful call."""
        self.failure_count = 0

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                logger.info("Circuit breaker transitioning to CLOSED (recovered)")
                self.state = CircuitBreakerState.CLOSED
                self.success_count = 0
                self.half_open_calls = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.success_count = 0

        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.warning("Circuit breaker reopening after failure in HALF_OPEN state")
            self.state = CircuitBreakerState.OPEN
            self.half_open_calls = 0
        elif self.failure_count >= self.config.failure_threshold:
            logger.error(
                f"Circuit breaker opening after {self.failure_count} failures"
            )
            self.state = CircuitBreakerState.OPEN


class RetryExecutor:
    """Execute functions with retry logic and exponential backoff."""

    def __init__(self, config: RetryConfig) -> None:
        self.config = config

    async def execute(
        self, func: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        """Execute function with retry logic."""
        last_exception: Optional[Exception] = None
        delay = self.config.initial_delay

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                logger.debug(f"Attempt {attempt}/{self.config.max_attempts}")
                result = await func(*args, **kwargs)
                if attempt > 1:
                    logger.info(f"Succeeded on attempt {attempt}")
                return result

            except Exception as e:
                last_exception = e

                # Check if exception is retryable
                if not self._is_retryable(e):
                    logger.error(f"Non-retryable exception: {type(e).__name__}: {e}")
                    raise

                # Last attempt - don't wait
                if attempt == self.config.max_attempts:
                    logger.error(
                        f"All {self.config.max_attempts} attempts failed. "
                        f"Last error: {type(e).__name__}: {e}"
                    )
                    break

                # Calculate delay and wait
                logger.warning(
                    f"Attempt {attempt} failed: {type(e).__name__}: {e}. "
                    f"Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
                delay = self._calculate_next_delay(delay, attempt)

        # All retries exhausted
        raise RetryExhaustedError(
            f"Failed after {self.config.max_attempts} attempts"
        ) from last_exception

    def _is_retryable(self, exception: Exception) -> bool:
        """Check if exception is retryable."""
        return any(
            isinstance(exception, exc_type)
            for exc_type in self.config.retryable_exceptions
        )

    def _calculate_next_delay(self, current_delay: float, attempt: int) -> float:
        """Calculate next delay based on strategy."""
        if self.config.strategy == RetryStrategy.EXPONENTIAL:
            next_delay = current_delay * self.config.exponential_base
        elif self.config.strategy == RetryStrategy.LINEAR:
            next_delay = current_delay + self.config.initial_delay
        else:  # FIXED
            next_delay = self.config.initial_delay

        return min(next_delay, self.config.max_delay)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    pass


# Global circuit breakers for common services
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    service_name: str, config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """Get or create circuit breaker for a service."""
    if service_name not in _circuit_breakers:
        _config = config or CircuitBreakerConfig()
        _circuit_breakers[service_name] = CircuitBreaker(_config)
    return _circuit_breakers[service_name]


async def with_retry(
    func: Callable[..., T],
    *args: Any,
    config: Optional[RetryConfig] = None,
    **kwargs: Any,
) -> T:
    """Convenience function to execute with retry logic."""
    _config = config or RetryConfig()
    executor = RetryExecutor(_config)
    return await executor.execute(func, *args, **kwargs)


async def with_circuit_breaker(
    service_name: str,
    func: Callable[..., T],
    *args: Any,
    cb_config: Optional[CircuitBreakerConfig] = None,
    **kwargs: Any,
) -> T:
    """Convenience function to execute with circuit breaker protection."""
    breaker = get_circuit_breaker(service_name, cb_config)
    return await breaker.call(func, *args, **kwargs)
