"""
ModelRun tracks each forecast ingest execution.

Used for idempotency, status tracking, and acts as the metadata for forecast data lookups.
Prefect workers check this before processing a new run.
"""

from datetime import datetime
from enum import Enum
from sqlalchemy import DateTime, String, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from models.base_model import Base
from models.mixins import TimestampMixin


class IngestStatus(Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


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
    run_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingest_status: Mapped[IngestStatus] = mapped_column(SQLEnum(IngestStatus))
