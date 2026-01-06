import logging

from core.config import APISettings
from core.exceptions.users import UserAlreadyExistsError, UserNotFoundError
from core.exceptions.auth import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

from core.redis import AsyncRedisManager
from core.security import SecurityManager

from repositories.account_tier_repository import AsyncAccountTierRepository
from repositories.user_repository import AsyncUserRepository

from schemas.auth_schema import UserEmailLogin, UserUsernameLogin, Tokens
from schemas.user_schema import UserCreate

from utils.password import verify_password

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        redis_manager: AsyncRedisManager,
        security_manager: SecurityManager,
        user_repo: AsyncUserRepository,
        tier_repo: AsyncAccountTierRepository,
        settings: APISettings,
    ):
        self.redis_manager = redis_manager
        self.security_manager = security_manager
        self.user_repo = user_repo
        self.tier_repo = tier_repo
        self.settings = settings.api

    def _get_refresh_token_key(self, refresh_token_hash: str) -> str:
        """Build Redis key for refresh token storage."""
        return f"auth:refresh:{refresh_token_hash}"

    def _get_user_sessions_key(self, user_id: int) -> str:
        """Build Redis key for tracking user's active sessions."""
        return f"auth:sessions:{user_id}"

    async def _issue_token_pair(self, user) -> Tokens:
        """Generate and store access + refresh tokens for a user."""
        # generate tokens
        access_token = self.security_manager.create_access_token(
            user_id=user.id,
            email=user.email,
            username=user.username,
            name=user.name,
            tier=user.tier.display_name,
            tier_id=user.tier.id,
            is_admin=user.is_admin,
        )
        refresh_token = self.security_manager.create_refresh_token()
        refresh_token_hash = self.security_manager.hash_refresh_token(refresh_token)
        ttl_seconds = self.settings.refresh_token_expire_days * 24 * 60 * 60

        # store refresh token in redis
        refresh_key = self._get_refresh_token_key(refresh_token_hash)
        await self.redis_manager.client.setex(
            name=refresh_key,
            time=ttl_seconds,
            value=str(user.id),
        )

        # track active session for revocation capability
        sessions_key = self._get_user_sessions_key(user.id)
        await self.redis_manager.client.sadd(sessions_key, refresh_token_hash)  # type: ignore https://github.com/redis/redis-py/issues/3169
        await self.redis_manager.client.expire(sessions_key, ttl_seconds)

        return Tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_type="bearer",
        )

    async def register(self, user_data: UserCreate):
        """Register a new user and return access tokens."""

        # check if user exists
        if await self.user_repo.exists_by_email(user_data.email):
            raise UserAlreadyExistsError("email", user_data.email)
        if await self.user_repo.exists_by_username(user_data.username):
            raise UserAlreadyExistsError("username", user_data.username)

        # TODO: in the future, add tier application logic here, but for now, all users
        # are created with a free tier
        tier = await self.tier_repo.get_by_name("free")

        # create new user, flush for access to id
        user = await self.user_repo.create(tier_id=tier.id, user_data=user_data)
        await self.user_repo.session.flush()

        # generate and store tokens
        token_response = await self._issue_token_pair(user)

        # commit user to db
        await self.user_repo.session.commit()

        logger.info(
            "User registered successfully",
            extra={"user_id": user.id, "username": user.username},
        )

        return token_response

    async def login(self, login_data: UserEmailLogin | UserUsernameLogin):
        """Authenticate user and return access tokens."""

        # determine credential type for error messages
        credential_type = (
            "email" if isinstance(login_data, UserEmailLogin) else "username"
        )

        # retrieve user based on login method
        try:
            match login_data:
                case UserEmailLogin(email=user_email, password=user_password):
                    user = await self.user_repo.get_by_email_with_tier(user_email)

                case UserUsernameLogin(username=user_username, password=user_password):
                    user = await self.user_repo.get_by_username_with_tier(user_username)

        except UserNotFoundError:
            raise InvalidCredentialsError(credential_type=credential_type)

        # verify password
        if not verify_password(user_password, user.password):
            raise InvalidCredentialsError(credential_type=credential_type)

        # generate and store tokens
        token_response = await self._issue_token_pair(user)

        logger.info(
            "User logged in successfully",
            extra={"user_id": user.id, "username": user.username},
        )

        return token_response

    async def logout(self, refresh_token: str):
        """Logout the user and remove their refresh token."""

        refresh_token_hash = self.security_manager.hash_refresh_token(refresh_token)
        refresh_key = self._get_refresh_token_key(refresh_token_hash)

        # get user_id before deleting token
        user_id_str = await self.redis_manager.client.get(refresh_key)
        if user_id_str:
            user_id = int(user_id_str)

            # remove token from user's active sessions set
            sessions_key = self._get_user_sessions_key(user_id)
            await self.redis_manager.client.srem(sessions_key, refresh_token_hash)  # type: ignore https://github.com/redis/redis-py/issues/3169

            logger.info(
                "User logged out successfully",
                extra={"user_id": user_id},
            )

        # delete the refresh token
        await self.redis_manager.client.delete(refresh_key)

    async def refresh(self, refresh_token: str):
        """Refresh access token using refresh token with rotation."""

        # validate old refresh token
        old_refresh_token_hash = self.security_manager.hash_refresh_token(refresh_token)
        old_refresh_key = self._get_refresh_token_key(old_refresh_token_hash)

        user_id_str = await self.redis_manager.client.get(old_refresh_key)
        if not user_id_str:
            raise InvalidRefreshTokenError()

        user_id = int(user_id_str)
        user = await self.user_repo.get_by_id_with_tier(user_id)

        # issue new token pair (creates new refresh token)
        token_response = await self._issue_token_pair(user)

        # invalidate old refresh token
        await self.redis_manager.client.delete(old_refresh_key)
        sessions_key = self._get_user_sessions_key(user_id)
        await self.redis_manager.client.srem(sessions_key, old_refresh_token_hash)  # type: ignore https://github.com/redis/redis-py/issues/3169

        logger.info(
            "Access token refreshed",
            extra={"user_id": user.id, "username": user.username},
        )

        return token_response

    async def revoke_all_sessions(self, user_id: int):
        """Revoke all active sessions for a user (e.g., password reset, account compromise)."""

        sessions_key = self._get_user_sessions_key(user_id)

        # get all refresh token hashes for this user
        token_hashes = await self.redis_manager.client.smembers(sessions_key)  # type: ignore https://github.com/redis/redis-py/issues/3169

        if token_hashes:
            # delete all refresh tokens
            keys_to_delete = [
                self._get_refresh_token_key(token_hash) for token_hash in token_hashes
            ]
            await self.redis_manager.client.delete(*keys_to_delete)

            # delete the sessions set
            await self.redis_manager.client.delete(sessions_key)

            logger.warning(
                "All user sessions revoked",
                extra={"user_id": user_id, "session_count": len(token_hashes)},
            )

            return len(token_hashes)

        return 0
