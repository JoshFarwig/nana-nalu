"""
ModelRun tracks each forecast ingest execution.

Used for idempotency, status tracking, and acts as the metadata for forecast data lookups.
Prefect workers check this before processing a new run.
"""

from datetime import datetime
from sqlalchemy import DOUBLE_PRECISION, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from models.base_model import Base
from models.mixins import TimestampMixin

#     op.execute(
#   "SELECT create_hypertable('forecast_data', by_range('valid_time'), if_not_exists => TRUE)"
# )


class ModelRun(Base, TimestampMixin):
    __tablename__ = "model_runs"
    __table_args__ = (
        UniqueConstraint(
            "provider", "model", "region", "run_time", name="uq_model_run_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(20))
    region: Mapped[str] = mapped_column(String(50))

    lat_origin: Mapped[float] = mapped_column(DOUBLE_PRECISION)
    lon_origin: Mapped[float] = mapped_column(DOUBLE_PRECISION)
    lat_res: Mapped[float] = mapped_column(DOUBLE_PRECISION)
    lon_res: Mapped[float] = mapped_column(DOUBLE_PRECISION)
    lat_count: Mapped[int] = mapped_column()
    lon_count: Mapped[int] = mapped_column()
    horizon_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # run_time = analysis time published by the source model (e.g. NOMADS cycle time)
    # if no analysis time exists, populates same value as created_at
    run_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @hybrid_property
    def lat_max(self) -> float:
        return self.lat_origin + (self.lat_count - 1) * self.lat_res

    @hybrid_property
    def lon_max(self) -> float:
        return self.lon_origin + (self.lon_count - 1) * self.lon_res

    @hybrid_method
    def contains(self, lat: float, lon: float) -> bool:
        return (
            (self.lat_origin <= lat)
            & (lat <= self.lat_max)
            & (self.lon_origin <= lon)
            & (lon <= self.lon_max)
        )
