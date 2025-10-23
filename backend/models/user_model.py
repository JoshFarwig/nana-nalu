from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base_model import Base

if TYPE_CHECKING:
    from .surf_spot_model import SurfSpot
    from .spot_observation_model import SpotObservation


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    # NOTE: Consider for future use how to handle SQLalchemy's lazy loading
    # for relationships. Either specify on relation to selectin or via query
    # https://stackoverflow.com/questions/74252768/missinggreenlet-greenlet-spawn-has-not-been-called

    spots: Mapped[list["SurfSpot"]] = relationship(back_populates="created_by")
    observations: Mapped[list["SpotObservation"]] = relationship(back_populates="user")
