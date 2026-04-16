"""
Models package.

Phase 3 will add forecast/buoy ORM models if needed. Current refactor uses
raw SQL via Alembic + JSONB payloads, so no per-table SQLAlchemy models yet.
"""

from models.base_model import Base  # noqa: F401
from models.mixins import TimestampMixin  # noqa: F401

__all__ = [
    "Base",
    "TimestampMixin",
]
