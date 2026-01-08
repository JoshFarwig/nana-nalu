# Magic Link System Implementation Plan (Redis-Based)

## Overview

Implement a unified magic link system for nānā-nalu using **Redis with auto-expiration** that handles:
1. **Email verification** (required before login/crew access)
2. **Password reset** (via email)
3. **Crew invites** (shareable links via iMessage/WhatsApp, not email)

## Goals & Requirements

### Core Requirements
- ✅ Users **cannot login** until email is verified
- ✅ Email verification **auto-logs in** user (issues tokens)
- ✅ Crew operations (create/join) require verified email
- ✅ Crew invites are **shareable links** (copy/paste to messaging apps)
- ✅ Crew invite links work for **both new and existing users**

### Security
- Tokens are hashed in Redis (never stored raw)
- One-time use with `GETDEL` atomic operation
- Cryptographically secure generation (256-bit entropy)
- Type validation prevents token misuse
- Auto-expiration via Redis TTL (no manual cleanup needed)

---

## Architecture

### 1. Redis Storage (No Database)

**Key Patterns:**
```python
# Email verification (24 hour TTL)
magic_link:email_verification:{token_hash} → JSON({
    "type": "email_verification",
    "user_id": 123,
    "email": "user@example.com"
})

# Password reset (1 hour TTL)
magic_link:password_reset:{token_hash} → JSON({
    "type": "password_reset",
    "user_id": 123,
    "email": "user@example.com"
})

# Crew invite (7 day TTL)
magic_link:crew_invite:{token_hash} → JSON({
    "type": "crew_invite",
    "crew_id": 5,
    "crew_name": "Sunset Crew",
    "inviter_user_id": 42,
    "inviter_name": "Josh"
})
```

**Why Redis?**
- ✅ **Auto-cleanup** - TTL handles expiration automatically
- ✅ **Atomic one-time use** - `GETDEL` retrieves and deletes in one operation
- ✅ **Fast** - In-memory reads (<1ms vs 5-10ms database)
- ✅ **Simple** - No migrations, no expired token cleanup
- ✅ **Perfect fit** - Temporary validation state is Redis's sweet spot

### 2. User Model Updates

```python
# backend/models/user_model.py

class User(Base, TimestampMixin):
    # ... existing fields ...

    # Email verification (REQUIRED for login/crews)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Social profile (already exists in your model)
    bio: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(50))

    # Referral tracking (already exists in your model)
    invited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
```

**Migration needed:**
- `email_verified` and `email_verified_at` fields need to be added
- `bio`, `location`, `invited_by_user_id` already exist

---

## Implementation Approach

### Flow 1: Registration + Email Verification

#### Registration (No Tokens Issued)

```python
# backend/api/v1/routes/auth.py

@router.post("/register")
async def register(
    user_data: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
    magic_link_service: MagicLinkService = Depends(get_magic_link_service),
):
    """Register user and send verification email. Does NOT issue tokens."""

    # Create user with email_verified=False
    user = await auth_service.user_repo.create(tier_id=tier.id, user_data=user_data)
    await auth_service.user_repo.session.flush()

    # Send verification email
    await magic_link_service.send_email_verification(
        user_id=user.id,
        user_email=user.email,
        user_name=user.name,
    )

    await auth_service.user_repo.session.commit()

    return SuccessResponse(
        message="Check your email to verify and login.",
        data={"email": user.email, "verification_sent": True}
    )
```

#### Email Verification (Auto-Login)

```python
@router.get("/verify-email")
async def verify_email(
    token: str,
    response: Response,
    magic_link_service: MagicLinkService = Depends(get_magic_link_service),
    auth_service: AuthService = Depends(get_auth_service),
    user_repo: AsyncUserRepository = Depends(get_user_repository),
):
    """Verify email and auto-login user (issue tokens)."""

    # Validate and consume link (atomic GETDEL)
    link_data = await magic_link_service.validate_and_consume_link(
        token=token,
        expected_type="email_verification",
    )

    # Mark as verified
    user = await user_repo.get_by_id_with_tier(link_data["user_id"])
    await user_repo.update(
        user_id=user.id,
        email_verified=True,
        email_verified_at=datetime.now(timezone.utc),
    )
    await user_repo.session.commit()

    # Issue tokens (auto-login)
    tokens = await auth_service._issue_token_pair(user)

    _set_refresh_token_cookie(
        refresh_token=tokens.refresh_token,
        max_age_days=auth_service.settings.refresh_token_expire_days,
        response=response,
    )

    return SuccessResponse(
        message="Email verified! You're logged in. 🎉",
        data={
            "access_token": tokens.access_token,
            "access_token_type": tokens.access_token_type,
        }
    )
```

