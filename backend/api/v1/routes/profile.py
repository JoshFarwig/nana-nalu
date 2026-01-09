import logging
from fastapi import APIRouter, Depends

from core.dependencies.auth import get_current_user
from core.dependencies.repositories import get_user_repository

from repositories.user_repository import AsyncUserRepository

from schemas.response_schema import SuccessResponse
from schemas.user_schema import CurrentUser, UserUpdate, UserResponse


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profile", tags=["users"])

# NOTE: Cloudflare R2 for profile pic / surf spot photos?


@router.get("/me")
async def get_current_user_profile(
    current_user: CurrentUser = Depends(get_current_user),
    user_repo: AsyncUserRepository = Depends(get_user_repository),
):
    user = await user_repo.get_by_id(current_user.user_id)

    user_profile = UserResponse(
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        bio=user.bio,
        location=user.location,
    )

    return SuccessResponse(message="Retrieved user profile", data=user_profile)


@router.put("/me")
async def update_user_profile(
    user_data: UserUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    user_repo: AsyncUserRepository = Depends(get_user_repository),
):
    fields_updated = [field for field in user_data.model_dump(exclude_unset=True)]
    user = await user_repo.update_profile(current_user.user_id, user_data)

    await user_repo.session.commit()

    logger.info(
        f"User: {user.id}-{user.username} updated their profile",
        extra={
            "user_id": user.id,
            "email": user.email,
            "username": user.username,
            "fields_updated": fields_updated,
        },
    )

    return SuccessResponse(message="User updated profile", data=fields_updated)


# TODO: introduce 1:1 features for better QOL for friend to friend relations in app,
# for now, crew-based relationships between users makes the most sense for v1, but
# in the future, v2 could have a global friend look up.

# def get_user_friends():
#     pass
# @router.get("/{username}")
# def get_user_profile(username: str):
#     pass


# TODO: setup cloudflare R2 for profile pic?
# @router.post("/me/avatar")
# def upload_profile_picture():
#     pass
