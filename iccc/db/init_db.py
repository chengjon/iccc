"""Database initialization script."""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

from iccc.config import load_config

# Load .env file
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_indexes(db):
    """Create indexes for all collections."""
    logger.info("Creating indexes...")

    # Projects collection indexes
    await db.projects.create_index("name", unique=True)
    await db.projects.create_index("status")
    await db.projects.create_index("created_at")
    logger.info("✓ Created indexes for 'projects' collection")

    # Agents collection indexes
    await db.agents.create_index("type")
    await db.agents.create_index("status")
    await db.agents.create_index("model")
    await db.agents.create_index("created_at")
    logger.info("✓ Created indexes for 'agents' collection")

    # Tasks collection indexes
    await db.tasks.create_index("project_id")
    await db.tasks.create_index("status")
    await db.tasks.create_index("task_type")
    await db.tasks.create_index("assigned_agent_id")
    await db.tasks.create_index("created_at")
    await db.tasks.create_index([("project_id", 1), ("status", 1)])
    logger.info("✓ Created indexes for 'tasks' collection")

    # Sessions collection indexes
    await db.sessions.create_index("agent_id")
    await db.sessions.create_index("task_id")
    await db.sessions.create_index("started_at")
    await db.sessions.create_index([("agent_id", 1), ("started_at", -1)])
    logger.info("✓ Created indexes for 'sessions' collection")

    # Events collection indexes
    await db.events.create_index("session_id")
    await db.events.create_index("event_type")
    await db.events.create_index("timestamp")
    await db.events.create_index([("session_id", 1), ("timestamp", 1)])
    logger.info("✓ Created indexes for 'events' collection")


async def init_database():
    """Initialize the database with collections and indexes."""
    logger.info("=" * 60)
    logger.info("MongoDB Database Initialization")
    logger.info("=" * 60)

    # Load configuration
    config = load_config()
    logger.info(f"\nMongoDB URI: {config.mongodb.uri}")
    logger.info(f"Database: {config.mongodb.database}")

    # Connect to MongoDB
    logger.info("\n[1/4] Connecting to MongoDB...")
    try:
        client = AsyncIOMotorClient(
            config.mongodb.uri,
            serverSelectionTimeoutMS=config.mongodb.timeout_ms,
        )
        await client.admin.command("ping")
        logger.info("✓ Connected to MongoDB")
    except Exception as e:
        logger.error(f"✗ Failed to connect to MongoDB: {e}")
        return 1

    # Get database
    db = client[config.mongodb.database]

    # List existing collections
    logger.info("\n[2/4] Checking existing collections...")
    existing_collections = await db.list_collection_names()
    if existing_collections:
        logger.info(f"Found {len(existing_collections)} existing collections:")
        for coll in existing_collections:
            count = await db[coll].count_documents({})
            logger.info(f"  - {coll}: {count} documents")
    else:
        logger.info("No existing collections found")

    # Create collections if they don't exist
    logger.info("\n[3/4] Creating collections...")
    required_collections = ["projects", "agents", "tasks", "sessions", "events"]

    for collection_name in required_collections:
        if collection_name not in existing_collections:
            await db.create_collection(collection_name)
            logger.info(f"✓ Created collection: {collection_name}")
        else:
            logger.info(f"⊘ Collection already exists: {collection_name}")

    # Create indexes
    logger.info("\n[4/4] Creating indexes...")
    await create_indexes(db)

    # Verify setup
    logger.info("\n" + "=" * 60)
    logger.info("Verification")
    logger.info("=" * 60)

    collections = await db.list_collection_names()
    logger.info(f"\nTotal collections: {len(collections)}")

    for coll_name in collections:
        indexes = await db[coll_name].index_information()
        count = await db[coll_name].count_documents({})
        logger.info(f"\n{coll_name}:")
        logger.info(f"  Documents: {count}")
        logger.info(f"  Indexes: {len(indexes)}")
        for idx_name, idx_info in indexes.items():
            if idx_name != "_id_":
                keys = idx_info.get("key", [])
                logger.info(f"    - {idx_name}: {keys}")

    # Close connection
    client.close()

    logger.info("\n" + "=" * 60)
    logger.info("✓ Database initialization complete!")
    logger.info("=" * 60)

    logger.info("\nYou can now:")
    logger.info("  1. Run tests: pytest tests/")
    logger.info("  2. Start API server: litestar run")
    logger.info("  3. Create your first project via API")

    return 0


async def drop_database():
    """Drop the entire database (use with caution!)."""
    logger.warning("=" * 60)
    logger.warning("WARNING: Database Drop Operation")
    logger.warning("=" * 60)

    config = load_config()
    logger.warning(f"\nThis will drop database: {config.mongodb.database}")
    logger.warning("All data will be permanently deleted!")

    # Connect to MongoDB
    client = AsyncIOMotorClient(
        config.mongodb.uri,
        serverSelectionTimeoutMS=config.mongodb.timeout_ms,
    )

    # Drop database
    await client.drop_database(config.mongodb.database)
    logger.info(f"\n✓ Dropped database: {config.mongodb.database}")

    client.close()


async def reset_database():
    """Drop and reinitialize the database."""
    logger.info("Resetting database...")
    await drop_database()
    await init_database()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MongoDB database management")
    parser.add_argument(
        "action",
        choices=["init", "drop", "reset"],
        help="Action to perform: init (create), drop (delete), or reset (drop + init)",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompts",
    )

    args = parser.parse_args()

    if args.action == "drop" and not args.yes:
        response = input(
            "Are you sure you want to drop the database? This cannot be undone! (yes/no): "
        )
        if response.lower() != "yes":
            logger.info("Operation cancelled")
            sys.exit(0)

    if args.action == "reset" and not args.yes:
        response = input(
            "Are you sure you want to reset the database? All data will be lost! (yes/no): "
        )
        if response.lower() != "yes":
            logger.info("Operation cancelled")
            sys.exit(0)

    if args.action == "init":
        exit_code = asyncio.run(init_database())
    elif args.action == "drop":
        asyncio.run(drop_database())
        exit_code = 0
    elif args.action == "reset":
        asyncio.run(reset_database())
        exit_code = 0

    sys.exit(exit_code)
