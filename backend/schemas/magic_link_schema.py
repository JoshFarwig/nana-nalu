from pydantic import BaseModel, EmailStr


# ============================================================================
# Internal DTOs (Redis Storage - Magic Link Payloads)
# ============================================================================


class EmailVerificationPayload(BaseModel):
    """Payload for email verification magic links (serialized to Redis)"""

    user_id: int


class PasswordResetPayload(BaseModel):
    """Payload for password reset magic links (serialized to Redis)"""

    user_id: int
    email: EmailStr
