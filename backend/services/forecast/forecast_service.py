import logging
from datetime import datetime
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions.forecasts import NoForecastDataError, NoModelRunError
from models.forecast_data import forecast_data
from models.model_run import ModelRun
from repositories.model_run_repository import ModelRunRepository
from schemas.forecast_schema import AvailableRunsResponse, ForecastPoint, ModelRunInfo
from utils.geo_spatial import snap_lat_lon

logger = logging.getLogger(__name__)


class ForecastService:
    def __init__(
        self, session: AsyncSession, model_run_repo: ModelRunRepository
    ) -> None:
        self.session = session
        self.repo = model_run_repo

    async def get_point_forecast(
        self,
        provider: str,
        model: str,
        region: str,
        lat: float,
        lon: float,
        valid_time: datetime | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[ModelRun, float, float, list[ForecastPoint]]:
        """
        Resolve latest run → snap coords → query → return validated ForecastPoints.

        Raises:
            NoModelRunError: No runs ingested for provider/model/region.
            NoForecastDataError: Run exists but no rows match coords/time filter.
        """
        run = await self._require_latest_run(provider, model, region)

        snapped_lat, snapped_lon = snap_lat_lon(
            run.lat_origin,
            run.lon_origin,
            run.lat_res,
            run.lon_res,
            lat,
            lon,
        )

        logger.debug(f"snapped lat lon: {snapped_lat, snapped_lon}")

        rows = await self._query_point(
            run.id,
            snapped_lat,
            snapped_lon,
            run.lat_res,
            run.lon_res,
            valid_time,
            start,
            end,
        )

        if not rows:
            raise NoForecastDataError(provider, model, region)

        points = [ForecastPoint.model_validate(r.payload) for r in rows]
        return run, snapped_lat, snapped_lon, points

    async def get_grid_forecast(
        self,
        provider: str,
        model: str,
        region: str,
        valid_time: datetime | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[ModelRun, Sequence]:
        """
        Resolve latest run → query all grid cells for time filter → return raw rows.
        Intended for visualization (map rendering).

        Raises:
            NoModelRunError: No runs ingested for provider/model/region.
            NoForecastDataError: Run exists but no rows match time filter.
        """
        run = await self._require_latest_run(provider, model, region)
        rows = await self._query_grid(run.id, valid_time, start, end)

        if not rows:
            raise NoForecastDataError(provider, model, region)

        return run, rows

    async def get_available_runs(self) -> AvailableRunsResponse:
        """Returns all ingested provider/model/region combos with their latest run time."""
        combos = await self.repo.get_distinct_combos()
        return AvailableRunsResponse(
            runs=[
                ModelRunInfo(
                    provider=row.provider,
                    model=row.model,
                    region=row.region,
                    latest_run_time=row.latest_run_time,
                )
                for row in combos
            ]
        )

    async def _require_latest_run(
        self, provider: str, model: str, region: str
    ) -> ModelRun:
        run = await self.repo.get_latest(provider, model, region)
        if not run:
            raise NoModelRunError(provider, model, region)
        return run

    async def _query_point(
        self,
        model_run_id: int,
        lat: float,
        lon: float,
        lat_res: float,
        lon_res: float,
        valid_time: datetime | None,
        start: datetime | None,
        end: datetime | None,
    ) -> Sequence:
        # BETWEEN absorbs float precision drift from origin + n*res arithmetic
        eps_lat = lat_res / 2
        eps_lon = lon_res / 2
        stmt = (
            select(forecast_data)
            .where(
                forecast_data.c.model_run_id == model_run_id,
                forecast_data.c.lat.between(lat - eps_lat, lat + eps_lat),
                forecast_data.c.lon.between(lon - eps_lon, lon + eps_lon),
            )
            .order_by(forecast_data.c.valid_time)
        )
        stmt = _apply_time_filter(stmt, valid_time, start, end)
        result = await self.session.execute(stmt)
        return result.fetchall()

    async def _query_grid(
        self,
        model_run_id: int,
        valid_time: datetime | None,
        start: datetime | None,
        end: datetime | None,
    ) -> Sequence:
        stmt = (
            select(forecast_data)
            .where(forecast_data.c.model_run_id == model_run_id)
            .order_by(
                forecast_data.c.valid_time, forecast_data.c.lat, forecast_data.c.lon
            )
        )
        stmt = _apply_time_filter(stmt, valid_time, start, end)
        result = await self.session.execute(stmt)
        return result.fetchall()


def _apply_time_filter(
    stmt, valid_time: datetime | None, start: datetime | None, end: datetime | None
):
    if valid_time is not None:
        return stmt.where(forecast_data.c.valid_time == valid_time)
    if start is not None:
        stmt = stmt.where(forecast_data.c.valid_time >= start)
    if end is not None:
        stmt = stmt.where(forecast_data.c.valid_time <= end)
    return stmt