#### Login (Blocks Unverified)

```python
@router.post("/login")
async def login(
    response: Response,
    user_data: UserEmailLogin | UserUsernameLogin,
    auth_service: AuthService = Depends(get_auth_service),
):
    """Login user. BLOCKS if email not verified."""

    user = await auth_service.user_repo.get_by_email_with_tier(user_data.email)

    # Verify password
    if not verify_password(user_data.password, user.password):
        raise InvalidCredentialsError()

    # Check email verification
    if not user.email_verified:
        raise EmailNotVerifiedError(email=user.email)

    # Issue tokens
    tokens = await auth_service._issue_token_pair(user)

    _set_refresh_token_cookie(
        refresh_token=tokens.refresh_token,
        max_age_days=auth_service.settings.refresh_token_expire_days,
        response=response,
    )

    return SuccessResponse(
        message="Successfully logged in",
        data={
            "access_token": tokens.access_token,
            "access_token_type": tokens.access_token_type,
        }
    )
```

---

### Flow 2: Shareable Crew Invites

#### Create Invite Link (Returns URL, No Email Sent)

```python
# backend/api/v1/routes/crews.py

@router.post("/{crew_id}/invite")
async def create_crew_invite_link(
    crew_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    magic_link_service: MagicLinkService = Depends(get_magic_link_service),
    crew_repo: CrewRepository = Depends(get_crew_repository),
    settings: APISettings = Depends(get_settings),
):
    """Generate shareable crew invite link (copy/paste to iMessage, etc.)."""

    # Verify user is crew member
    crew = await crew_repo.get_by_id(crew_id)
    if not await crew_repo.is_member(crew_id, current_user.id):
        raise InsufficientPermissionsError()

    # Generate link (no target email/user - shareable to anyone)
    token = await magic_link_service.create_crew_invite_link(
        crew_id=crew.id,
        crew_name=crew.name,
        inviter_user_id=current_user.id,
        inviter_name=current_user.name,
    )

    # Build full URL for user to copy
    invite_url = f"{settings.api.app_url}/crews/join?token={token}"

    return SuccessResponse(
        message="Invite link created",
        data={
            "invite_url": invite_url,
            "crew_name": crew.name,
            "expires_in_days": 7,
        }
    )
```

#### Join Crew (Handles New + Existing Users)

```python
@router.get("/join")
async def join_crew_via_link(
    token: str,
    current_user: CurrentUser | None = Depends(get_current_user_optional),
    magic_link_service: MagicLinkService = Depends(get_magic_link_service),
    crew_repo: CrewRepository = Depends(get_crew_repository),
    user_repo: AsyncUserRepository = Depends(get_user_repository),
):
    """
    Join crew via shareable link.

    THREE FLOWS:
    1. Not logged in → return auth_required (frontend handles redirect)
    2. Logged in but email not verified → block with error
    3. Logged in + verified → join crew
    """

    # Validate link (without consuming - need to preview first)
    link_data = await magic_link_service.validate_link_without_consuming(token)

    crew_id = link_data["crew_id"]
    crew_name = link_data["crew_name"]
    inviter_name = link_data["inviter_name"]

    # FLOW 1: Not authenticated
    if not current_user:
        return {
            "action": "auth_required",
            "message": f"{inviter_name} invited you to join {crew_name}",
            "context": {
                "crew_id": crew_id,
                "crew_name": crew_name,
                "invite_token": token,
            }
        }

    # FLOW 2: Email not verified
    if not current_user.email_verified:
        raise EmailNotVerifiedError(email=current_user.email)

    # FLOW 3: Consume link and join crew
    await magic_link_service.consume_link(token)
    await crew_repo.add_member(crew_id, current_user.id)

    # Track referral
    if not current_user.invited_by_user_id:
        await user_repo.update(
            user_id=current_user.id,
            invited_by_user_id=link_data["inviter_user_id"]
        )

    await user_repo.session.commit()

    return SuccessResponse(
        message=f"Welcome to {crew_name}! 🤙",
        data={"crew_id": crew_id, "crew_name": crew_name}
    )
```

---

## Frontend Flow: New User via Crew Invite

### Simplified Approach (No Invite Token to Register)

