from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.base_model import Base


if TYPE_CHECKING:
    from models.user_model import User


class Crew(Base):
    __tablename__ = "crews"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    name: Mapped[str] = mapped_column(String(25))
    max_size: Mapped[int]

    members: Mapped[list["User"]] = relationship()
    creator: Mapped["User"] = relationship()
