#!/usr/bin/env python3
"""Test script to verify MongoDB and Redis connections."""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from iccc.config import load_config


async def test_mongodb_connection(config):
    """Test MongoDB connection."""
    print("\n" + "=" * 60)
    print("Testing MongoDB Connection")
    print("=" * 60)

    print(f"\nConfiguration:")
    print(f"  URI: {config.mongodb.uri}")
    print(f"  Database: {config.mongodb.database}")
    print(f"  Timeout: {config.mongodb.timeout_ms}ms")

    try:
        # Create client
        client = AsyncIOMotorClient(
            config.mongodb.uri,
            serverSelectionTimeoutMS=config.mongodb.timeout_ms,
        )

        # Test connection
        print("\n[1/5] Connecting to MongoDB...")
        await client.admin.command("ping")
        print("✓ Connection successful")

        # Get server info
        print("\n[2/5] Getting server information...")
        server_info = await client.server_info()
        print(f"✓ MongoDB version: {server_info.get('version')}")

        # List databases
        print("\n[3/5] Listing databases...")
        db_list = await client.list_database_names()
        print(f"✓ Found {len(db_list)} databases: {', '.join(db_list)}")

        # Access target database
        print(f"\n[4/5] Accessing database '{config.mongodb.database}'...")
        db = client[config.mongodb.database]
        collections = await db.list_collection_names()
        print(f"✓ Found {len(collections)} collections")
        if collections:
            print(f"  Collections: {', '.join(collections)}")

        # Test write operation
        print("\n[5/5] Testing write operation...")
        test_collection = db["connection_test"]
        result = await test_collection.insert_one({"test": "connection", "status": "ok"})
        print(f"✓ Write successful (ID: {result.inserted_id})")

        # Clean up test document
        await test_collection.delete_one({"_id": result.inserted_id})
        print("✓ Cleanup successful")

        # Close connection
        client.close()

        print("\n" + "=" * 60)
        print("✓ MongoDB connection test PASSED")
        print("=" * 60)
        return True

    except ServerSelectionTimeoutError as e:
        print(f"\n✗ Connection timeout: {e}")
        print("\nPossible issues:")
        print("  - MongoDB server not running")
        print("  - Incorrect host/port")
        print("  - Network connectivity issues")
        print("  - Firewall blocking connection")
        return False

    except ConnectionFailure as e:
        print(f"\n✗ Connection failed: {e}")
        print("\nPossible issues:")
        print("  - Invalid credentials")
        print("  - Authentication database issue")
        print("  - User permissions")
        return False

    except Exception as e:
        print(f"\n✗ Unexpected error: {type(e).__name__}: {e}")
        return False


async def test_redis_connection(config):
    """Test Redis connection."""
    print("\n" + "=" * 60)
    print("Testing Redis Connection")
    print("=" * 60)

    print(f"\nConfiguration:")
    print(f"  Host: {config.redis.host}")
    print(f"  Port: {config.redis.port}")
    print(f"  Database: {config.redis.db}")
    print(f"  Password: {'<set>' if config.redis.password else '<none>'}")

    try:
        # Create Redis client
        redis_client = Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password if config.redis.password else None,
            decode_responses=True,
        )

        # Test connection
        print("\n[1/5] Connecting to Redis...")
        await redis_client.ping()
        print("✓ Connection successful")

        # Get server info
        print("\n[2/5] Getting server information...")
        info = await redis_client.info("server")
        print(f"✓ Redis version: {info.get('redis_version')}")
        print(f"  OS: {info.get('os')}")
        print(f"  Architecture: {info.get('arch_bits')}-bit")

        # Get database info
        print("\n[3/5] Getting database information...")
        db_info = await redis_client.info("keyspace")
        db_key = f"db{config.redis.db}"
        if db_key in db_info:
            print(f"✓ Database {config.redis.db} info: {db_info[db_key]}")
        else:
            print(f"✓ Database {config.redis.db} is empty")

        # Test write operation
        print("\n[4/5] Testing write operation...")
        test_key = "iccc:connection:test"
        await redis_client.set(test_key, "ok", ex=60)  # Expire in 60 seconds
        print(f"✓ Write successful (key: {test_key})")

        # Test read operation
        print("\n[5/5] Testing read operation...")
        value = await redis_client.get(test_key)
        print(f"✓ Read successful (value: {value})")

        # Clean up
        await redis_client.delete(test_key)
        print("✓ Cleanup successful")

        # Close connection
        await redis_client.aclose()

        print("\n" + "=" * 60)
        print("✓ Redis connection test PASSED")
        print("=" * 60)
        return True

    except RedisConnectionError as e:
        print(f"\n✗ Connection failed: {e}")
        print("\nPossible issues:")
        print("  - Redis server not running")
        print("  - Incorrect host/port")
        print("  - Network connectivity issues")
        print("  - Firewall blocking connection")
        return False

    except Exception as e:
        print(f"\n✗ Unexpected error: {type(e).__name__}: {e}")
        if "WRONGPASS" in str(e):
            print("\nAuthentication failed - check password")
        elif "NOAUTH" in str(e):
            print("\nAuthentication required but no password provided")
        return False


async def main():
    """Main test function."""
    print("\n" + "=" * 60)
    print("iCCC Connection Test Suite")
    print("=" * 60)

    # Load environment variables
    env_file = project_root / ".env"
    if env_file.exists():
        print(f"\n✓ Loading environment from: {env_file}")
        load_dotenv(env_file)
    else:
        print(f"\n⚠ .env file not found at: {env_file}")
        print("  Using system environment variables")

    # Load configuration
    print("\n✓ Loading configuration...")
    config = load_config()

    # Run tests
    mongodb_ok = await test_mongodb_connection(config)
    redis_ok = await test_redis_connection(config)

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"\nMongoDB: {'✓ PASSED' if mongodb_ok else '✗ FAILED'}")
    print(f"Redis:   {'✓ PASSED' if redis_ok else '✗ FAILED'}")

    if mongodb_ok and redis_ok:
        print("\n✓ All connection tests PASSED")
        print("\nYou can now:")
        print("  1. Run the test suite: pytest")
        print("  2. Start the API server: litestar run")
        print("  3. Initialize the database: python -m iccc.db.init_db")
        return 0
    else:
        print("\n✗ Some connection tests FAILED")
        print("\nPlease check:")
        print("  1. MongoDB and Redis services are running")
        print("  2. Configuration in .env file is correct")
        print("  3. Network connectivity to remote services")
        print("  4. Firewall rules allow connections")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
