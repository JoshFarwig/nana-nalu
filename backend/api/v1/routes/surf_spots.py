import logging
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies.auth import get_current_user, require_admin
from core.dependencies.core import get_async_db_session

from core.dependencies.services import get_forecast_service, get_surf_spot_service
from repositories.surf_spot_repository import AsyncSurfSpotRepository

from schemas.response_schema import SuccessResponse
from schemas.surf_spot_schema import SurfSpotCreate, SurfSpotUpdate, SurfSpotResponse
from schemas.filters_schema import AdminSurfSpotFilters
from schemas.user_schema import CurrentUser

from services.forecast.forecast_schema import ProviderForecastResponse
from services.forecast.forecast_service import ForecastService
from services.surf_spot_service import SurfSpotService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/surf-spots", tags=["surf_spots"])


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


@router.post("/", summary="Create a new surf spot")
async def create_surf_spot(
    data: SurfSpotCreate,
    current_user: CurrentUser = Depends(get_current_user),
    surf_spot_service: SurfSpotService = Depends(get_surf_spot_service),
):
    spot = await surf_spot_service.create_spot(current_user.user_id, data)

    return SuccessResponse(message=f"Created surf spot '{spot.name}'", data=spot)


# TODO: figure out how to refactor surf spot endpoints / repo methods for is_demo
@router.get("/demo", summary="List all active demo spots")
async def get_all_demo_surf_spots():
    return {"message": "TODO"}


@router.get("/me", summary="List of all surf spots created by the user")
async def get_user_surf_spots(
    current_user: CurrentUser = Depends(get_current_user),
    surf_spot_service: SurfSpotService = Depends(get_surf_spot_service),
):
    spots = await surf_spot_service.get_user_spots(current_user.user_id)

    return SuccessResponse(message=f"Retrieved {len(spots)} surf spot(s)", data=spots)


@router.get("/{id}", summary="Get surf spot data")
async def get_surf_spot(
    id: int,
    current_user: CurrentUser = Depends(get_current_user),
    surf_spot_service: SurfSpotService = Depends(get_surf_spot_service),
):
    spot = await surf_spot_service.get_spot(current_user.user_id, id)

    return SuccessResponse(message=f"Retrieved data for {spot.name}", data=spot)


@router.patch("/{id}", summary="Update a surf spot")
async def update_surf_spot(
    id: int,
    data: SurfSpotUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    surf_spot_service: SurfSpotService = Depends(get_surf_spot_service),
):
    spot = await surf_spot_service.update_spot(current_user.user_id, id, data)

    return SuccessResponse(message=f"Updated surf spot '{spot.name}'", data=spot)


@router.delete("/{id}", summary="Delete a surf spot")
async def delete_surf_spot(
    id: int,
    current_user: CurrentUser = Depends(get_current_user),
    surf_spot_service: SurfSpotService = Depends(get_surf_spot_service),
):
    await surf_spot_service.delete_spot(current_user.user_id, id)

    return SuccessResponse(message=f"Deleted surf spot {id}")


@router.get(
    "/{id}/forecasts",
    summary="Return all forecast data for a surf spot",
)
async def get_forecasts(
    id: int,
    current_user: CurrentUser = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    forecasts = await forecast_service.get_forecasts(id, current_user.user_id)

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
    id: int,
    current_user: CurrentUser = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    providers = await forecast_service.get_available_providers(id, current_user.user_id)

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
    current_user: CurrentUser = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    provider_forecasts = await forecast_service.get_forecast_by_provider(
        id, provider, current_user.user_id
    )

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
    current_user: CurrentUser = Depends(get_current_user),
    forecast_service: ForecastService = Depends(get_forecast_service),
):
    model_forecast = await forecast_service.get_forecast_by_model(
        id, provider, model, current_user.user_id
    )

    forecast_response = ProviderForecastResponse.from_provider_forecast(
        model_forecast
    ).to_response_dict()

    return SuccessResponse(
        message=f"Retrieved {model} forecast for provider {provider} for spot {id}",
        data=forecast_response,
    )
