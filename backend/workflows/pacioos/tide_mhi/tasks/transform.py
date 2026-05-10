from prefect import task, get_run_logger

from services.forecast.pacioos_config import PacIOOSModelConfig
from workflows.pacioos.tide_mhi.mapper import map_pacioos_tide_forecast
from services.forecast.forecast_schema import GridCellForecast


@task(name="tide-mhi-transform-forecasts")
def transform_forecasts(
    raw_cells: list[dict],
    config: PacIOOSModelConfig,
) -> list[GridCellForecast]:
    """Transform raw PacIOOS tide grid cells to unified GridCellForecast schema."""
    logger = get_run_logger()

    if not raw_cells:
        logger.warning("No raw cells to transform")
        return []

    cells = [
        map_pacioos_tide_forecast(cell["lat"], cell["lon"], cell, config.data_summary)
        for cell in raw_cells
    ]

    logger.info(f"Transformed {len(cells)} grid cells to unified schema")
    return cells
