from pydantic import Field, SecretStr


from core.configs.database_config import DatabaseConfig
from core.database import AsyncDatabaseManager


class DatabaseBlock:
    _block_type_name = "Database Configuration"
    _logo_url = "https://cdn.simpleicons.org/postgresql"

    host: str = Field(description="Database host")
    port: int = Field(default=5432, description="Database port")
    database: str = Field(description="Database name")
    username: str = Field(description="Database username")
    password: SecretStr = Field(description="Database password")
    pool_size: int = Field(default=5, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max overflow")

    def get_manager(self) -> AsyncDatabaseManager:
        """Create manager instance from block config."""
        return AsyncDatabaseManager(DatabaseConfig())
