import secrets
import hashlib
import logging
import jwt
from datetime import datetime, timedelta, timezone

from core.config import APISettings

logger = logging.getLogger(__name__)


class SecurityManager:
    def __init__(self, settings: APISettings) -> None:
        self.settings = settings.api

    def create_access_token(
        self,
        user_id: int,
        username: str,
        email: str,
        name: str,
        tier: str,
        is_admin: bool,
    ):
        """Create a short-lived JWT acccess token (15mins)"""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.settings.access_token_expire_minutes)

        payload = {
            "sub": str(user_id),
            "username": username,
            "email": email,
            "name": name,
            "tier": tier,
            "is_admin": is_admin,
            "iat": now,
            "exp": expires_at,
        }

        return jwt.encode(
            payload,
            key=self.settings.jwt_secret_key.get_secret_value(),
            algorithm=self.settings.jwt_algorithm,
        )

    def decode_access_token(self, token: str):
        """Decodes an access token, will throw jwt.Error(s) if unable to decode"""

        payload = jwt.decode(
            token,
            key=self.settings.jwt_secret_key.get_secret_value(),
            algorithms=[self.settings.jwt_algorithm],
        )

        return {
            "user_id": payload["sub"],
            "username": payload["username"],
            "email": payload["email"],
            "name": payload["name"],
            "tier": payload["tier"],
            "is_admin": payload["is_admin"],
        }

    def create_hashed_refresh_token(self):
        return self.hash_refresh_token(self.create_refresh_token())

    def create_refresh_token(self):
        """Generate 256-bit random token for Redis storage"""
        return secrets.token_urlsafe(32)

    def hash_refresh_token(self, token: str):
        """Hash token before storing in Redis"""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
