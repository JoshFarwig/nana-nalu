from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from models.user_model import User


class UserRepository:
    """Repository for User database operations."""

    # Password hashing context
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def __init__(self, session: AsyncSession):
        self.session = session

    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash."""
        return self.pwd_context.verify(plain_password, hashed_password)

    async def add(self, user_data: dict) -> User:
        """
        Add a new user to the session (no commit).

        If user_data contains a 'password' field, it will be automatically hashed.
        To provide a pre-hashed password, use 'hashed_password' field instead.
        """
        user_data_copy = user_data.copy()

        # Handle password hashing
        if "password" in user_data_copy:
            plain_password = user_data_copy.pop("password")
            user_data_copy["password"] = self.hash_password(plain_password)
        elif "hashed_password" in user_data_copy:
            # If already hashed, just rename the field
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
