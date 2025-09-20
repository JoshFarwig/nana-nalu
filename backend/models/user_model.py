from typing import Optional, Union, List
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base_model import Base
from .surf_spot_model import SurfSpot
from .spot_observation_model import SpotObservation


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    spots: Mapped[list["SurfSpot"]] = relationship(back_populates="created_by")
    observations: Mapped[list["SpotObservation"]] = relationship(
        back_populates="observations"
    )
