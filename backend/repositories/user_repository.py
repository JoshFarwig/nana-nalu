import logging
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.config import APISettings
from core.exceptions.users import UserNotFoundError
from utils.password import hash_password
from models.user_model import User


class AsyncUserRepository:
    def __init__(self, session: AsyncSession, settings: APISettings):
        self.session = session
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def add(self, user_data: dict) -> User:
        """
        Add a new user to the session.

        If user_data contains a 'password' field, it will be automatically hashed.
        To provide a pre-hashed password, use 'hashed_password' field instead.
        """
        user_data_copy = user_data.copy()

        # handle password hashing
        if "password" in user_data_copy:
            plain_password = user_data_copy.pop("password")
            user_data_copy["password"] = hash_password(
                plain_password, rounds=self.settings.api.bcrypt_rounds
            )
        elif "hashed_password" in user_data_copy:
            # if already hashed, just rename the field
            user_data_copy["password"] = user_data_copy.pop("hashed_password")

        user = User(**user_data_copy)
        self.session.add(user)
        return user

    async def get_by_id(self, user_id: int) -> User:
        """
        Get user by ID.

        Args:
            user_id: The ID of the user

        Returns:
            User model instance

        Raises:
            UserNotFoundError: If user doesn't exist
        """
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(user_id, field="id")

        return user

    async def get_by_email(self, email: str) -> User:
        """
        Get user by email address.

        Args:
            email: The email address of the user

        Returns:
            User model instance

        Raises:
            UserNotFoundError: If user doesn't exist
        """
        result = await self.session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(email, field="email")

        return user

    async def get_by_username(self, username: str) -> User:
        """
        Get user by username.

        Args:
            username: The username of the user

        Returns:
            User model instance

        Raises:
            UserNotFoundError: If user doesn't exist
        """
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(username, field="username")

        return user

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[User]:
        result = await self.session.execute(select(User).offset(skip).limit(limit))
        return result.scalars().all()

    async def update(self, user_id: int, user_data: dict) -> User:
        """
        Update user by ID.

        Note: For updating passwords, use update_password() method instead.
        This method will NOT automatically hash password fields.

        Args:
            user_id: The ID of the user
            user_data: Dictionary of fields to update

        Returns:
            Updated User model instance

        Raises:
            UserNotFoundError: If user doesn't exist
        """
        user = await self.get_by_id(user_id)

        for key, value in user_data.items():
            if hasattr(user, key):
                setattr(user, key, value)

        return user

    async def update_password(self, user_id: int, new_password: str) -> User:
        """
        Update a user's password by ID.

        The password will be automatically hashed before storage.

        Args:
            user_id: The ID of the user
            new_password: The new plaintext password (will be hashed)

        Returns:
            Updated User model instance

        Raises:
            UserNotFoundError: If user doesn't exist
        """
        user = await self.get_by_id(user_id)

        user.password = hash_password(
            new_password, rounds=self.settings.api.bcrypt_rounds
        )
        return user

    async def delete(self, user_id: int) -> bool:
        """
        Delete a user by ID.

        Args:
            user_id: The ID of the user

        Returns:
            True if deleted successfully

        Raises:
            UserNotFoundError: If user doesn't exist
        """
        user = await self.get_by_id(user_id)
        await self.session.delete(user)
        return True

    async def exists_by_email(self, email: str) -> bool:
        result = await self.session.execute(select(User.id).where(User.email == email))
        return result.scalar_one_or_none() is not None

    async def exists_by_username(self, username: str) -> bool:
        result = await self.session.execute(
            select(User.id).where(User.username == username)
        )
        return result.scalar_one_or_none() is not None


class SyncUserRepository:
    def __init__(self, session: Session, settings: APISettings):
        self.session = session
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def add(self, user_data: dict) -> User:
        """
        Add a new user to the session.

        If user_data contains a 'password' field, it will be automatically hashed.
        To provide a pre-hashed password, use 'hashed_password' field instead.
        """
        user_data_copy = user_data.copy()

        # handle password hashing
        if "password" in user_data_copy:
            plain_password = user_data_copy.pop("password")
            user_data_copy["password"] = hash_password(
                plain_password, rounds=self.settings.api.bcrypt_rounds
            )
        elif "hashed_password" in user_data_copy:
            # if already hashed, just rename the field
            user_data_copy["password"] = user_data_copy.pop("hashed_password")

        user = User(**user_data_copy)
        self.session.add(user)
        return user

    def get_by_username(self, username: str) -> User:
        """
        Get user by username.

        Args:
            username: The username of the user

        Returns:
            User model instance

        Raises:
            UserNotFoundError: If user doesn't exist
        """
        result = self.session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(username, field="username")

        return user
