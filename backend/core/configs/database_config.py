from pydantic import BaseModel, SecretStr, computed_field
from urllib.parse import quote


class DatabaseConfig(BaseModel):
    """Configuration for SQLAlchemy Engine"""

    # SQLAlchemy connection address
    host: str | None
    port: str | None
    username: str
    password: SecretStr
    name: str

    # postgres engine drivers
    async_driver: str = "asyncpg"
    sync_driver: str = "psycopg2"

    # async SQLAlchemy engine config
    # # set higher pool size / overflow depending on estimated traffic
    async_pool_size: int = 3
    async_max_overflow: int = 5
    async_pool_timeout: int = 30
    async_pool_pre_ping: bool = True

    def _get_encoded_password(self) -> str:
        """Process any special characters in the db password for SQLAlchemy"""
        return quote(self.password.get_secret_value())

    @computed_field
    @property
    def async_url(self) -> SecretStr:
        """Build async database connection url"""
        url = (
            f"postgresql+{self.async_driver}://{self.username}:{self._get_encoded_password()}"
            f"@{self.host}:{self.port}/{self.name}"
        )
        return SecretStr(url)

    @computed_field
    @property
    def sync_url(self) -> SecretStr:
        """Build sync database connection url"""
        url = (
            f"postgresql+{self.sync_driver}://{self.username}:{self._get_encoded_password()}"
            f"@{self.host}:{self.port}/{self.name}"
        )
        return SecretStr(url)
