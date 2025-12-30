import logging
from typing import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from sqlalchemy import Engine, NullPool, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)

from .configs import DatabaseConfig

logger = logging.getLogger(__name__)


class AsyncDatabaseManager:
    """
    Database manager with async SQLAlchemy engine and sessions.
    Primarily used for fastapi ops.
    """

    def __init__(self, settings: DatabaseConfig):
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.database_url = settings.get_async_url()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    # TODO: consider settings a idle_session_duration or whatever pg field it is to the database
    def _create_engine(self) -> AsyncEngine:
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
            # plugin to add some event listeners
            plugins=["geoalchemy2"],
        )

    def _create_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            # set false for async sessions: https://github.com/sqlalchemy/sqlalchemy/discussions/11495
            expire_on_commit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self._session_factory = self._create_session_factory()
        return self._session_factory

    async def get_explicit_commit_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Issue out session via generator and expect EXPLICIT commits.

        This method is NOT decorated with @asynccontextmanager (unlike the
        SyncDatabaseManager's get_explicit_commit_session with @contextmanager)
        because FastAPI's Depends() cannot currently work with decorated context
        managers (they appear as regularfunctions to Python's inspect module,
        causing injection to fail).

        For direct usage outside FastAPI (scripts, tests), use explicit_commit_session() instead,
        which IS decorated with @asynccontextmanager for clean 'async with' syntax.

        FastAPI internally wraps this plain generator with to manage the session lifecycle
        (creation, exception handling, cleanup).

        PR #10353 may enable sync and async contextmanager support in future FastAPI versions.

        See: https://github.com/fastapi/fastapi/discussions/8955
             https://github.com/fastapi/fastapi/pull/10353
        """
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    @asynccontextmanager
    async def explicit_commit_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Issue out a context manager for the session and expect EXPLICIT commits.
        """
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    @asynccontextmanager
    async def auto_commit_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Issue out a context manager for the session and autocommit the entire transaction.
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def health_check(self) -> bool:
        try:
            async with self.session_factory() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
            self.logger.info("Successfully closed")
            self._engine = None
            self._session_factory = None


class SyncDatabaseManager:
    """
    Database manager with sync SQLAlchemy engine and session.
    Primarily used for celery worker ops
    """

    def __init__(self, settings: DatabaseConfig) -> None:
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.database_url = settings.get_sync_url()
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    def _create_engine(self) -> Engine:
        if self._engine is None:
            # NOTE: use NullPool for celery worker context. NullPool creates a fresh connection
            # for each request and closes it immediately, so no pooling or pre-ping needed.
            # this prevents connection sharing issues in multi-process environments, i.e.
            # celery's prefork concurrency model. overall, trying to keep celery tasks
            # all sync in nature to reduce multi-process errors, and remove
            # any chance for multiple async event loop errors.
            # https://docs.sqlalchemy.org/en/20/core/pooling.html#sqlalchemy.pool.NullPool
            # https://stackoverflow.com/questions/64016062/whats-the-proper-way-to-use-sqlalchemy-sessions-with-celery
            self._engine = create_engine(
                self.database_url,
                poolclass=NullPool,
                plugins=["geoalchemy2"],
            )
        return self._engine

    def _create_session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(self.engine)
        return self._session_factory

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = self._create_session_factory()
        return self._session_factory

    @contextmanager
    def explicit_commit_session(self) -> Generator[Session, None, None]:
        """
        Issue out a context manager for the session and expect EXPLICIT commits.
        """
        with self.session_factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    @contextmanager
    def auto_commit_session(self) -> Generator[Session, None, None]:
        """
        Issue out a context manager for the session and autocommit the entire transaction.
        """
        with self.session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def health_check(self):
        try:
            with self.session_factory() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception:
            return False

    def close(self):
        if self.engine:
            self.engine.dispose()
            self.logger.info("Successfully closed")
        self._engine = None
        self._session_factory = None
