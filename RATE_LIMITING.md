# Redis-Based Rate Limiting Implementation

## Overview

This document describes the production-ready Redis-based rate limiting system implemented for the iCCC API.

## Architecture

### Components

1. **RedisRateLimiter** (`iccc/api/rate_limiter.py`)
   - Sliding window algorithm using Redis sorted sets
   - Atomic operations via Redis pipelines
   - Graceful failure handling (fail open)
   - Per-key rate limiting with configurable windows

2. **Middleware Integration** (`iccc/api/middleware.py`)
   - Automatic rate limit enforcement
   - HTTP header injection (X-RateLimit-*)
   - 429 status code for exceeded limits
   - Retry-After header support

3. **Configuration** (`iccc/config.py`)
   - Pydantic-based validation
   - Environment variable support
   - Per-tier limit overrides
   - Exempt path configuration

## Features

### Sliding Window Algorithm

Uses Redis sorted sets to implement accurate sliding window rate limiting:

```python
# Redis key: ratelimit:{key}
# Members: request timestamps
# Scores: same timestamps
# TTL: window duration

ZREMRANGEBYSCORE key 0 (now - window)  # Remove old requests
ZCARD key                               # Count current requests
ZADD key now now                        # Add current request
EXPIRE key window_seconds               # Set TTL
```

### Rate Limit Headers

Every response includes standard rate limit headers:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1702857600
```

### 429 Response

When rate limit is exceeded:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 42
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1702857600

{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded. Maximum 100 requests per 60 seconds.",
  "details": {
    "limit": 100,
    "window_seconds": 60,
    "retry_after": 42
  },
  "timestamp": "2024-12-08T10:30:00"
}
```

## Configuration

### Environment Variables

Add to `.env`:

```bash
# Rate Limiting
ICCC_RATE_LIMIT_ENABLED=true
ICCC_RATE_LIMIT_REQUESTS_PER_WINDOW=100
ICCC_RATE_LIMIT_WINDOW_SECONDS=60
```

### Programmatic Configuration

```python
from iccc.config import RateLimitConfig

config = RateLimitConfig(
    enabled=True,
    requests_per_window=100,
    window_seconds=60,
    exempt_paths=["/", "/health", "/schema"],
)
```

## Usage

### Initialization

```python
from iccc.api.rate_limiter import RedisRateLimiter
from iccc.api.middleware import set_rate_limiter

# Create rate limiter
limiter = RedisRateLimiter(
    redis_url="redis://localhost:6379/0",
    requests_per_window=100,
    window_seconds=60,
)

await limiter.connect()

# Set global instance for middleware
set_rate_limiter(limiter)
```

### Check Rate Limit

```python
# Check and increment
result = await limiter.check_rate_limit("user123")

if result.allowed:
    # Process request
    print(f"Allowed. Remaining: {result.remaining}")
else:
    # Reject request
    print(f"Blocked. Retry in {result.reset_after_seconds}s")
```

### Manual Management

```python
# Get remaining without incrementing
remaining, reset_after = await limiter.get_remaining("user123")

# Reset limit for a key
await limiter.reset_limit("user123")

# Clear all rate limit data (use with caution)
deleted_count = await limiter.clear_all()
```

## Rate Limit Keys

The middleware automatically determines the rate limit key:

1. **API Key** (preferred): `apikey:{first_16_chars}`
   - From `X-API-Key` header
   - Or `Authorization: Bearer` token

2. **Client IP** (fallback): `ip:{client_ip}`
   - Used when no API key present
   - Based on `request.client.host`

## Graceful Failure Handling

The rate limiter implements "fail open" behavior:

- **Redis Connection Failure**: Allows requests, logs warning
- **Redis Operation Error**: Allows requests, logs error
- **Middleware Error**: Allows requests, logs error

This prevents rate limiting issues from causing service outages.

## Performance Characteristics

### Redis Operations

Each rate limit check performs:
- 1 pipeline with 4 commands: `ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`, `EXPIRE`
- Atomic execution via Redis pipeline
- O(log N + M) complexity where N = total items, M = items removed

### Memory Usage

Per key: ~100 bytes + (32 bytes per request in window)

