from pydantic import BaseModel, ConfigDict, SecretStr
from urllib.parse import quote


class DatabaseConfig(BaseModel):
    """Configuration for SQLAlchemy Engine"""

    model_config = ConfigDict(frozen=True)

    # sqlalchemy connection address
    host: str | None
    port: str | None
    username: str
    password: SecretStr
    name: str

    # sqlalchemy engine dialect / drivers
    dialect: str = "postgresql"
    async_driver: str = "asyncpg"
    sync_driver: str = "psycopg2"

    # async engine config
    # set higher pool size / overflow depending on estimated traffic
    async_pool_size: int = 10
    async_max_overflow: int = 20
    async_pool_timeout: int = 30
    async_pool_pre_ping: bool = True

    def _get_encoded_password(self) -> str:
        """Process any special characters in the db password for SQLAlchemy"""
        return quote(self.password.get_secret_value())

    def get_async_url(self) -> str:
        """Build async database connection url"""
        return (
            f"{self.dialect}+{self.async_driver}://{self.username}:{self._get_encoded_password()}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    def get_sync_url(self) -> str:
        """Build sync database connection url"""
        return (
            f"{self.dialect}+{self.sync_driver}://{self.username}:{self._get_encoded_password()}"
            f"@{self.host}:{self.port}/{self.name}"
        )
