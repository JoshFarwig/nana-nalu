"""
forecast_data (core data table, doesn't need ORM)

High-volume hypertable storing grid-point forecasts.
TimescaleDB hypertable conversion handled in Alembic migration.
Write path: bulk insert via Core insert().values([...])
Read path: Core select() or raw SQL with PostGIS/TimescaleDB functions.
"""

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    PrimaryKeyConstraint,
    Table,
    Column,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from models.base_model import Base
from geoalchemy2 import Geography

forecast_data = Table(
    "forecast_data",
    Base.metadata,
    Column("ingested_at", DateTime(timezone=True), server_default=func.now()),
    Column("valid_time", DateTime(timezone=True), nullable=False),
    Column("loc", Geography(geometry_type="POINT", srid=4326), nullable=False),
    Column("model_run_id", ForeignKey("model_runs.id"), nullable=False),
    Column("payload", JSONB, nullable=False),
    PrimaryKeyConstraint("time", "model_run_id", name="pk_forecast_data"),
)

# GIST index for KNN queries via <-> operator
# TimescaleDB propagates this index to each chunk automatically
Index("ix_forecast_data_loc", forecast_data.c.loc, postgresql_using="gist")