Example: 10,000 active keys, 100 req/min window = ~4 MB

### Throughput

Redis can handle 100,000+ rate limit checks per second on modern hardware.

## Testing

### Unit Tests

```bash
pytest tests/api/test_rate_limiter.py -v
```

Tests include:
- Sliding window accuracy
- Multiple key isolation
- Redis error handling
- Header injection
- 429 response format

### Integration Tests

```bash
pytest tests/api/test_rate_limiter.py -v -m integration
```

Requires Redis running on `localhost:6379`.

### Demo Script

```bash
python examples/rate_limiter_demo.py
```

Shows:
- Basic rate limiting
- Sliding window behavior
- Multiple key isolation
- Graceful failure

## Production Considerations

### Redis Configuration

1. **Persistence**: Use AOF or RDB for rate limit data persistence
2. **Memory**: Set `maxmemory-policy volatile-lru` for automatic cleanup
3. **Replication**: Use Redis Sentinel or Cluster for high availability
4. **Monitoring**: Track rate limit keys, memory usage, command latency

### Rate Limit Tuning

- **Web API**: 100-1000 req/min per user
- **Mobile API**: 60-300 req/min per device
- **Internal Services**: 1000-10000 req/min per service
- **Burst Tolerance**: Use larger windows (5-15 min) for bursty traffic

### Security

- Rate limit before authentication to prevent auth brute force
- Use different limits for different endpoint types
- Implement IP-based limits for unauthenticated endpoints
- Monitor for rate limit abuse patterns

## Files Created/Modified

### New Files
- `/opt/iflow/iccc/iccc/api/rate_limiter.py` - Core rate limiter implementation
- `/opt/iflow/iccc/tests/api/test_rate_limiter.py` - Comprehensive tests
- `/opt/iflow/iccc/examples/rate_limiter_demo.py` - Demonstration script
- `/opt/iflow/iccc/RATE_LIMITING.md` - This documentation

### Modified Files
- `/opt/iflow/iccc/iccc/config.py` - Added RateLimitConfig class
- `/opt/iflow/iccc/iccc/api/middleware.py` - Implemented rate_limit_middleware
- `/opt/iflow/iccc/iccc/api/app.py` - Integrated rate limiting middleware
- `/opt/iflow/iccc/.env.example` - Added rate limit configuration
- `/opt/iflow/iccc/tests/api/test_middleware.py` - Added rate limit tests

## API Reference

### RedisRateLimiter

```python
class RedisRateLimiter:
    """Redis-based rate limiter using sliding window algorithm."""

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        redis_url: Optional[str] = None,
        requests_per_window: int = 100,
        window_seconds: int = 60,
        key_prefix: str = "ratelimit",
    )

    async def connect(self) -> None
    async def disconnect(self) -> None
    async def check_rate_limit(self, key: str, increment: bool = True) -> RateLimitResult
    async def get_remaining(self, key: str) -> Tuple[int, int]
    async def reset_limit(self, key: str) -> None
    async def clear_all(self) -> int
```

### RateLimitResult

```python
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool              # Whether request is allowed
    limit: int                 # Maximum requests per window
    remaining: int             # Requests remaining in window
    reset_timestamp: float     # Unix timestamp of window reset

    @property
    def reset_after_seconds(self) -> int  # Seconds until reset
```

## Troubleshooting

### Rate limiter not working

1. Check Redis connection: `redis-cli ping`
2. Verify rate limiter is initialized: Check middleware setup
3. Enable debug logging: `ICCC_LOG_LEVEL=DEBUG`

### Too many false positives

1. Increase window size or request limit
2. Check for clock skew between servers
3. Verify key generation is consistent

### Performance issues

1. Check Redis latency: `redis-cli --latency`
2. Monitor pipeline execution time
3. Consider Redis Cluster for horizontal scaling

## Future Enhancements

- [ ] Distributed rate limiting across multiple Redis instances
- [ ] Per-endpoint rate limits
- [ ] Tiered rate limits (free/paid/enterprise)
- [ ] Rate limit analytics and reporting
- [ ] Automatic rate limit adjustment based on load
- [ ] Token bucket algorithm option
- [ ] Rate limit bypass tokens
