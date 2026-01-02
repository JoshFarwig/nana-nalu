from typing import TYPE_CHECKING
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:
    from models.account_tier_model import AccountTier
    from models.surf_spot_model import SurfSpot
    from models.spot_observation_model import SpotObservation


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tier_id: Mapped[int] = mapped_column(ForeignKey("account_tiers.id"))

    first_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # if there is enough of a support backing behind the app, may expand limits and
    # create kokua tier w/ subscription model

    # Relationships
    # NOTE: Consider for future use how to handle SQLalchemy's lazy loading
    # for relationships. Either specify on relation to selectin or via query
    # https://stackoverflow.com/questions/74252768/missinggreenlet-greenlet-spawn-has-not-been-called

    tier: Mapped["AccountTier"] = relationship()
    spots: Mapped[list["SurfSpot"]] = relationship(back_populates="created_by")
    observations: Mapped[list["SpotObservation"]] = relationship(back_populates="user")
