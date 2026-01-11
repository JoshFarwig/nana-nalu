from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:
    from models.account_tier_model import AccountTier
    from models.surf_spot_model import SurfSpot
    from models.spot_observation_model import SpotObservation
    from models.crew_model import Crew
    from models.crew_member_model import CrewMember


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tier_id: Mapped[int] = mapped_column(ForeignKey("account_tiers.id"))

    username: Mapped[str] = mapped_column(String(20), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    first_name: Mapped[str] = mapped_column(String(25))
    last_name: Mapped[str] = mapped_column(String(50))
    bio: Mapped[str | None] = mapped_column(String(100), default=None)
    location: Mapped[str | None] = mapped_column(String(50), default=None)

    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    # NOTE: Consider for future use how to handle SQLalchemy's lazy loading
    # for relationships. Either specify on relation to selectin or via query
    # https://stackoverflow.com/questions/74252768/missinggreenlet-greenlet-spawn-has-not-been-called

    tier: Mapped["AccountTier"] = relationship()
    owned_crews: Mapped[list["Crew"]] = relationship(back_populates="owner")
    crew_memberships: Mapped[list["CrewMember"]] = relationship(back_populates="user")
    spots: Mapped[list["SurfSpot"]] = relationship(back_populates="created_by")
    observations: Mapped[list["SpotObservation"]] = relationship(back_populates="user")
