from pydantic import BaseModel, SecretStr


class APIConfig(BaseModel):
    """Configuration for API"""

    name: str = "nānā_nalu_api"
    version: str = "0.1.0"

    log_level: str = "INFO"
    debug: bool = False

    admin_username: SecretStr
    admin_password: SecretStr
    admin_email: SecretStr

    bcrypt_rounds: int = 12
