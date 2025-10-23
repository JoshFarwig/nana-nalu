from pydantic import BaseModel, SecretStr, computed_field
from urllib.parse import quote


class RedisConfig(BaseModel):
    """Configuration for Redis Client"""

    host: str | None
    port: int | None
    password: SecretStr

    # redis databases
    broker_db: int = 0
    cache_db: int = 1

    # async redis manager settings
    async_max_connections: int = 8
    async_connect_timeout: int = 5
    async_socket_timeout: int = 2

    # general client settings
    decode_responses: bool = True
    retry_on_timeout: bool = True

    def _get_encoded_password(self) -> str:
        """Process any special characters in the db password for Redis"""
        return quote(self.password.get_secret_value())

    @computed_field
    @property
    def broker_url(self) -> SecretStr:
        """Build connection url to the celery broker database in the Redis Server"""
        url = f"redis//:{self._get_encoded_password()}@{self.host}:{self.port}/{self.broker_db}"
        return SecretStr(url)

    @computed_field
    @property
    def cache_url(self) -> SecretStr:
        """Build connection url to the app cache database in the Redis Server"""
        url = f"redis//:{self._get_encoded_password()}@{self.host}:{self.port}/{self.cache_db}"
        return SecretStr(url)
