from typing import TYPE_CHECKING
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base_model import Base

if TYPE_CHECKING:
    from models.surf_spot_model import SurfSpot


class SurflineSpot(Base):
    __tablename__ = "surfline_spots"

    # composite primary key
    surfline_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    spot_id: Mapped[int] = mapped_column(ForeignKey("surf_spots.id"), primary_key=True)

    spot: Mapped["SurfSpot"] = relationship(back_populates="surfline_spot")
