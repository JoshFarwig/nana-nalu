from sqlalchemy.orm import Mapped, mapped_column


from models.base_model import Base
from models.mixins import TimestampMixin


class AccountTier(Base, TimestampMixin):
    __tablename__ = "account_tiers"

    id: Mapped[int] = mapped_column(primary_key=True)

    # tier types free + kokua
    name: Mapped[str] = mapped_column(unique=True)
    display_name: Mapped[str]

    # spot pooling, None or NULL = unlimited
    active_spot_quota: Mapped[int]
    max_archived_spots: Mapped[int]

    # crew limits
    max_crews: Mapped[int]
    max_crew_members: Mapped[int]

    price_monthly_cents: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)
