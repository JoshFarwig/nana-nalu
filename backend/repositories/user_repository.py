from typing import Sequence
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core import BaseConfig
from models.user_model import User


class UserRepository:
    """Repository for User database operations."""

    def __init__(self, session: AsyncSession, settings: BaseConfig):
        self.session = session
        self.settings = settings

    # NOTE: this could be moved to a seperate util with DI support?
    # figure out later down the road
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt(rounds=self.settings.api.bcrypt_rounds)
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash."""
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

    def password_needs_rehash(self, hashed_password: str) -> bool:
        """Determine if password needs update (bcrypt_rounds were increased)"""
        try:
            # bcrypt hashes use $version$cost$salt+hash
            parts = hashed_password.split("$")
            current_cost = int(parts[1])
            return current_cost < self.settings.api.bcrypt_rounds
        except (ValueError, IndexError):
            return True

    async def add(self, user_data: dict) -> User:
        """
        Add a new user to the session (no commit).

        If user_data contains a 'password' field, it will be automatically hashed.
        To provide a pre-hashed password, use 'hashed_password' field instead.
        """
        user_data_copy = user_data.copy()

        # handle password hashing
        if "password" in user_data_copy:
            plain_password = user_data_copy.pop("password")
            user_data_copy["password"] = self.hash_password(plain_password)
        elif "hashed_password" in user_data_copy:
            # if already hashed, just rename the field
            user_data_copy["password"] = user_data_copy.pop("hashed_password")

        user = User(**user_data_copy)
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
        """
        Update user by ID (no commit).

        Note: For updating passwords, use update_password() method instead.
        This method will NOT automatically hash password fields.
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        for key, value in user_data.items():
            if hasattr(user, key):
                setattr(user, key, value)

        await self.session.flush()
        return user

    async def update_password(self, user_id: int, new_password: str) -> User | None:
        """
        Update a user's password by ID (no commit).

        The password will be automatically hashed before storage.
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None

        user.password = self.hash_password(new_password)
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
