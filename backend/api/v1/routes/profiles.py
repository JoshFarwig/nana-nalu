import logging
from typing import Literal

from fastapi import APIRouter, Depends

from core.dependencies.auth import get_current_user
from core.dependencies.services import get_condition_profile_service

from schemas.condition_profile_schema import (
    ConditionProfileCreate,
    ConditionProfileUpdate,
    ConditionProfileResponse,
)
from schemas.response_schema import SuccessResponse
from schemas.user_schema import CurrentUser

from services.condition_profile_service import ConditionProfileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/me", summary="List all condition profiles created by the user")
async def get_user_condition_profiles(
    current_user: CurrentUser = Depends(get_current_user),
    profile_service: ConditionProfileService = Depends(get_condition_profile_service),
):
    profiles = await profile_service.get_user_profiles(current_user.user_id)
    data = [ConditionProfileResponse.model_validate(p) for p in profiles]

    return SuccessResponse(
        message=f"Retrieved {len(data)} condition profile(s)", data=data
    )


@router.get(
    "/surf-spots/{spot_id}",
    summary="List all condition profiles for a surf spot",
)
async def get_spot_condition_profiles(
    spot_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    profile_service: ConditionProfileService = Depends(get_condition_profile_service),
):
    profiles = await profile_service.get_spot_profiles(current_user.user_id, spot_id)
    data = [ConditionProfileResponse.model_validate(p) for p in profiles]

    return SuccessResponse(
        message=f"Retrieved {len(data)} condition profile(s) for spot {spot_id}",
        data=data,
    )


@router.post(
    "/surf-spots/{spot_id}",
    summary="Create a condition profile on a surf spot",
)
async def create_condition_profile(
    spot_id: int,
    data: ConditionProfileCreate,
    current_user: CurrentUser = Depends(get_current_user),
    profile_service: ConditionProfileService = Depends(get_condition_profile_service),
):
    profile = await profile_service.create_profile(current_user.user_id, spot_id, data)
    response = ConditionProfileResponse.model_validate(profile)

    return SuccessResponse(
        message=f"Created condition profile '{response.name}'", data=response
    )


@router.get("/{profile_id}", summary="Get a condition profile by ID")
async def get_condition_profile(
    profile_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    profile_service: ConditionProfileService = Depends(get_condition_profile_service),
):
    profile = await profile_service.get_profile(current_user.user_id, profile_id)
    response = ConditionProfileResponse.model_validate(profile)

    return SuccessResponse(
        message=f"Retrieved condition profile '{response.name}'", data=response
    )


@router.put("/{profile_id}", summary="Update a condition profile")
async def update_condition_profile(
    profile_id: int,
    data: ConditionProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    profile_service: ConditionProfileService = Depends(get_condition_profile_service),
):
    profile = await profile_service.update_profile(
        current_user.user_id, profile_id, data
    )
    response = ConditionProfileResponse.model_validate(profile)

    return SuccessResponse(
        message=f"Updated condition profile '{response.name}'", data=response
    )


@router.delete("/{profile_id}", summary="Delete a condition profile")
async def delete_condition_profile(
    profile_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    profile_service: ConditionProfileService = Depends(get_condition_profile_service),
):
    await profile_service.delete_profile(current_user.user_id, profile_id)

    return SuccessResponse(message=f"Deleted condition profile {profile_id}")


@router.get(
    "/status",
    summary="Get condition status for user-viewable spots (all or only user owned)",
)
async def get_all_condition_statuses(
    scope: Literal["all", "mine"] = "all",
    current_user: CurrentUser = Depends(get_current_user),
    profile_service: ConditionProfileService = Depends(get_condition_profile_service),
):
    if scope == "mine":
        result = await profile_service.evalute_all_user_condition_profiles(
            current_user.user_id
        )
    else:
        result = await profile_service.evalute_all_viewable_condition_profiles(
            current_user.user_id
        )

    return SuccessResponse(
        message=f"Evaluated conditions for {len(result.spots)} spot(s)",
        data=result,
    )


@router.get(
    "/status/{profile_id}",
    summary="Get condition status for a single profile",
)
async def get_condition_profile_status(
    profile_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    profile_service: ConditionProfileService = Depends(get_condition_profile_service),
):
    # verify view access before evaluating
    await profile_service.get_profile(current_user.user_id, profile_id)
    result = await profile_service.evalute_condition_profile(profile_id)

    return SuccessResponse(
        message=f"Evaluated condition profile {profile_id}",
        data=result,
    )
