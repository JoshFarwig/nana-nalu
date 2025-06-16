import os
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from backend.core.config import BaseConfig
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from sqlalchemy import text


class DatabaseManager:
    """
    DatabaseManager class to handle database connections and sessions.
    This class is designed to be used with SQLAlchemy's async capabilities.
    It provides methods to create and manage database sessions.
    """

    def __init__(self, settings: BaseConfig):
        self.settings = settings
        self.database_url = settings.database_url
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def _create_engine(self) -> AsyncEngine:
        """Create and configure the async database engine."""
        return create_async_engine(
            self.database_url,
            echo=self.settings.engine_echo,  # logs SQL queries
            pool_size=self.settings.engine_pool_size,  # controls how many connections in pool
            max_overflow=self.settings.engine_max_overflow,  # extra connections allowed temporarily
            pool_timeout=self.settings.engine_pool_timeout,  # seconds to wait before error if pool is full
        )

    def _create_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Create and configure the async session factory."""
        return async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=self.settings.session_expire_on_commit,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Get the database engine, creating it if necessary."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Get the session factory, creating it if necessary."""
        if self._session_factory is None:
            self._session_factory = self._create_session_factory()
        return self._session_factory

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session using async context manager.
        Use this with FastAPI Depends() for dependency injection.
        """
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    @asynccontextmanager
    async def session_context(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session using async context manager.
        Use this for manual session management outside of FastAPI.
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def health_check(self) -> bool:
        """Check if database connection is healthy."""
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the database engine and all connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    async def create_tables(self, metadata) -> None:
        """Create all tables defined in metadata."""
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def drop_tables(self, metadata) -> None:
        """Drop all tables defined in metadata."""
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.drop_all)
