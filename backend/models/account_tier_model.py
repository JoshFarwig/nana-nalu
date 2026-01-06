from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column


from models.base_model import Base
from models.mixins import TimestampMixin


class AccountTier(Base, TimestampMixin):
    __tablename__ = "account_tiers"

    __table_args__ = (
        CheckConstraint(
            "max_active_spots IS NULL AND spot_quota IS NULL OR max_active_spots <= spot_quota",
            name="max_active_spots_within_quota",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # tier types free + kokua
    name: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str]

    spots_quota: Mapped[int]
    max_active_spots: Mapped[int]

    # crew limits
    max_crews: Mapped[int]
    max_crew_members: Mapped[int]

    price_monthly_cents: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


# default tier definitions used during seeding
DEFAULT_TIERS = {
    "free": {
        "name": "free",
        "display_name": "Free",
        "spot_quota": 5,
        "max_active_spots": 3,
        "max_crews": 1,
        "max_crew_members": 3,
        "price_monthly_cents": 0,
    },
    # TODO: after adjusting free tier w/ test users,
    # consider what some valid 5 a month value options would be?
}
