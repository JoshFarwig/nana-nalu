from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")  # generic type for data


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response envelope."""

    success: bool = True
    message: str = "Success"
    data: T


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    success: bool = False
    message: str
    error_code: str | None = None
    details: dict | None = None


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str  # "healthy" | "unhealthy"
    database: str  # "connected" | "disconnected" | "error"
    version: str
    timestamp: str
    error: str | None = None
