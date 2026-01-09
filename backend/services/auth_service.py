from datetime import timedelta
import logging

from pydantic import SecretStr, EmailStr

from core.config import APISettings
from core.exceptions.users import UserAlreadyExistsError, UserNotFoundError
from core.exceptions.auth import (
    AccountDisabledError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

from core.redis import AsyncRedisManager
from core.saga import SagaContext
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
from schemas.magic_link_schema import EmailVerificationPayload, PasswordResetPayload
from schemas.user_schema import UserCreate

from utils.password import verify_password

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
        settings: APISettings,
    ):
        self.redis_manager = redis_manager
        self.security_manager = security_manager
        self.email_service = email_service
        self.magic_link_service = magic_link_service
        self.user_repo = user_repo
        self.tier_repo = tier_repo
        self.settings = settings.api

    def _get_refresh_token_key(self, refresh_token_hash: str) -> str:
        """Build Redis key for refresh token storage."""
        return f"auth:refresh:{refresh_token_hash}"

    def _get_user_sessions_key(self, user_id: int) -> str:
        """Build Redis key for tracking user's active sessions."""
        return f"auth:sessions:{user_id}"

    async def _revoke_refresh_token(self, refresh_token: str, user_id: int):
        """
        Revoke a single refresh token (for cleanup/compensating transactions).

        Used to clean up tokens when operations fail after token issuance.
        Silently handles errors to avoid masking the original failure.

        Args:
            refresh_token: The refresh token to revoke
            user_id: The user ID associated with the token
        """
        try:
            refresh_token_hash = self.security_manager.hash_refresh_token(refresh_token)
            refresh_key = self._get_refresh_token_key(refresh_token_hash)

            # remove from active sessions set
            sessions_key = self._get_user_sessions_key(user_id)
            await self.redis_manager.client.srem(sessions_key, refresh_token_hash)  # type: ignore

            # delete the refresh token
            await self.redis_manager.client.delete(refresh_key)

            logger.info(
                "Refresh token revoked during cleanup",
                extra={"user_id": user_id},
            )
        except Exception as cleanup_error:
            # don't raise - we're already in error handling, just log it
            logger.error(
                "Failed to revoke refresh token during cleanup",
                extra={"user_id": user_id, "error": str(cleanup_error)},
            )

    async def _issue_auth_token_pair(self, user: User) -> AuthTokens:
        """Generate and store access + refresh tokens for a user."""
        # generate tokens
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

        # store refresh token in redis
        refresh_key = self._get_refresh_token_key(refresh_token_hash)
        await self.redis_manager.client.setex(
            name=refresh_key,
            time=int(ttl.total_seconds()),
            value=str(user.id),
        )

        # track active session for revocation capability
        sessions_key = self._get_user_sessions_key(user.id)
        await self.redis_manager.client.sadd(sessions_key, refresh_token_hash)  # type: ignore https://github.com/redis/redis-py/issues/3169
        await self.redis_manager.client.expire(sessions_key, ttl)

        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_type="bearer",
        )

    async def register(self, user_data: UserCreate) -> AuthTokens:
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
        user = await self.user_repo.create_from_registration(
            tier_id=tier.id, user_data=user_data
        )
        await self.user_repo.session.flush()

        # orchestrate multi-step registration with automatic rollback on failure
        async with SagaContext() as saga:
            # step 1: generate and store tokens
            tokens = await self._issue_auth_token_pair(user)
            saga.add_rollback(self._revoke_refresh_token, tokens.refresh_token, user.id)

            # step 2: create magic token for verification
            magic_token = await self.magic_link_service.create_link(
                "email_verification",
                payload=EmailVerificationPayload(user_id=user.id).model_dump(),
                ttl=timedelta(minutes=self.settings.email_verification_expire_minutes),
            )
            saga.add_rollback(
                self.magic_link_service.invalidate_link,
                "email_verification",
                magic_token,
            )

            # step 3: send verification email (if this fails, steps 1-2 auto-rollback)
            await self.email_service.send_email_verification(
                magic_token,
                to_email=user.email,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )

            # commit user to db once all operations succeed
            await self.user_repo.session.commit()

        logger.info(
            "User registered successfully and verification email sent",
            extra={"user_id": user.id, "username": user.username},
        )

        return tokens

    async def verify_email(self, token: str):
        """Verify a user's email account"""

        # validate and consume magic link for email verification
        data = await self.magic_link_service.validate_link(
            link_type="email_verification", token=token
        )
        payload = EmailVerificationPayload(**data)

        user = await self.user_repo.update_verified(
            user_id=payload.user_id, verified=True
        )

        # commit verification
        await self.user_repo.session.commit()

        logger.info(
            "User account verified via email",
            extra={
                "user_id": user.id,
                "email": user.email,
                "username": user.username,
                "verified_at": user.verified_at,
            },
        )

    async def login(self, login_data: UserEmailLogin | UserUsernameLogin) -> AuthTokens:
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

        # ensure verified email
        if not user.verified:
            raise EmailNotVerifiedError()

        # ensure account is active:
        if not user.is_active:
            raise AccountDisabledError()

        # generate and store tokens
        tokens = await self._issue_auth_token_pair(user)

        logger.info(
            "User logged in successfully",
            extra={"user_id": user.id, "username": user.username},
        )

        return tokens

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

    async def refresh(self, refresh_token: str) -> AuthTokens:
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
        tokens = await self._issue_auth_token_pair(user)

        # invalidate old refresh token
        await self.redis_manager.client.delete(old_refresh_key)
        sessions_key = self._get_user_sessions_key(user_id)
        await self.redis_manager.client.srem(sessions_key, old_refresh_token_hash)  # type: ignore https://github.com/redis/redis-py/issues/3169

        logger.info(
            "Access token refreshed",
            extra={"user_id": user.id, "username": user.username},
        )

        return tokens

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

    async def enable_account(self, user_id: int) -> EnabledAccount:
        """Enable a users account"""

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
            await self.user_repo.session.commit()

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
        """Disable account and revoke all user sessons"""

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
            await self.user_repo.session.commit()

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
        """
        Complete password reset using magic link token.

        Validates token, updates password, commits, then revokes all sessions for security.
        Order matters: commit password change before revoking sessions.
        """
        # validate and consume token
        payload = await self.magic_link_service.validate_link("password_reset", token)
        password_reset_payload = PasswordResetPayload(**payload)

        # update password in DB
        user = await self.user_repo.update_password(
            password_reset_payload.user_id, new_password.get_secret_value()
        )

        # commit password change
        await self.user_repo.session.commit()

        # revoke all sessions AFTER commit succeeds (force re-login with new password)
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
        """Send a reset password email request"""

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
