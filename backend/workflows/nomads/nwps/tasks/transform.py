from prefect import task, get_run_logger

from services.forecast.nomads_config import NWPSConfig
from workflows.nomads.mappers import map_nwps_forecast
from services.forecast.forecast_schema import GridCellForecast


@task(name="nwps-transform-forecasts")
def transform_forecasts(
    raw_cells: list[dict],
    config: NWPSConfig,
) -> list[GridCellForecast]:
    """Transform raw NWPS grid cell data to unified GridCellForecast schema."""
    logger = get_run_logger()

    if not raw_cells:
        logger.warning("No raw cells to transform")
        return []

    cells = [
        map_nwps_forecast(cell["lat"], cell["lon"], cell, config.data_summary)
        for cell in raw_cells
    ]

    logger.info(f"Transformed {len(cells)} grid cells to unified schema")
    return cells
