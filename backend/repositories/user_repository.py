import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from core.config import APISettings
from core.exceptions.users import UserNotFoundError
from schemas.user_schema import UserCreate, UserUpdate
from utils.password import hash_password
from models.user_model import User

logger = logging.getLogger(__name__)


class AsyncUserRepository:
    def __init__(self, session: AsyncSession, settings: APISettings):
        self.session = session
        self.settings = settings

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

    async def get_by_id(self, user_id: int) -> User:
        """Get user by ID."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(user_id, field="id")

        return user

    async def get_by_email(self, email: str) -> User:
        """Get user by email."""
        result = await self.session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(email, field="email")

        return user

    async def get_by_username(self, username: str) -> User:
        """Get user by username."""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(username, field="username")

        return user

    async def get_by_email_with_tier(self, email: str) -> User:
        """
        Get user by email with tier relationship eagerly loaded.

        Use this in auth flows (login/register/refresh) where tier info is needed
        for token generation.
        """
        result = await self.session.execute(
            select(User).where(User.email == email).options(selectinload(User.tier))
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(email, field="email")

        return user

    async def get_by_username_with_tier(self, username: str) -> User:
        """
        Get user by username with tier relationship eagerly loaded.

        Use this in auth flows (login/register/refresh) where tier info is needed
        for token generation.
        """
        result = await self.session.execute(
            select(User)
            .where(User.username == username)
            .options(selectinload(User.tier))
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(username, field="username")

        return user

    async def get_by_id_with_tier(self, user_id: int) -> User:
        """
        Get user by ID with tier relationship eagerly loaded.

        Use this in auth flows (refresh) where tier info is needed
        for token generation.
        """
        result = await self.session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.tier))
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(user_id, field="id")

        return user

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[User]:
        """Get all users with pagination."""
        result = await self.session.execute(select(User).offset(skip).limit(limit))
        return result.scalars().all()

    async def create(self, user_data: dict) -> User:
        """
        Create a new user - internal/admin method.

        Accepts any valid User model fields. Use this for admin operations
        or seeding where you need full control.

        Args:
            user_data: Dictionary of fields to set on the new user
                      Must include: username, email, first_name, last_name, password (hashed), tier_id
                      Optional: bio, location, is_admin, verified, etc.

        Returns:
            Created User model instance
        """
        # hash password on every user create
        user_data["password"] = hash_password(
            user_data["password"], self.settings.api.bcrypt_rounds
        )

        user = User(**user_data)
        self.session.add(user)
        return user

    async def create_from_registration(
        self,
        tier_id: int,
        user_data: UserCreate,
    ) -> User:
        """
        Create a new user from registration - public-facing method.

        Automatically sets: is_admin=False (enforced by not allowing it in dict).
        User provides: username, email, first_name, last_name, bio, location, password.

        Args:
            tier_id: The account tier ID (typically free tier for new registrations)
            user_data: Validated UserCreate schema with user registration data

        Returns:
            Created User model instance

        Raises:
            UserAlreadyExistsError: If username or email already exists (handled by caller)
        """
        data = user_data.model_dump(exclude_unset=True)
        data["tier_id"] = tier_id
        return await self.create(user_data=data)

    async def update(self, user_id: int, user_data: dict) -> User:
        """
        Update user by ID - for admin / internal use

        Note: For updating passwords, use update_password() method instead.

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

    async def update_profile(self, user_id: int, user_data: UserUpdate) -> User:
        """
        Update user by ID - for public facing user use

        Args:
            user_id: The ID of the user
            user_data: Dictionary of fields to update

        Returns:
            Updated User model instance

        Raises:
            UserNotFoundError: If user doesn't exist
        """

        data = user_data.model_dump(exclude_unset=True)
        return await self.update(user_id, user_data=data)

    async def update_verified(self, user_id: int, verified: bool) -> User:
        """
        Update the user's verified status for email verification.

        Args:
            user_id: The ID of the user
            verified: The new state of verified
        Returns:
            Updated User model instance

        Raises:
            UserNotFoundError: If user doesn't exist
        """
        user = await self.get_by_id(user_id)
        user.verified = verified
        user.verified_at = datetime.now(timezone.utc) if verified else None
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


class SyncUserRepository:
    def __init__(self, session: Session, settings: APISettings):
        self.session = session
        self.settings = settings

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

    def create(self, user_data: dict) -> User:
        """
        Create a new user - internal/admin method (sync version).

        Accepts any valid User model fields. Password will be automatically hashed.
        Use this for admin operations or seeding where you need full control.

        Args:
            user_data: Dictionary of fields to set on the new user
                      Must include: username, email, first_name, last_name, password (plaintext), tier_id
                      Optional: bio, location, is_admin, verified, etc.

        Returns:
            Created User model instance
        """
        # hash password on every user create (defensive programming)
        user_data["password"] = hash_password(
            user_data["password"], self.settings.api.bcrypt_rounds
        )

        user = User(**user_data)
        self.session.add(user)
        return user
