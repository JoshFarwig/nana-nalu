"""
forecast_data (core data table, doesn't need ORM)

High-volume hypertable storing grid-point forecasts.
TimescaleDB hypertable conversion handled in Alembic migration.
Write path: bulk insert via Core insert().values([...])
Read path: Core select(), frontend snaps click coords to grid, exact lookup
on (model_run_id, lat, lon) via composite btree.
"""

from sqlalchemy import (
    DOUBLE_PRECISION,
    DateTime,
    ForeignKey,
    Index,
    Table,
    Column,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from models.base_model import Base

forecast_data = Table(
    "forecast_data",
    Base.metadata,
    Column("ingested_at", DateTime(timezone=True), server_default=func.now()),
    Column("valid_time", DateTime(timezone=True), nullable=False),
    Column("lat", DOUBLE_PRECISION, nullable=False),
    Column("lon", DOUBLE_PRECISION, nullable=False),
    Column(
        "model_run_id", ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    ),
    Column("payload", JSONB, nullable=False),
    Index("ix_forecast_data_lookup", "model_run_id", "lat", "lon", "valid_time"),
)
