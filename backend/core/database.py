import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)

from .configs import DatabaseConfig


class AsyncDatabaseManager:
    """
    Database Manager with asynchronous SQLAlchemy Engine and Sessions.
    """

    def __init__(self, settings: DatabaseConfig):
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.database_url = settings.async_url.get_secret_value()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    # TODO: Consider settings a idle_session_duration or whatever pg field it is to the database
    def _create_engine(self) -> AsyncEngine:
        """Create and configure the async database engine."""
        return create_async_engine(
            self.database_url,
            # controls how many connections in pool
            pool_size=self.settings.async_pool_size,
            # extra connections allowed temporarily
            max_overflow=self.settings.async_max_overflow,
            # seconds to wait before error if pool is full
            pool_timeout=self.settings.async_pool_timeout,
            # a pool pre ping to ensure non-stale connections: https://docs.sqlalchemy.org/en/20/core/pooling.html#dealing-with-disconnects
            pool_pre_ping=self.settings.async_pool_pre_ping,
        )

    def _create_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Create and configure the async session factory."""
        return async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,  # set false for async sessions: https://github.com/sqlalchemy/sqlalchemy/discussions/11495
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
