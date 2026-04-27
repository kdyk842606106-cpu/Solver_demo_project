"""
Database connection test script.

Run this script to verify PostgreSQL connectivity:
    python scripts/test_db_connection.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import async_engine, sync_engine

# Total timeout for each connection attempt (seconds)
CONNECT_TIMEOUT = 10


async def test_async_connection():
    """Test async database connection with timeout."""
    print("Testing async connection...")
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.fetchone()
            print(f"  OK Async connection successful: {row}")
            return True
    except Exception as e:
        print(f"  FAIL Async connection failed: {e}")
        return False


def test_sync_connection():
    """Test sync database connection with timeout."""
    print("Testing sync connection...")
    try:
        with sync_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            row = result.fetchone()
            print(f"  OK Sync connection successful: {row}")
            return True
    except Exception as e:
        print(f"  FAIL Sync connection failed: {e}")
        return False


async def main():
    """Run all connection tests with timeout guard."""
    print("=" * 50)
    print("Database Connection Test")
    print("=" * 50)

    # Test sync connection first (simpler)
    sync_ok = test_sync_connection()

    # Test async connection with explicit timeout
    try:
        async_ok = await asyncio.wait_for(test_async_connection(), timeout=CONNECT_TIMEOUT)
    except asyncio.TimeoutError:
        print(f"  FAIL Async connection timed out after {CONNECT_TIMEOUT}s")
        async_ok = False

    print("=" * 50)
    if sync_ok and async_ok:
        print("All tests passed! Database is ready.")
        return 0
    else:
        print("Some tests failed. Check your database configuration.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
