from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from core.config import APISettings
from core.exceptions.users import UserNotFoundError
from schemas.user_schema import UserCreate, UserUpdate
from utils.password import hash_password
from models.user_model import User

if TYPE_CHECKING:
    from schemas.magic_link_schema import PendingRegistrationPayload

logger = logging.getLogger(__name__)


class AsyncUserRepository:
    def __init__(self, session: AsyncSession, settings: APISettings):
        self.session = session
        self.settings = settings

    async def exists_by_email(self, email: str) -> bool:
        result = await self.session.execute(select(User.id).where(User.email == email))
        return result.scalar_one_or_none() is not None

    async def exists_by_username(self, username: str) -> bool:
        result = await self.session.execute(
            select(User.id).where(User.username == username)
        )
        return result.scalar_one_or_none() is not None

    async def get_by_id(self, user_id: int) -> User:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(user_id, field="id")

        return user

    async def get_by_email(self, email: str) -> User:
        result = await self.session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(email, field="email")

        return user

    async def get_by_username(self, username: str) -> User:
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(username, field="username")

        return user

    async def get_by_email_with_tier(self, email: str) -> User:
        """Eagerly loads tier. Use in auth flows where tier is needed for tokens."""
        result = await self.session.execute(
            select(User).where(User.email == email).options(selectinload(User.tier))
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(email, field="email")

        return user

    async def get_by_username_with_tier(self, username: str) -> User:
        """Eagerly loads tier. Use in auth flows where tier is needed for tokens."""
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
        """Eagerly loads tier. Use in auth flows where tier is needed for tokens."""
        result = await self.session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.tier))
        )
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(user_id, field="id")

        return user

    async def get_all(self, skip: int = 0, limit: int = 100) -> Sequence[User]:
        result = await self.session.execute(select(User).offset(skip).limit(limit))
        return result.scalars().all()

    async def create(self, user_data: dict) -> User:
        """Internal/admin method. Password is hashed automatically."""
        user_data["password"] = hash_password(
            user_data["password"], self.settings.api.bcrypt_rounds
        )

        user = User(**user_data)
        self.session.add(user)
        return user

    async def create_from_pending_registration(
        self, tier_id: int, payload: PendingRegistrationPayload
    ) -> User:
        """Password already hashed from pending registration, no re-hash."""

        user = User(
            tier_id=tier_id,
            username=payload.username,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            password=payload.password_hash,
        )
        self.session.add(user)
        return user

    async def update(self, user_id: int, user_data: dict) -> User:
        """Internal/admin update. For passwords, use update_password() instead."""
        user = await self.get_by_id(user_id)

        for key, value in user_data.items():
            if hasattr(user, key):
                setattr(user, key, value)

        return user

    async def update_profile(self, user_id: int, user_data: UserUpdate) -> User:
        data = user_data.model_dump(exclude_unset=True)
        return await self.update(user_id, user_data=data)

    async def update_password(self, user_id: int, new_password: str) -> User:
        """Accepts plaintext, hashes automatically before storage."""
        user = await self.get_by_id(user_id)
        user.password = hash_password(
            new_password, rounds=self.settings.api.bcrypt_rounds
        )
        return user

    async def delete(self, user_id: int) -> bool:
        user = await self.get_by_id(user_id)
        await self.session.delete(user)
        return True


class SyncUserRepository:
    def __init__(self, session: Session, settings: APISettings):
        self.session = session
        self.settings = settings

    def get_by_username(self, username: str) -> User:
        result = self.session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError(username, field="username")

        return user

    def create(self, user_data: dict) -> User:
        """Internal/admin method. Password is hashed automatically."""
        user_data["password"] = hash_password(
            user_data["password"], self.settings.api.bcrypt_rounds
        )

        user = User(**user_data)
        self.session.add(user)
        return user
