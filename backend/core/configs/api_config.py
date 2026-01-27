from pydantic import BaseModel, ConfigDict, SecretStr


class APIConfig(BaseModel):
    """Configuration for API"""

    model_config = ConfigDict(frozen=True)

    name: str = "nānā-nalu-api"
    version: str = "0.1.0"

    log_level: str = "INFO"
    debug: bool = False

    admin_username: SecretStr
    admin_password: SecretStr
    admin_email: SecretStr
    admin_name: str = "Admin"

    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"

    # token / magic link expirations
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    email_verification_expire_minutes: int = 30
    password_reset_expire_minutes: int = 15
    crew_invite_expire_hours: int = 24

    bcrypt_rounds: int = 12

    resend_api_key: SecretStr
    app_url: str  # front-end url for token redirect

    # TODO: register valid from_email w/ domain?
    # for now using my email
    from_email: str = "noreply@nananalu.com"