**Journey:**
1. User clicks invite link → `/crews/join?token=abc123`
2. Backend returns `{action: "auth_required", context: {...}}`
3. Frontend saves invite to localStorage, redirects to `/auth`
4. User registers → backend sends verification email (no tokens issued)
5. Frontend shows "Check your email to verify"
6. User clicks email link → backend verifies email + issues tokens
7. **Frontend checks localStorage for pending invite**
8. **Frontend calls `/crews/join?token=abc123` again (now authenticated)**
9. User joins crew automatically

```typescript
// Step 3: Save invite to localStorage
async function handleInviteLinkClick(token: string) {
  const response = await api.get(`/crews/join?token=${token}`)

  if (response.action === 'auth_required') {
    // Save for later
    localStorage.setItem('pending_crew_invite', JSON.stringify({
      token: token,
      crew_id: response.context.crew_id,
      crew_name: response.context.crew_name,
    }))

    navigate('/auth')
  }
}

// Step 7-8: After email verification, complete invite
async function handleEmailVerification(verificationToken: string) {
  const response = await api.get(`/auth/verify-email?token=${verificationToken}`)

  // Save tokens (user now logged in)
  saveTokens(response.data.access_token)

  // Check for pending invite
  const pendingInvite = JSON.parse(localStorage.getItem('pending_crew_invite'))

  if (pendingInvite) {
    // Complete crew join (now authenticated + verified)
    await api.get(`/crews/join?token=${pendingInvite.token}`)
    localStorage.removeItem('pending_crew_invite')
    navigate(`/crews/${pendingInvite.crew_id}`)
  } else {
    navigate('/dashboard')
  }
}
```

**Why this approach?**
- ✅ Simpler - registration endpoint unchanged
- ✅ Stateless - backend doesn't need to track pending invites
- ✅ Resilient - invite persists even if user closes browser during registration
- ✅ Reusable - same `/crews/join` endpoint for all scenarios

---

## Magic Link Service Core Implementation

```python
# backend/services/magic_link_service.py

import json
import secrets
import hashlib
from datetime import datetime, timedelta, timezone

from core.redis import AsyncRedisManager
from core.exceptions.auth import (
    MagicLinkInvalidError,
    MagicLinkExpiredError,
    MagicLinkTypeError,
)


class MagicLinkService:
    def __init__(
        self,
        redis_manager: AsyncRedisManager,
        email_service: EmailService,
        settings: APISettings,
    ):
        self.redis = redis_manager.client
        self.email_service = email_service
        self.settings = settings

    # ===== TOKEN GENERATION =====

    def _generate_token(self) -> str:
        """Generate 256-bit cryptographically secure token."""
        return secrets.token_urlsafe(32)

    def _hash_token(self, token: str) -> str:
        """Hash token before storing in Redis."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _get_redis_key(self, link_type: str, token_hash: str) -> str:
        """Build Redis key for magic link."""
        return f"magic_link:{link_type}:{token_hash}"

    # ===== EMAIL VERIFICATION =====

    async def send_email_verification(
        self,
        user_id: int,
        user_email: str,
        user_name: str,
    ) -> None:
        """Create email verification link and send email."""
        token = self._generate_token()
        token_hash = self._hash_token(token)

        # Store in Redis with 24h TTL
        key = self._get_redis_key("email_verification", token_hash)
        data = json.dumps({
            "type": "email_verification",
            "user_id": user_id,
            "email": user_email,
        })

        await self.redis.setex(
            name=key,
            time=int(timedelta(hours=24).total_seconds()),
            value=data,
        )

        # Send email
        await self.email_service.send_email_verification(
            to_email=user_email,
            magic_token=token,
            user_name=user_name,
        )

    # ===== PASSWORD RESET =====

    async def send_password_reset(
        self,
        user_id: int,
        user_email: str,
        user_name: str,
    ) -> None:
        """Create password reset link and send email."""
        token = self._generate_token()
        token_hash = self._hash_token(token)

        # Store in Redis with 1h TTL
        key = self._get_redis_key("password_reset", token_hash)
        data = json.dumps({
            "type": "password_reset",
            "user_id": user_id,
            "email": user_email,
        })

        await self.redis.setex(
            name=key,
            time=int(timedelta(hours=1).total_seconds()),
            value=data,
        )

        # Send email
        await self.email_service.send_password_reset(
            to_email=user_email,
            magic_token=token,
            user_name=user_name,
        )

    # ===== CREW INVITES =====

    async def create_crew_invite_link(
        self,
        crew_id: int,
        crew_name: str,
        inviter_user_id: int,
        inviter_name: str,
    ) -> str:
        """Create shareable crew invite (NO EMAIL SENT). Returns raw token."""
        token = self._generate_token()
        token_hash = self._hash_token(token)

        # Store in Redis with 7 day TTL
        key = self._get_redis_key("crew_invite", token_hash)
        data = json.dumps({
            "type": "crew_invite",
            "crew_id": crew_id,
            "crew_name": crew_name,
            "inviter_user_id": inviter_user_id,
            "inviter_name": inviter_name,
        })

        await self.redis.setex(
            name=key,
            time=int(timedelta(days=7).total_seconds()),
            value=data,
        )

        return token

    # ===== VALIDATION =====

    async def validate_link_without_consuming(self, token: str) -> dict:
        """
        Validate link WITHOUT consuming (for preview/auth flows).
        Used when you need to check link validity before authentication.
        """
        token_hash = self._hash_token(token)

        # Try all link types (we don't know which type this token is)
        for link_type in ["email_verification", "password_reset", "crew_invite"]:
            key = self._get_redis_key(link_type, token_hash)
            data_str = await self.redis.get(key)

            if data_str:
                return json.loads(data_str)

        # Token not found in any type
        raise MagicLinkInvalidError()

    async def validate_and_consume_link(
        self,
        token: str,
        expected_type: str,
    ) -> dict:
        """
        Validate link type and consume atomically (GETDEL).
        Used for final validation when processing the link.
        """
        token_hash = self._hash_token(token)
        key = self._get_redis_key(expected_type, token_hash)

        # Atomic get and delete
        data_str = await self.redis.getdel(key)

        if not data_str:
            raise MagicLinkInvalidError()

        data = json.loads(data_str)

        # Verify type matches
        if data.get("type") != expected_type:
            raise MagicLinkTypeError(
                expected=expected_type,
                actual=data.get("type"),
            )

        return data

    async def consume_link(self, token: str) -> dict:
        """
        Consume link without type validation (for crew invites after preview).
        Returns link data.
        """
        token_hash = self._hash_token(token)

        # Try all link types
        for link_type in ["email_verification", "password_reset", "crew_invite"]:
            key = self._get_redis_key(link_type, token_hash)
            data_str = await self.redis.getdel(key)

            if data_str:
                return json.loads(data_str)

        # Already used or never existed
        raise MagicLinkInvalidError()
```

