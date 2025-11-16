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

    bcrypt_rounds: int = 12
