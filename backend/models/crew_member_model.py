from typing import TYPE_CHECKING, Literal
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base
from models.mixins import TimestampMixin


if TYPE_CHECKING:
    from models.user_model import User
    from models.crew_model import Crew


CrewRole = Literal["owner", "member"]


class CrewMember(Base, TimestampMixin):
    """
    Join table for crew membership.

    The created_at timestamp (from TimestampMixin) serves as the join date,
    which is used to determine removal order during tier downgrades
    (newest members are removed first - LIFO).
    """

    __tablename__ = "crew_members"

    crew_id: Mapped[int] = mapped_column(
        ForeignKey("crews.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[CrewRole] = mapped_column(String, default="member")

    # relationships
    crew: Mapped["Crew"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="crew_memberships")
