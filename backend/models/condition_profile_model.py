from typing import TYPE_CHECKING
from sqlalchemy import Boolean, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from models.base_model import Base
from models.mixins import TimestampMixin

from schemas.condition_profile_schema import ProviderConditionEntry

if TYPE_CHECKING:
    from models.user_model import User
    from models.surf_spot_model import SurfSpot


class ConditionProfile(Base, TimestampMixin):
    __tablename__ = "condition_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    spot_id: Mapped[int] = mapped_column(
        ForeignKey("surf_spots.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    name: Mapped[str] = mapped_column(String(100))
    conditions: Mapped[list[ProviderConditionEntry]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    spot: Mapped["SurfSpot"] = relationship(back_populates="condition_profiles")
    created_by: Mapped["User"] = relationship(back_populates="condition_profiles")
