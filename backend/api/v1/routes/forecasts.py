from fastapi import APIRouter, Depends

from core.dependencies.services import get_forecast_service
from schemas.filters_schema import GridForecastFilter, PointForecastFilter
from schemas.forecast_schema import (
    AvailableRunsResponse,
    GridForecastResponse,
    GridForecastRow,
    PointForecastResponse,
)
from schemas.response_schema import SuccessResponse
from services.forecast.forecast_service import ForecastService


router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get(
    "/available",
    response_model=SuccessResponse[AvailableRunsResponse],
    response_model_exclude_none=True,
)
async def get_available_runs(
    service: ForecastService = Depends(get_forecast_service),
) -> SuccessResponse[AvailableRunsResponse]:
    """All ingested provider/model/region combos with their latest run time."""
    data = await service.get_available_runs()
    return SuccessResponse(data=data)


@router.get(
    "/point",
    response_model=SuccessResponse[PointForecastResponse],
    response_model_exclude_none=True,
)
async def get_point_forecast(
    filters: PointForecastFilter = Depends(),
    service: ForecastService = Depends(get_forecast_service),
) -> SuccessResponse[PointForecastResponse]:
    """
    Point forecast for a lat/lon. Snaps coords to nearest grid cell.

    Time filter (pick one):
    - valid_time: single forecast timestamp
    - start + end: inclusive time range
    - neither: full forecast horizon

    Raises 404 via NanaNaluException if no model run or no data for coords/time.
    """
    run, snapped_lat, snapped_lon, points = await service.get_point_forecast(
        filters.provider,
        filters.model,
        filters.region,
        filters.lat,
        filters.lon,
        filters.valid_time,
        filters.start,
        filters.end,
    )

    data = PointForecastResponse(
        provider=filters.provider,
        model=filters.model,
        region=filters.region,
        run_time=run.run_time,
        lat=snapped_lat,
        lon=snapped_lon,
        points=points,
    )
    return SuccessResponse(data=data)


@router.get(
    "/grid",
    response_model=SuccessResponse[GridForecastResponse],
    response_model_exclude_none=True,
)
async def get_grid_forecast(
    filters: GridForecastFilter = Depends(),
    service: ForecastService = Depends(get_forecast_service),
) -> SuccessResponse[GridForecastResponse]:
    """
    All grid cells for a time filter. Intended for map visualization.

    Time filter (pick one):
    - valid_time: single snapshot across all grid cells (recommended for map rendering)
    - start + end: all cells across a time range (can be large)
    - neither: full grid x full horizon (very large, use with caution)

    Raises 404 via NanaNaluException if no model run or no data for time filter.
    """
    run, rows = await service.get_grid_forecast(
        filters.provider,
        filters.model,
        filters.region,
        filters.valid_time,
        filters.start,
        filters.end,
    )

    data = GridForecastResponse(
        provider=filters.provider,
        model=filters.model,
        region=filters.region,
        run_time=run.run_time,
        rows=[GridForecastRow(lat=r.lat, lon=r.lon, payload=r.payload) for r in rows],
    )
    return SuccessResponse(data=data)
