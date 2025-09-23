from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user_model import User


class UserRepository:
    """Repository for User database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, user_data: dict) -> User:
        """Add a new user to the session (no commit)"""
        user = User(**user_data)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """Get user by username."""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[User]:
        """Get all users with pagination."""
        result = await self.session.execute(select(User).offset(skip).limit(limit))
        return result.scalars().all()

    async def update(self, user_id: int, user_data: dict) -> User | None:
        """Update user by ID (no commit)."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        for key, value in user_data.items():
            if hasattr(user, key):
                setattr(user, key, value)

        await self.session.flush()
        return user

    async def delete(self, user_id: int) -> bool:
        """Delete user by ID (no commit)."""
        user = await self.get_by_id(user_id)
        if not user:
            return False

        await self.session.delete(user)
        await self.session.flush()
        return True

    async def exists_by_email(self, email: str) -> bool:
        """Check if user exists by email."""
        result = await self.session.execute(select(User.id).where(User.email == email))
        return result.scalar_one_or_none() is not None

    async def exists_by_username(self, username: str) -> bool:
        """Check if user exists by username."""
        result = await self.session.execute(
            select(User.id).where(User.username == username)
        )
        return result.scalar_one_or_none() is not None
