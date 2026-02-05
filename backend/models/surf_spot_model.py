from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from models.base_model import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:
    from models.user_model import User
    from models.crew_model import Crew
    from models.condition_profile_model import ConditionProfile


class SurfSpot(Base, TimestampMixin):
    __tablename__ = "surf_spots"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    crew_id: Mapped[int | None] = mapped_column(
        ForeignKey("crews.id", ondelete="SET NULL"), default=None
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    region: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    # relationships
    created_by: Mapped["User"] = relationship(back_populates="spots")
    crew: Mapped["Crew | None"] = relationship(back_populates="spots")
    condition_profiles: Mapped[list["ConditionProfile"]] = relationship(
        back_populates="spot", cascade="all, delete-orphan"
    )
