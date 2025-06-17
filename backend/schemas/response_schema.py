"""Response envelope schemas for consistent API responses."""

from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel

T = TypeVar("T")  # Data type for data


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response envelope."""

    success: bool = True
    message: str = "Success"
    data: T


class ErrorResponse(BaseModel):
    """Standard error response envelope."""

    success: bool = False
    message: str
    error_code: Optional[str] = None
    details: Optional[dict] = None


class ListResponse(BaseModel, Generic[T]):
    """Response envelope for simple lists."""

    success: bool = True
    message: str = "Success"
    data: List[T]


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    total: int
    page: int
    limit: int
    pages: int
    has_next: bool = False
    has_prev: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        # Auto-calculate navigation flags
        self.has_next = self.page < self.pages
        self.has_prev = self.page > 1


class PaginatedListResponse(BaseModel, Generic[T]):
    """Response envelope for paginated lists."""

    success: bool = True
    message: str = "Success"
    data: List[T]
    meta: PaginationMeta


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str  # "healthy" | "unhealthy"
    database: str  # "connected" | "disconnected" | "error"
    version: str
    timestamp: str
    error: Optional[str] = None
