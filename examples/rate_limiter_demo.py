"""
Demonstration of Redis-based rate limiting.

This script shows:
1. How to initialize and use the RedisRateLimiter
2. Sliding window rate limiting behavior
3. Graceful failure handling
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from iccc.api.rate_limiter import RedisRateLimiter


async def demo_basic_rate_limiting():
    """Demonstrate basic rate limiting functionality."""
    print("\n=== Basic Rate Limiting Demo ===\n")

    # Create rate limiter: 5 requests per 10 seconds
    limiter = RedisRateLimiter(
        redis_url="redis://localhost:6379/15",  # Use test DB
        requests_per_window=5,
        window_seconds=10,
        key_prefix="demo",
    )

    try:
        await limiter.connect()
        print("✓ Connected to Redis")

        # Clear any previous demo data
        await limiter.clear_all()

        test_key = "user123"

        print(f"\nRate Limit: 5 requests per 10 seconds for key '{test_key}'")
        print("-" * 60)

        # Make 7 requests (5 should succeed, 2 should be blocked)
        for i in range(1, 8):
            result = await limiter.check_rate_limit(test_key)

            status = "✓ ALLOWED" if result.allowed else "✗ BLOCKED"
            print(
                f"Request {i}: {status} | "
                f"Remaining: {result.remaining}/{result.limit} | "
                f"Reset in: {result.reset_after_seconds}s"
            )

            if not result.allowed:
                print(f"  ⚠ Rate limit exceeded! Retry after {result.reset_after_seconds} seconds")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        # Cleanup
        await limiter.clear_all()
        await limiter.disconnect()
        print("\n✓ Disconnected from Redis")


async def demo_sliding_window():
    """Demonstrate sliding window behavior."""
    print("\n=== Sliding Window Demo ===\n")

    limiter = RedisRateLimiter(
        redis_url="redis://localhost:6379/15",
        requests_per_window=3,
        window_seconds=5,
        key_prefix="demo_window",
    )

    try:
        await limiter.connect()
        await limiter.clear_all()

        test_key = "api_client_xyz"

        print(f"Rate Limit: 3 requests per 5 seconds for key '{test_key}'")
        print("-" * 60)

        # Make 3 requests quickly
        print("\n1. Making 3 requests (should all succeed):")
        for i in range(1, 4):
            result = await limiter.check_rate_limit(test_key)
            print(f"  Request {i}: {'✓ ALLOWED' if result.allowed else '✗ BLOCKED'} (remaining: {result.remaining})")

        # 4th request should be blocked
        print("\n2. Making 4th request (should be blocked):")
        result = await limiter.check_rate_limit(test_key)
        print(f"  Request 4: {'✓ ALLOWED' if result.allowed else '✗ BLOCKED'}")

        if not result.allowed:
            print(f"  ⚠ Must wait {result.reset_after_seconds} seconds")

            # Wait for window to pass
            print(f"\n3. Waiting {result.reset_after_seconds + 1} seconds for window to reset...")
            await asyncio.sleep(result.reset_after_seconds + 1)

            # Now request should succeed
            print("\n4. Making request after window reset:")
            result = await limiter.check_rate_limit(test_key)
            print(f"  Request: {'✓ ALLOWED' if result.allowed else '✗ BLOCKED'} (remaining: {result.remaining})")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        await limiter.clear_all()
        await limiter.disconnect()


async def demo_multiple_keys():
    """Demonstrate isolated rate limits for different keys."""
    print("\n=== Multiple Keys Demo ===\n")

    limiter = RedisRateLimiter(
        redis_url="redis://localhost:6379/15",
        requests_per_window=3,
        window_seconds=10,
        key_prefix="demo_multi",
    )

    try:
        await limiter.connect()
        await limiter.clear_all()

        print("Rate Limit: 3 requests per 10 seconds per key")
        print("-" * 60)

        # Different API keys
        keys = ["apikey:abc123", "apikey:def456", "ip:192.168.1.1"]

        for key in keys:
            print(f"\nKey: {key}")
            # Make 4 requests for this key
            for i in range(1, 5):
                result = await limiter.check_rate_limit(key)
                status = "✓ ALLOWED" if result.allowed else "✗ BLOCKED"
                print(f"  Request {i}: {status} (remaining: {result.remaining})")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        await limiter.clear_all()
        await limiter.disconnect()


async def demo_graceful_failure():
    """Demonstrate graceful failure when Redis is unavailable."""
    print("\n=== Graceful Failure Demo ===\n")

    # Use invalid Redis URL
    limiter = RedisRateLimiter(
        redis_url="redis://invalid-host:6379/0",
        requests_per_window=10,
        window_seconds=60,
    )

    try:
        # Try to connect (will fail)
        print("Attempting to connect to invalid Redis host...")
        await limiter.connect()
    except Exception as e:
        print(f"✗ Connection failed (expected): {type(e).__name__}")
        print("\nNote: In production, the rate limiter fails open")
        print("      (allows requests) when Redis is unavailable")
        print("      to prevent service disruption.")

    print("\n" + "=" * 60)


async def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("Redis Rate Limiter Demonstration")
    print("=" * 60)

    try:
        # Test if Redis is available
        test_limiter = RedisRateLimiter(redis_url="redis://localhost:6379/15")
        await test_limiter.connect()
        await test_limiter.disconnect()

        # Run demos
        await demo_basic_rate_limiting()
        await demo_sliding_window()
        await demo_multiple_keys()
        await demo_graceful_failure()

        print("\n✓ All demos completed successfully!\n")

    except Exception as e:
        print(f"\n✗ Redis connection failed: {e}")
        print("\nPlease ensure Redis is running:")
        print("  - Docker: docker run -d -p 6379:6379 redis:latest")
        print("  - Local: redis-server")
        print("\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
