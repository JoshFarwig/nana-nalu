from pydantic import BaseModel, ConfigDict, SecretStr


class APIConfig(BaseModel):
    """Configuration for API"""

    model_config = ConfigDict(frozen=True)

    name: str = "nānā-nalu-api"
    version: str = "0.1.0"

    log_level: str = "INFO"
    debug: bool = False

    # retained for /admin health check (Phase 5 may drop or repurpose)
    admin_username: SecretStr
    admin_password: SecretStr
