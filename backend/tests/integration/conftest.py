import pytest

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models.base_model import Base


@pytest.fixture(scope="session")
async def async_db_engine(url: str):
    engine = create_async_engine(url)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest.fixture()
async def async_db_session(async_db_engine):
    with async_db_engine.connect() as conn:
        await conn.begin()  # start transaction
        await conn.begin_nested()  # setup SAVEPOINT

        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")

        yield session
        await session.close()
        await conn.rollback()
