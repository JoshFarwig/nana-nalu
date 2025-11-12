from pydantic import BaseModel, SecretStr
from urllib.parse import quote


class RedisConfig(BaseModel):
    """Configuration for Redis Client"""

    host: str | None
    port: int | None
    password: SecretStr

    # redis databases
    broker_db: int = 0
    cache_db: int = 1

    # redis conn scheme (can be redis://, rediss://, or unix://)
    # https://redis.readthedocs.io/en/stable/examples/connection_examples.html#Connecting-to-Redis-instances-by-specifying-a-URL-scheme.
    conn_scheme: str = "redis"

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

    def get_broker_url(self) -> str:
        """Build connection url to the celery broker database in the Redis Server"""
        return f"{self.conn_scheme}://:{self._get_encoded_password()}@{self.host}:{self.port}/{self.broker_db}"

    def get_cache_url(self) -> str:
        """Build connection url to the app cache database in the Redis Server"""
        return f"{self.conn_scheme}://:{self._get_encoded_password()}@{self.host}:{self.port}/{self.cache_db}"
