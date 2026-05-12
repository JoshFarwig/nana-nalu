from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies.core import get_async_db_session
from core.dependencies.repos import get_model_run_repo
from repositories.model_run_repository import ModelRunRepository
from services.forecast.forecast_service import ForecastService


def get_forecast_service(
    session: AsyncSession = Depends(get_async_db_session),
    repo: ModelRunRepository = Depends(get_model_run_repo),
) -> ForecastService:
    return ForecastService(session, repo)