---

## Email Service Setup with Resend

### Configuration

```python
# backend/core/config.py

class APIConfig(BaseModel):
    # ... existing fields ...

    # Email configuration
    resend_api_key: SecretStr
    app_url: str  # e.g., "http://localhost:5173" (dev) or "https://app.nananalu.com" (prod)
    from_email: str = "noreply@nananalu.app"
```

### Email Service Implementation

```python
# backend/services/email_service.py

import resend


class EmailService:
    def __init__(self, settings: APISettings):
        resend.api_key = settings.api.resend_api_key.get_secret_value()
        self.from_email = settings.api.from_email
        self.app_url = settings.api.app_url

    async def send_email_verification(
        self,
        to_email: str,
        magic_token: str,
        user_name: str,
    ):
        """Send email verification link."""
        link = f"{self.app_url}/auth/verify-email?token={magic_token}"

        resend.Emails.send({
            "from": self.from_email,
            "to": [to_email],
            "subject": "Verify your nānā-nalu account",
            "html": f"""
                <h2>Welcome to nānā-nalu! 🌊</h2>
                <p>Hey {user_name}, click below to verify your email:</p>
                <a href="{link}">Verify Email</a>
                <p>This link expires in 24 hours.</p>
            """
        })

    async def send_password_reset(
        self,
        to_email: str,
        magic_token: str,
        user_name: str,
    ):
        """Send password reset link."""
        link = f"{self.app_url}/auth/reset-password?token={magic_token}"

        resend.Emails.send({
            "from": self.from_email,
            "to": [to_email],
            "subject": "Reset your nānā-nalu password",
            "html": f"""
                <h2>Password Reset Request</h2>
                <p>Hey {user_name}, click below to reset your password:</p>
                <a href="{link}">Reset Password</a>
                <p>This link expires in 1 hour.</p>
                <p>If you didn't request this, ignore this email.</p>
            """
        })
```

---

## Dependency Injection Setup

