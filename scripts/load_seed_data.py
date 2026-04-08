"""
Seed data loader script.

Loads initial data from SQL files into the database.

Usage:
    python scripts/load_seed_data.py [--file seeds/001_initial_data.sql]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.db.session import async_engine


async def load_seed_data(sql_file: str) -> None:
    """Load seed data from SQL file."""
    sql_path = Path(sql_file)
    
    if not sql_path.exists():
        print(f"Error: SQL file not found: {sql_path}")
        sys.exit(1)
    
    print(f"Loading seed data from: {sql_path}")
    
    sql_content = sql_path.read_text(encoding="utf-8")
    
    async with async_engine.begin() as conn:
        # Split by semicolons and execute each statement
        statements = [s.strip() for s in sql_content.split(";") if s.strip()]
        
        for i, statement in enumerate(statements, 1):
            if statement:
                try:
                    await conn.execute(text(statement))
                    print(f"  [{i}/{len(statements)}] Executed statement")
                except Exception as e:
                    print(f"  [{i}/{len(statements)}] Error: {e}")
                    raise
    
    print("Seed data loaded successfully!")


async def verify_seed_data() -> None:
    """Verify seed data was loaded correctly."""
    print("\nVerifying seed data...")
    
    async with async_engine.connect() as conn:
        # Check machine types
        result = await conn.execute(text("SELECT COUNT(*) FROM machine_type"))
        count = result.scalar()
        print(f"  Machine Types: {count}")
        
        # Check machines
        result = await conn.execute(text("SELECT COUNT(*) FROM machine"))
        count = result.scalar()
        print(f"  Machines: {count}")
        
        # Check state feature definitions
        result = await conn.execute(text("SELECT COUNT(*) FROM state_feature_def"))
        count = result.scalar()
        print(f"  State Feature Defs: {count}")
        
        # Check machine states
        result = await conn.execute(text("SELECT COUNT(*) FROM machine_state"))
        count = result.scalar()
        print(f"  Machine States: {count}")
        
        # Check machine state features
        result = await conn.execute(text("SELECT COUNT(*) FROM machine_state_feature"))
        count = result.scalar()
        print(f"  Machine State Features: {count}")
        
        # Check operation rules
        result = await conn.execute(text("SELECT COUNT(*) FROM op_rule"))
        count = result.scalar()
        print(f"  Operation Rules: {count}")
        
        # Check preconditions
        result = await conn.execute(text("SELECT COUNT(*) FROM op_rule_precond"))
        count = result.scalar()
        print(f"  Preconditions: {count}")
        
        # Check effects
        result = await conn.execute(text("SELECT COUNT(*) FROM op_rule_effect"))
        count = result.scalar()
        print(f"  Effects: {count}")
        
        # Check resources
        result = await conn.execute(text("SELECT COUNT(*) FROM resource"))
        count = result.scalar()
        print(f"  Resources: {count}")
    
    print("\nVerification complete!")


async def main():
    parser = argparse.ArgumentParser(description="Load seed data into database")
    parser.add_argument(
        "--file",
        type=str,
        default="seeds/001_initial_data.sql",
        help="SQL file to load",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing data, don't load",
    )
    
    args = parser.parse_args()
    
    if args.verify_only:
        await verify_seed_data()
    else:
        await load_seed_data(args.file)
        await verify_seed_data()
    
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
