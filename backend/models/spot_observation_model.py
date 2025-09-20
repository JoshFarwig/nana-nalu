from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base_model import Base
from .surf_spot_model import SurfSpot
from .user_model import User


class SpotObservation(Base):
    __tablename__ = "spot_observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    spot_id: Mapped[int] = mapped_column(ForeignKey("surf_spots.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    observation_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now(timezone.utc)
    )
    rating: Mapped[int | None] = mapped_column(Integer)
    wave_height_observed: Mapped[float | None] = mapped_column(Float)
    conditions: Mapped[str | None] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(String(500))

    # Relationships
    spot: Mapped["SurfSpot"] = relationship(back_populates="observations")
    user: Mapped["User"] = relationship(back_populates="observations")
