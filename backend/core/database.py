from typing import AsyncGenerator
from contextlib import asynccontextmanager

from backend.core.config import BaseConfig

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


class DatabaseManager:
    """
    DatabaseManager class to handle database connections and sessions.
    This class is designed to be used with SQLAlchemy's async capabilities.
    It provides methods to create and manage database sessions.
    """

    def __init__(
        self,
        settings: BaseConfig,
    ):
        self.database_url = settings.database_url
        self.engine = create_async_engine(
            self.database_url,
            echo=True,
            pool_size=10,  # controls how many connections in pool
            max_overflow=5,  # extra connections allowed temporarily
            pool_timeout=30,  # seconds to wait before error if pool is full,
        )
        self.AsyncSessionLocal = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    pass


# async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_size=10,  # controls how many connections in pool
    max_overflow=5,  # extra connections allowed temporarily
    pool_timeout=30,  # seconds to wait before error if pool is full,
)

# session factory, need to double check if I should be expiring on session commit or not.
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
