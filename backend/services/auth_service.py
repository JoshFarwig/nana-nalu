from datetime import timedelta
import logging

from pydantic import SecretStr, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import APISettings
from core.exceptions.users import UserAlreadyExistsError, UserNotFoundError
from core.exceptions.auth import (
    AccountDisabledError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

from core.redis import AsyncRedisManager
from core.security import SecurityManager

from models.user_model import User
from services.email_service import EmailService
from services.magic_link_service import MagicLinkService

from repositories.account_tier_repository import AsyncAccountTierRepository
from repositories.user_repository import AsyncUserRepository

from schemas.auth_schema import (
    DisabledAccount,
    EnabledAccount,
    UserEmailLogin,
    UserUsernameLogin,
    AuthTokens,
)
from schemas.magic_link_schema import PendingRegistrationPayload, PasswordResetPayload
from schemas.user_schema import UserCreate

from utils.password import hash_password, verify_password

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        redis_manager: AsyncRedisManager,
        security_manager: SecurityManager,
        email_service: EmailService,
        magic_link_service: MagicLinkService,
        user_repo: AsyncUserRepository,
        tier_repo: AsyncAccountTierRepository,
        session: AsyncSession,
        settings: APISettings,
    ):
        self.redis_manager = redis_manager
        self.security_manager = security_manager
        self.email_service = email_service
        self.magic_link_service = magic_link_service
        self.user_repo = user_repo
        self.tier_repo = tier_repo
        self.session = session
        self.settings = settings.api

    def _get_refresh_token_key(self, refresh_token_hash: str) -> str:
        return f"auth:refresh:{refresh_token_hash}"

    def _get_user_sessions_key(self, user_id: int) -> str:
        return f"auth:sessions:{user_id}"

    async def _issue_auth_token_pair(self, user: User) -> AuthTokens:
        access_token = self.security_manager.create_access_token(
            user_id=user.id,
            email=user.email,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            tier=user.tier.display_name,
            tier_id=user.tier.id,
            is_admin=user.is_admin,
        )
        refresh_token = self.security_manager.create_refresh_token()
        refresh_token_hash = self.security_manager.hash_refresh_token(refresh_token)
        ttl = timedelta(days=self.settings.refresh_token_expire_days)

        refresh_key = self._get_refresh_token_key(refresh_token_hash)
        await self.redis_manager.client.setex(
            name=refresh_key,
            time=int(ttl.total_seconds()),
            value=str(user.id),
        )

        sessions_key = self._get_user_sessions_key(user.id)
        await self.redis_manager.client.sadd(sessions_key, refresh_token_hash)  # type: ignore https://github.com/redis/redis-py/issues/3169
        await self.redis_manager.client.expire(sessions_key, ttl)

        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_type="bearer",
        )

    async def register(self, user_data: UserCreate) -> None:
        """Store pending registration in Redis and send verification email.

        No DB row is created until verify_email_and_create_user() is called.
        """
        if await self.user_repo.exists_by_email(user_data.email):
            raise UserAlreadyExistsError("email", user_data.email)
        if await self.user_repo.exists_by_username(user_data.username):
            raise UserAlreadyExistsError("username", user_data.username)

        password_hash = hash_password(user_data.password, self.settings.bcrypt_rounds)

        payload = PendingRegistrationPayload(
            email=user_data.email,
            username=user_data.username,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            password_hash=password_hash,
        )

        magic_token = await self.magic_link_service.create_link(
            "email_verification",
            payload=payload.model_dump(),
            ttl=timedelta(minutes=self.settings.email_verification_expire_minutes),
        )

        await self.email_service.send_email_verification(
            magic_token,
            to_email=user_data.email,
            username=user_data.username,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
        )

        logger.info(
            "Verification email sent for pending registration",
            extra={"email": user_data.email, "username": user_data.username},
        )

    async def verify_email_and_create_user(self, token: str) -> AuthTokens:

        data = await self.magic_link_service.validate_link(
            link_type="email_verification", token=token
        )

        payload = PendingRegistrationPayload(**data)

        if await self.user_repo.exists_by_email(payload.email):
            raise UserAlreadyExistsError("email", payload.email)
        if await self.user_repo.exists_by_username(payload.username):
            raise UserAlreadyExistsError("username", payload.username)

        tier = await self.tier_repo.get_by_name("free")
        user = await self.user_repo.create_from_pending_registration(tier.id, payload)
        await self.session.flush()

        user.tier = tier
        tokens = await self._issue_auth_token_pair(user)
        await self.session.commit()

        return tokens

    async def login(self, login_data: UserEmailLogin | UserUsernameLogin) -> AuthTokens:
        credential_type = (
            "email" if isinstance(login_data, UserEmailLogin) else "username"
        )

        try:
            match login_data:
                case UserEmailLogin(email=user_email, password=user_password):
                    user = await self.user_repo.get_by_email_with_tier(user_email)

                case UserUsernameLogin(username=user_username, password=user_password):
                    user = await self.user_repo.get_by_username_with_tier(user_username)

        except UserNotFoundError:
            raise InvalidCredentialsError(credential_type=credential_type)

        if not verify_password(user_password, user.password):
            raise InvalidCredentialsError(credential_type=credential_type)

        if not user.is_active:
            raise AccountDisabledError()

        tokens = await self._issue_auth_token_pair(user)

        logger.info(
            "User logged in successfully",
            extra={"user_id": user.id, "username": user.username, "email": user.email},
        )

        return tokens

    async def logout(self, refresh_token: str):
        refresh_token_hash = self.security_manager.hash_refresh_token(refresh_token)
        refresh_key = self._get_refresh_token_key(refresh_token_hash)

        user_id_str = await self.redis_manager.client.get(refresh_key)
        if user_id_str:
            user_id = int(user_id_str)

            sessions_key = self._get_user_sessions_key(user_id)
            await self.redis_manager.client.srem(sessions_key, refresh_token_hash)  # type: ignore https://github.com/redis/redis-py/issues/3169

            logger.info(
                "User logged out successfully",
                extra={"user_id": user_id},
            )

        await self.redis_manager.client.delete(refresh_key)

    async def refresh(self, refresh_token: str) -> AuthTokens:
        """Rotates refresh token on each use. Old token is invalidated."""
        old_refresh_token_hash = self.security_manager.hash_refresh_token(refresh_token)
        old_refresh_key = self._get_refresh_token_key(old_refresh_token_hash)

        user_id_str = await self.redis_manager.client.get(old_refresh_key)
        if not user_id_str:
            raise InvalidRefreshTokenError()

        user_id = int(user_id_str)
        user = await self.user_repo.get_by_id_with_tier(user_id)

        tokens = await self._issue_auth_token_pair(user)

        await self.redis_manager.client.delete(old_refresh_key)
        sessions_key = self._get_user_sessions_key(user_id)
        await self.redis_manager.client.srem(sessions_key, old_refresh_token_hash)  # type: ignore https://github.com/redis/redis-py/issues/3169

        logger.info(
            "Access token refreshed",
            extra={"user_id": user.id, "username": user.username},
        )

        return tokens

    async def revoke_all_sessions(self, user_id: int):

        sessions_key = self._get_user_sessions_key(user_id)

        token_hashes = await self.redis_manager.client.smembers(sessions_key)  # type: ignore https://github.com/redis/redis-py/issues/3169

        if token_hashes:
            keys_to_delete = [
                self._get_refresh_token_key(token_hash) for token_hash in token_hashes
            ]
            await self.redis_manager.client.delete(*keys_to_delete)

            await self.redis_manager.client.delete(sessions_key)

            logger.warning(
                "All user sessions revoked",
                extra={"user_id": user_id, "session_count": len(token_hashes)},
            )

            return len(token_hashes)

        return 0

    async def enable_account(self, user_id: int) -> EnabledAccount:

        user = await self.user_repo.get_by_id(user_id)

        if user.is_active:
            logger.info(
                "User account is already enabled",
                extra={
                    "user_id": user_id,
                    "email": user.email,
                    "username": user.username,
                },
            )

            return EnabledAccount(
                user_id=user_id,
                email=user.email,
                username=user.username,
            )
        else:
            await self.user_repo.update(user_id, user_data={"is_active": True})
            await self.session.commit()

            logger.info(
                "user account enabled",
                extra={
                    "user_id": user_id,
                    "email": user.email,
                    "username": user.username,
                },
            )

            return EnabledAccount(
                user_id=user_id,
                email=user.email,
                username=user.username,
            )

    async def disable_account(self, user_id: int) -> DisabledAccount:
        """Disables account and revokes all active sessions."""

        user = await self.user_repo.get_by_id(user_id)

        if not user.is_active:
            logger.warning(
                "User account is already disabled",
                extra={
                    "user_id": user_id,
                    "email": user.email,
                    "username": user.username,
                },
            )

            return DisabledAccount(
                user_id=user_id,
                email=user.email,
                username=user.username,
                sessions_revoked=0,
            )
        else:
            await self.user_repo.update(user_id, user_data={"is_active": False})
            await self.session.commit()

            logger.warning(
                "User account disabled",
                extra={
                    "user_id": user_id,
                    "email": user.email,
                    "username": user.username,
                },
            )

            sessions_revoked = await self.revoke_all_sessions(user_id)

            return DisabledAccount(
                user_id=user_id,
                email=user.email,
                username=user.username,
                sessions_revoked=sessions_revoked,
            )

    async def reset_password(self, token: str, new_password: SecretStr):
        """Complete password reset via magic link token.

        Order matters: commit password change before revoking sessions so the
        user isn't locked out if session cleanup fails.
        """
        payload = await self.magic_link_service.validate_link("password_reset", token)
        password_reset_payload = PasswordResetPayload(**payload)

        user = await self.user_repo.update_password(
            password_reset_payload.user_id, new_password.get_secret_value()
        )

        await self.session.commit()
        await self.revoke_all_sessions(user.id)

        logger.info(
            "Password reset completed, all sessions revoked",
            extra={
                "user_id": user.id,
                "email": user.email,
                "username": user.username,
            },
        )

    async def request_password_reset_email(self, email: EmailStr):

        user = await self.user_repo.get_by_email(email)

        payload = PasswordResetPayload(user_id=user.id, email=user.email)

        magic_token = await self.magic_link_service.create_link(
            "password_reset",
            payload=payload.model_dump(),
            ttl=timedelta(minutes=self.settings.password_reset_expire_minutes),
        )

        await self.email_service.send_passsword_reset(
            magic_token, to_email=user.email, username=user.username
        )

        logger.info(
            f"Sent reset password email to user email: {user.email}",
            extra={
                "user_id": user.id,
                "email": user.email,
                "username": user.username,
            },
        )
