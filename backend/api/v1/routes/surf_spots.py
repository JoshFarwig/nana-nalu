import logging
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies.auth import require_admin
from core.dependencies.core import get_async_db_session

from core.dependencies.services import get_forecast_service
from repositories.surf_spot_repository import AsyncSurfSpotRepository

from schemas.response_schema import SuccessResponse
from schemas.surf_spot_schema import SurfSpotResponse
from schemas.filters_schema import AdminSurfSpotFilters, SurfSpotFilters

from services.forecast.forecast_schema import ProviderForecastResponse
from services.forecast.forecast_service import ForecastService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/surf-spots", tags=["surf_spots"])


# =============================
# Base Surf Spot Routes
# =============================


@router.get("/", summary="List all surf spots", dependencies=[Depends(require_admin)])
async def get_all_surf_spots(
    filters: Annotated[AdminSurfSpotFilters, Query()],
    session: AsyncSession = Depends(get_async_db_session),
):
    repo = AsyncSurfSpotRepository(session)
    spots = await repo.get_all_with_coordinates(
        filters.offset,
        filters.limit,
        filters.is_active,
    )
    spot_responses = [SurfSpotResponse.model_validate(spot) for spot in spots]

    return SuccessResponse(
        message=f"Retrieved {len(spot_responses)} surf spot(s)", data=spot_responses
    )


# TODO: figure out how to refactor surf spot endpoints / repo methods for is_demo
@router.get("/demo", summary="List all active demo spots")
async def get_all_demo_surf_spots():
    pass


# @router.post("/", summary="Create a new surf spot")
# async def create_surf_spot():
#     pass


@router.get("/me", summary="List of all surf spots created by the user")
async def get_user_surf_spots(session: AsyncSession = Depends(get_async_db_session)):
    pass


# TODO: add auth check to verify spot data is created from user, in crew, or from admin
@router.get("/{id}", summary="Get surf spot data")
async def get_surf_spot(id: int, session: AsyncSession = Depends(get_async_db_session)):
    repo = AsyncSurfSpotRepository(session)
    spot = await repo.get_with_coordinates(id)

    spot_response = SurfSpotResponse.model_validate(spot)

    return SuccessResponse(
        message=f"Retrieved data for {spot_response.name}", data=spot_response
    )


# =============================
# Surf Spot Forecast Routes
# =============================


@router.get(
    "/{id}/forecasts",
    summary="Return all forecast data for a surf spot",
)
async def get_forecasts(
    id: int, forecast_service: ForecastService = Depends(get_forecast_service)
):
    forecasts = await forecast_service.get_forecasts(id)

    # convert to clean response dicts (excludes None, computes units)
    forecast_responses = [
        ProviderForecastResponse.from_provider_forecast(f).to_response_dict()
        for f in forecasts
    ]

    return SuccessResponse(
        message=f"Retrieved {len(forecast_responses)} forecast provider(s)",
        data=forecast_responses,
    )


@router.get(
    "/{id}/forecasts/available",
    summary="Return all the available providers and their forecast models for a surf spot",
)
async def get_available_providers(
    id: int, forecast_service: ForecastService = Depends(get_forecast_service)
):
    providers = await forecast_service.get_available_providers(id)

    return SuccessResponse(
        message=f"{len(providers)} forecast provider(s) available", data=providers
    )


@router.get(
    "/{id}/forecasts/{provider}",
    summary="Return all forecast data from a forecast provider",
    response_model_exclude_none=True,
)
async def get_provider_forecast(
    id: int,
    provider: str,
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    provider_forecasts = await forecast_service.get_forecast_by_provider(id, provider)

    # convert to response schema
    forecast_responses = [
        ProviderForecastResponse.from_provider_forecast(f).to_response_dict()
        for f in provider_forecasts
    ]

    return SuccessResponse(
        message=f"Retrieved {provider} provider forecast(s) for spot {id}",
        data=forecast_responses,
    )


@router.get(
    "/{id}/forecasts/{provider}/{model}",
    summary="Return forecast data from a provider's forecast model",
)
async def get_model_forecast(
    id: int,
    provider: str,
    model: str,
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    # will raise NoForecastDataError (404) if data doesn't exist
    model_forecast = await forecast_service.get_forecast_by_model(id, provider, model)

    forecast_response = ProviderForecastResponse.from_provider_forecast(
        model_forecast
    ).to_response_dict()

    return SuccessResponse(
        message=f"Retrieved {model} forecast for provider {provider} for spot {id}",
        data=forecast_response,
    )
