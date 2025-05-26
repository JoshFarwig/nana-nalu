from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import os

# TODO Look into how fastapi handles configurations and environment variables
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/mydb"
)

# Async Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=True,
    pool_size=10,  # cntrols how many connections in pool
    max_overflow=5,  # extra connections allowed temporarily
    pool_timeout=30,  # seconds to wait before error if pool is full
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


# Base class for declarative models
class Base(DeclarativeBase):
    pass
