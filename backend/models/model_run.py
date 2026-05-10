"""
ModelRun tracks each forecast ingest execution.

Used for idempotency, status tracking, and acts as the metadata for forecast data lookups.
Prefect workers check this before processing a new run.
"""

import enum
from datetime import datetime
from sqlalchemy import DOUBLE_PRECISION, DateTime, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from models.base_model import Base
from models.mixins import TimestampMixin


class IngestStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


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
    # run_time = analysis time of model run (time model pulled data) or
    # time forecast was processed/ingested into nana-nalu
    run_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # ingest_status: Mapped[IngestStatus] = mapped_column(
    #     Enum(IngestStatus, name="ingeststatus")
    # )
