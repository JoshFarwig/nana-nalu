import logging
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies.core import get_async_db_session

from repositories.surf_spot_repository import AsyncSurfSpotRepository

from schemas.response_schema import SuccessResponse
from schemas.surf_spot_schema import SurfSpotResponse
from schemas.filters_schema import SurfSpotFilters

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/surf_spots", tags=["surf_spots"])

# api/surf_spots
#   - return all surf spots with base data.
#   - this will probably depend on the user's
#     type, if its admin, it should be all spots
#     else, it should just show a user's spots.
#   - if "crews" are implemented, should be able to get all surf spots from a crew.
#   - maybe, endpoint to get a users surf spots should be api/surf_spots/me or /{id as your user id}?
#     and the same for the crew execept as api/surf_spots/crew/{id}?


# TODO: add JWT check for user role for admin, for now exclusive to admin
# may add to user if they wanna get global + created + crew spots.


# maybe convert query params in to a pydantic model? idk
@router.get("/", summary="List all surf spots")
async def get_all_surf_spots(
    filters: Annotated[SurfSpotFilters, Query()],
    session: AsyncSession = Depends(get_async_db_session),
):
    repo = AsyncSurfSpotRepository(session)
    spots = await repo.get_all_with_coordinates(
        filters.offset, filters.limit, filters.is_active
    )
    spot_responses = [SurfSpotResponse.model_validate(spot) for spot in spots]

    return SuccessResponse(
        message=f"Retrieved {len(spot_responses)} surf spot(s)", data=spot_responses
    )


# TODO: create surf spot endpoint, also checks user tier and available spots
@router.post("/", summary="Create a new surf spot")
async def create_surf_spot():
    pass


# TODO: add auth, get user id from JWT
@router.get("/me", summary="List of all surf spots created by the user")
async def get_user_surf_spots(session: AsyncSession = Depends(get_async_db_session)):
    pass


# TODO: add auth check to verify spot data is created from user, in crew, or from admin
@router.get("/{id}", summary="Get surf spot data")
async def get_surf_spot(id: int, session: AsyncSession = Depends(get_async_db_session)):
    repo = AsyncSurfSpotRepository(session)
    spot = await repo.get_with_coordinates(id)  # Returns dict with GeoJSON geometry

    spot_response = SurfSpotResponse.model_validate(spot)

    return SuccessResponse(
        message=f"Retrieved data for {spot_response.name}", data=spot_response
    )


@router.get(
    "/{id}/forecasts",
    summary="Return all forecast data for a surf spot",
)
async def get_forecasts(id: int, session: AsyncSession = Depends(get_async_db_session)):
    pass


@router.get(
    "/{id}/forecasts/available",
    summary="Return all the available providers and their forecast models for a surf spot",
)
async def get_available_providers():
    pass


@router.get(
    "/{id}/forecasts/{provider}",
    summary="Return all forecast data from a forecast provider",
)
async def get_provider_forecast(id: int, provider: str):
    pass


@router.get(
    "/{id}/forecasts/{provider}/{model}",
    summary="Return forecast data from a provider's forecast model",
)
async def get_model_forecast(id: int, provider: str, model: str):
    pass


# api/surf_spots/{id}
#   - return base data of the surf_spot
#
# api/surf_spots/{id}/forecasts -> can have different providers
#   - this would return all forecast proviers and their data for this spot
#
# api/surf_spots/{id}/forecasts/{provider}
#   - returns specific provider forecast data
