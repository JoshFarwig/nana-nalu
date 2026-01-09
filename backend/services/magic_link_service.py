from datetime import timedelta
import hashlib
import json
import secrets
from typing import Literal

from core.config import APISettings
from core.redis import AsyncRedisManager
from core.exceptions.magic_links import (
    MagicLinkInvalidError,
)


MagicLinkType = Literal["email_verification", "password_reset", "crew_invite"]


class MagicLinkService:
    def __init__(
        self,
        redis_manager: AsyncRedisManager,
        settings: APISettings,
    ):
        self.redis_manager = redis_manager
        self.settings = settings.api

    def _generate_token(self) -> str:
        """Generate 256-bit token"""
        return secrets.token_urlsafe(32)

    def _hash_token(self, token: str) -> str:
        """Hash token before redis storage"""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _get_redis_key(self, link_type: MagicLinkType, hashed_token: str) -> str:
        """Generate redis key for storing magic link tokens"""
        return f"magic_link:{link_type}:{hashed_token}"

    async def create_link(
        self,
        link_type: MagicLinkType,
        payload: dict,
        ttl: timedelta,
    ) -> str:
        """
        Create a magic link token and store in Redis.

        Args:
            link_type: Token category (e.g., "email_verification", "password_reset", "crew_invite")
            payload: Data to associate with token (user_id, email, etc.)
            ttl: How long until token expires

        Returns:
            Raw token (send this to user, never store it)
        """

        token = self._generate_token()
        hashed_token = self._hash_token(token)
        redis_key = self._get_redis_key(link_type, hashed_token)

        data = json.dumps({"type": link_type, **payload})

        await self.redis_manager.client.setex(
            redis_key, time=int(ttl.total_seconds()), value=data
        )

        return token

    async def validate_link(
        self, link_type: MagicLinkType, token: str, consume: bool = True
    ) -> dict:
        """
        Validate token with consumption or not.

        Non consumption useful for preview flows where you need to check validity
        before user is authenticated (e.g., crew invite preview).

        Else, consume for valid verification flows

        Args:
            token: Raw token from user
            link_type: Required magic link type
            consume: whenever or not to consume the token

        Returns:
            Payload data associated with token

        Raises:
            MagicLinkInvalidError: Token not found or expired
        """

        hashed_token = self._hash_token(token)
        redis_key = self._get_redis_key(link_type, hashed_token)

        if consume:
            data = await self.redis_manager.client.getdel(redis_key)
        else:
            data = await self.redis_manager.client.get(redis_key)

        if not data:
            raise MagicLinkInvalidError()

        return json.loads(data)

    async def invalidate_link(self, link_type: MagicLinkType, token: str) -> bool:
        """
        Invalidate a magic link token (for cleanup/revocation).

        Used for compensating transactions when registration or other flows fail
        after creating a magic link but before committing the operation.

        Args:
            link_type: Token category (must match what was used in create_link)
            token: Raw token to invalidate

        Returns:
            True if token was deleted, False if it didn't exist
        """
        hashed_token = self._hash_token(token)
        redis_key = self._get_redis_key(link_type, hashed_token)

        deleted_count = await self.redis_manager.client.delete(redis_key)
        return deleted_count > 0
