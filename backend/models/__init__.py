"""
Models package - imports all SQLAlchemy models.

Import order is critical for Alembic migrations to properly resolve
foreign key relationships. Models must be imported in dependency order:
models with no dependencies first, then models that reference them.
"""

from models.base_model import Base  # noqa: F401
from models.mixins import TimestampMixin  # noqa: F401

# Import in dependency order
from models.account_tier_model import AccountTier  # noqa: F401
from models.user_model import User  # noqa: F401
from models.crew_model import Crew  # noqa: F401
from models.crew_member_model import CrewMember  # noqa: F401
from models.surf_spot_model import SurfSpot  # noqa: F401
from models.spot_observation_model import SpotObservation  # noqa: F401

__all__ = [
    "Base",
    "TimestampMixin",
    "AccountTier",
    "User",
    "Crew",
    "CrewMember",
    "SurfSpot",
    "SpotObservation",
]
