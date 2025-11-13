from pydantic import BaseModel


class HTTPConfig(BaseModel):
    """Configuration for HTTP clients"""

    user_agent: str = "Agent"  # TODO: Make user_agent for http client
    timeout: float = 30.0

    max_retries: int = 3
    max_connections: int = 20
    max_keepalive_connections: int = 10

    retry_base_delay: float = 10.0
    retry_max_delay: float = 60.0
    retry_backoff_factor: float = 2.0
