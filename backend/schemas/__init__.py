"""Schemas module exports."""

# Response envelopes - used across all endpoints
from .response_schema import (
    SuccessResponse,
    ErrorResponse,
    ListResponse,
    PaginationMeta,
)

# Domain-specific schemas
from .user_schema import (
    UserBase,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserLogin,
)

__all__ = [
    # Response envelopes
    "SuccessResponse",
    "ErrorResponse",
    "ListResponse",
    "PaginationMeta",
    # User schemas
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserLogin",
]
