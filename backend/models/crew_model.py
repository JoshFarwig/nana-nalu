from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base
from models.mixins import TimestampMixin


if TYPE_CHECKING:
    from models.user_model import User
    from models.surf_spot_model import SurfSpot
    from models.crew_member_model import CrewMember


class Crew(Base, TimestampMixin):
    """
    A crew is a group of users who share surf spots and observations.

    Member limits are derived dynamically from the owner's tier:
        crew.owner.tier.max_crew_members

    This means if an owner downgrades their tier, the crew limit shrinks.
    Downgrade logic (handled in service layer) removes newest members first.
    """

    __tablename__ = "crews"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # relationships
    owner: Mapped["User"] = relationship(back_populates="owned_crews")
    members: Mapped[list["CrewMember"]] = relationship(
        back_populates="crew", cascade="all, delete-orphan"
    )
    spots: Mapped[list["SurfSpot"]] = relationship(back_populates="crew")

    @property
    def max_members(self) -> int:
        """Derive max members from owner's tier."""
        return self.owner.tier.max_crew_members

    @property
    def member_count(self) -> int:
        """Current number of members in the crew."""
        return len(self.members)