```python
# backend/core/dependencies/services.py

from services.magic_link_service import MagicLinkService
from services.email_service import EmailService


def get_email_service(
    settings: APISettings = Depends(get_settings),
) -> EmailService:
    """Get email service instance."""
    return EmailService(settings=settings)


def get_magic_link_service(
    redis_manager: AsyncRedisManager = Depends(get_async_redis_manager),
    email_service: EmailService = Depends(get_email_service),
    settings: APISettings = Depends(get_settings),
) -> MagicLinkService:
    """Get magic link service instance."""
    return MagicLinkService(
        redis_manager=redis_manager,
        email_service=email_service,
        settings=settings,
    )
```

---

## Exception Definitions

```python
# backend/core/exceptions/auth.py

class MagicLinkInvalidError(AuthenticationError):
    """Raised when magic link is invalid, expired, or already used"""

    def __init__(self, message: str = "Invalid or expired link"):
        super().__init__(
            message=message,
            error_code="magic_link_invalid",
            status_code=HTTPStatus.UNAUTHORIZED,
        )


class MagicLinkTypeError(AuthenticationError):
    """Raised when magic link type doesn't match expected type"""

    def __init__(self, expected: str, actual: str):
        super().__init__(
            message=f"Invalid link type. Expected {expected}, got {actual}",
            error_code="magic_link_type_mismatch",
            status_code=HTTPStatus.UNAUTHORIZED,
            details={"expected": expected, "actual": actual},
        )


class EmailNotVerifiedError(AuthenticationError):
    """Raised when user tries to login without verifying email"""

    def __init__(self, email: str):
        super().__init__(
            message="Please verify your email before logging in. Check your inbox.",
            error_code="email_not_verified",
            status_code=HTTPStatus.UNAUTHORIZED,
            details={"email": email},
        )
```

---

## Implementation Checklist

### Phase 1: Database Migration
- [ ] Create migration for `email_verified` and `email_verified_at` fields
- [ ] Run migration on dev database

### Phase 2: Email Service
- [ ] Sign up for Resend account
- [ ] Add `RESEND_API_KEY`, `APP_URL`, `FROM_EMAIL` to `.env`
- [ ] Install `resend` package: `poetry add resend`
- [ ] Create `backend/services/email_service.py`
- [ ] Add `get_email_service()` to dependencies

### Phase 3: Magic Link Service
- [ ] Create `backend/services/magic_link_service.py`
- [ ] Add `get_magic_link_service()` to dependencies
- [ ] Add exception classes to `core/exceptions/auth.py`

### Phase 4: Auth Flow Updates
- [ ] Update `POST /auth/register` to not issue tokens
- [ ] Update `POST /auth/login` to check `email_verified`
- [ ] Create `GET /auth/verify-email` endpoint (with auto-login)
- [ ] Create `POST /auth/resend-verification` endpoint

### Phase 5: Crew Invites (Future)
- [ ] Create `POST /crews/{id}/invite` endpoint (returns URL)
- [ ] Create `GET /crews/join` endpoint (handles 3 flows)
- [ ] Update crew creation to require verified email

### Phase 6: Frontend Integration (Future)
- [ ] Update registration flow (no tokens expected)
- [ ] Create verification pending page
- [ ] Add localStorage handling for pending invites
- [ ] Implement email verification handler

---

## Security Considerations

✅ **Tokens hashed in Redis** - Raw tokens never stored
✅ **Cryptographically secure generation** - 256-bit entropy via `secrets.token_urlsafe(32)`
✅ **Expiration enforcement** - Redis TTL (24h verification, 7d invites, 1h reset)
✅ **One-time use** - `GETDEL` atomic operation prevents replay attacks
✅ **Type validation** - Can't use crew invite token for email verification
✅ **Email verification required** - Prevents spam accounts from accessing crews
✅ **No database bloat** - Redis auto-cleans expired links

---

## Redis Key Expiration Times

| Link Type | TTL | Reasoning |
|-----------|-----|-----------|
| Email Verification | 24 hours | User should verify within a day |
| Password Reset | 1 hour | Security-sensitive, short window |
| Crew Invite | 7 days | Shareable links need longer validity |

---

## Future Enhancements

- [ ] Rate limiting on verification email sends (prevent spam)
- [ ] Email templates with better styling (React Email or MJML)
- [ ] "Copy link" button with success feedback for crew invites
- [ ] Share sheet integration for mobile PWA
- [ ] Invite link preview (show crew photo/stats before auth)
- [ ] Optional analytics logging (track invite creation/usage in DB separately)
