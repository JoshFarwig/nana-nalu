from pydantic import BaseModel, EmailStr


# ============================================================================
# Internal DTOs (Redis Storage - Magic Link Payloads)
# ============================================================================


class PendingRegistrationPayload(BaseModel):
    """Payload for deferred registration (stored in Redis until email verification)."""

    email: EmailStr
    username: str
    first_name: str
    last_name: str
    password_hash: str  # bcrypt hash — safe to store in Redis with TTL


class EmailVerificationPayload(BaseModel):
    """Payload for email verification magic links (serialized to Redis)"""

    user_id: int


class PasswordResetPayload(BaseModel):
    """Payload for password reset magic links (serialized to Redis)"""

    user_id: int
    email: EmailStr
