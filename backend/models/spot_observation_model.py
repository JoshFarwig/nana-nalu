from typing import TYPE_CHECKING
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base_model import Base

if TYPE_CHECKING:
    from models.user_model import User
    from models.surf_spot_model import SurfSpot


class WindConditionEnum(Enum):
    ON_SHORE = "on_shore"
    OFF_SHORE = "off_shore"
    NONE = "none"


class TideHeightEnum(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SpotObservation(Base):
    __tablename__ = "spot_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    spot_id: Mapped[int] = mapped_column(ForeignKey("surf_spots.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Base fields
    observation_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )
    rating: Mapped[int | None] = mapped_column(Integer)  # 1-5
    wave_height_observed: Mapped[float | None] = mapped_column(Float)  # ft
    wind_condition_observed: Mapped[WindConditionEnum | None] = mapped_column(
        SQLEnum(WindConditionEnum, name="wind_condition_observed_enum"), nullable=True
    )
    tide_height_observed: Mapped[TideHeightEnum | None] = mapped_column(
        SQLEnum(TideHeightEnum, name="tide_height_observed_enum"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(500))

    # Relationships
    spot: Mapped["SurfSpot"] = relationship(back_populates="observations")
    user: Mapped["User"] = relationship(back_populates="observations")
