import logging
from fastapi import APIRouter, Depends

from core.dependencies.auth import get_current_user
from core.dependencies.services import get_crew_service

from schemas.response_schema import SuccessResponse
from schemas.crew_schema import CrewCreate, CrewResponse, CrewDetailResponse
from schemas.user_schema import CurrentUser

from services.crew_service import CrewService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crews", tags=["crews"])


@router.get("/me")
async def get_my_crews(
    current_user: CurrentUser = Depends(get_current_user),
    crew_service: CrewService = Depends(get_crew_service),
):
    """Get all crews the current user is a member of."""
    crews = await crew_service.get_user_crews(current_user.user_id)

    return SuccessResponse(
        message="Retrieved user crews",
        data=[CrewResponse.model_validate(crew) for crew in crews],
    )


@router.post("/")
async def create_crew(
    crew_data: CrewCreate,
    current_user: CurrentUser = Depends(get_current_user),
    crew_service: CrewService = Depends(get_crew_service),
):
    """Create a new crew with current user as creator."""
    crew = await crew_service.create_crew(current_user.user_id, crew_data)

    return SuccessResponse(
        message="Crew created successfully",
        data=CrewDetailResponse.model_validate(crew),
    )


@router.get("/{crew_id}")
async def get_crew(
    crew_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    crew_service: CrewService = Depends(get_crew_service),
):
    """Get crew details by ID."""
    crew = await crew_service.get_crew(crew_id)

    return SuccessResponse(
        message="Retrieved crew details",
        data=CrewDetailResponse.model_validate(crew),
    )


@router.post("/{crew_id}/join")
async def join_crew(
    crew_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    crew_service: CrewService = Depends(get_crew_service),
):
    """Join an existing crew."""
    await crew_service.join_crew(current_user.user_id, crew_id)

    return SuccessResponse(message="Successfully joined crew")


@router.post("/{crew_id}/leave")
async def leave_crew(
    crew_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    crew_service: CrewService = Depends(get_crew_service),
):
    """Leave a crew."""
    await crew_service.leave_crew(current_user.user_id, crew_id)

    return SuccessResponse(message="Successfully left crew")


# =========================================================================
# Magic Link Invite Routes (TODO)
# =========================================================================

# @router.post("/{crew_id}/invite")
# async def generate_invite_link(crew_id: int, ...):
#     """Generate a magic link invite for the crew."""
#     pass

# @router.post("/invite/accept")
# async def accept_invite(token: str, ...):
#     """Accept a crew invite via magic link token."""
#     pass

# @router.get("/invite/preview")
# async def preview_invite(token: str, ...):
#     """Preview crew details from invite link (without consuming)."""
#     pass
