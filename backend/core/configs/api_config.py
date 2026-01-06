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
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    bcrypt_rounds: int = 12
