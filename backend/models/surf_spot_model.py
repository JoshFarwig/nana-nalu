from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry
from .base_model import Base

if TYPE_CHECKING:
    from .user_model import User
    from .spot_observation_model import SpotObservation


class SurfSpot(Base):
    __tablename__ = "surf_spots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped["User"] = relationship(back_populates="spots")
    observations: Mapped[list["SpotObservation"]] = relationship(
        back_populates="spot", cascade="all, delete-orphan"
    )
