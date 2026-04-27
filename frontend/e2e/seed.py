"""Seed SQLite DB for Playwright E2E tests."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Base
from tests.e2e.conftest import seed_base_data, seed_op_rules
from tests.integration.test_blockage_strategies import _seed_repair_strategy_data

DB_PATH = Path(__file__).with_suffix('.db')
ASYNC_URL = f"sqlite+aiosqlite:///{DB_PATH}"


async def main():
    engine = create_async_engine(ASYNC_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await seed_base_data(session)
        await seed_op_rules(session)
        # Seed both serial states (1,2) and repair states (3,4)
        await _seed_repair_strategy_data(session)
        await session.commit()

    print(f"Seeded: {DB_PATH}")


if __name__ == '__main__':
    asyncio.run(main())
