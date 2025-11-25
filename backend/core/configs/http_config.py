from pydantic import BaseModel, ConfigDict


class HTTPConfig(BaseModel):
    """Configuration for HTTP clients"""

    model_config = ConfigDict(frozen=True)

    user_agent: str = "Agent"  # TODO: Make user_agent for http client
    timeout: float = 30.0

    max_attempts: int = 3

    # async http manager settings
    # used for fastapi
    async_max_connections: int = 20
    async_max_keepalive_connections: int = 10

    # NOTE: adjust sync settings based on the average task load
    # currently only considering NWPS provider and
    # one other provider task

    # sync http manager settings
    # used for celery workers
    sync_max_connections: int = 2
    sync_max_keepalive_connections: int = 0
    sync_keepalive_expiry: float = 5.0

    retry_base_delay: float = 10.0
    retry_max_delay: float = 60.0
    retry_backoff_factor: float = 2.0
