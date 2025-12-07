#!/usr/bin/env python3
"""Diagnose MongoDB connection issues."""

import asyncio
import socket
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient


async def test_socket_connection(host, port):
    """Test raw socket connection."""
    print(f"\n[1] Testing TCP connection to {host}:{port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, int(port)))
        sock.close()

        if result == 0:
            print(f"✓ TCP connection successful")
            return True
        else:
            print(f"✗ TCP connection failed (error code: {result})")
            return False
    except socket.gaierror as e:
        print(f"✗ DNS resolution failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Socket error: {e}")
        return False


async def test_mongodb_variants(host, port, username, password, dbname):
    """Test different MongoDB connection string variants."""
    print(f"\n[2] Testing different MongoDB connection strings...\n")

    variants = [
        {
            "name": "With auth + authSource=admin",
            "uri": f"mongodb://{username}:{password}@{host}:{port}/{dbname}?authSource=admin",
        },
        {
            "name": "With auth + authSource=iccc",
            "uri": f"mongodb://{username}:{password}@{host}:{port}/{dbname}?authSource={dbname}",
        },
        {
            "name": "With auth + no authSource",
            "uri": f"mongodb://{username}:{password}@{host}:{port}/{dbname}",
        },
        {
            "name": "Without auth",
            "uri": f"mongodb://{host}:{port}/{dbname}",
        },
        {
            "name": "With auth + directConnection=true",
            "uri": f"mongodb://{username}:{password}@{host}:{port}/{dbname}?authSource=admin&directConnection=true",
        },
    ]

    for variant in variants:
        print(f"Testing: {variant['name']}")
        print(f"  URI: {variant['uri']}")

        try:
            client = AsyncIOMotorClient(
                variant["uri"], serverSelectionTimeoutMS=5000
            )
            await client.admin.command("ping")
            print(f"  ✓ SUCCESS\n")
            client.close()
            return variant["uri"]
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + "..."
            print(f"  ✗ Failed: {error_msg}\n")

    return None


async def main():
    """Main diagnostic function."""
    print("=" * 60)
    print("MongoDB Connection Diagnostics")
    print("=" * 60)

    # Load environment
    env_file = project_root / ".env"
    load_dotenv(env_file)

    import os

    host = os.getenv("MONGODB_HOST", "192.168.123.104")
    port = os.getenv("MONGODB_PORT", "27017")
    username = os.getenv("MONGODB_USERNAME", "mongo")
    password = os.getenv("MONGODB_PASSWORD", "")
    dbname = os.getenv("MONGODB_DBNAME", "iccc")

    print(f"\nConfiguration:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Username: {username}")
    print(f"  Password: {'<set>' if password else '<not set>'}")
    print(f"  Database: {dbname}")

    # Test TCP connection
    tcp_ok = await test_socket_connection(host, port)

    if not tcp_ok:
        print("\n" + "=" * 60)
        print("✗ TCP connection failed")
        print("=" * 60)
        print("\nPossible causes:")
        print("  1. MongoDB is not running on the remote server")
        print("  2. MongoDB is not bound to 0.0.0.0 (check bindIp in mongod.conf)")
        print("  3. Firewall is blocking port 27017")
        print("  4. Network routing issue")
        print("\nTo check on the MongoDB server:")
        print(f"  1. netstat -tlnp | grep {port}")
        print("  2. sudo systemctl status mongod")
        print("  3. sudo cat /etc/mongod.conf | grep bindIp")
        return 1

    # Test MongoDB connection variants
    working_uri = await test_mongodb_variants(host, port, username, password, dbname)

    if working_uri:
        print("=" * 60)
        print("✓ Found working connection!")
        print("=" * 60)
        print(f"\nWorking URI: {working_uri}")
        print("\nUpdate your .env file with:")
        print(f'MONGODB_URL="{working_uri}"')
        return 0
    else:
        print("=" * 60)
        print("✗ No working connection found")
        print("=" * 60)
        print("\nPossible causes:")
        print("  1. Incorrect username/password")
        print("  2. User doesn't have access to the database")
        print("  3. MongoDB authentication is not enabled")
        print("  4. User exists in different authSource database")
        print("\nTo debug on MongoDB server:")
        print("  1. Check if auth is enabled:")
        print("     mongosh --eval 'db.runCommand({getCmdLineOpts: 1})'")
        print("  2. Check users:")
        print("     mongosh admin --eval 'db.getUsers()'")
        print("  3. Try connecting from server:")
        print(f"     mongosh mongodb://{username}:{password}@localhost:27017/{dbname}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
