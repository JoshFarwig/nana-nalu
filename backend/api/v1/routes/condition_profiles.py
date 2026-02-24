import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("/me")
def get_user_condition_profiles():
    pass


@router.get("/spots/{spot_id}")
def get_spot_condition_profiles():
    pass


@router.put("/{profile_id}")
def update_condition_profile():
    pass


@router.delete("/{profile_id}")
def delete_condition_profile():
    pass


# all user viewable condition profile matches
@router.get("/status")
# allow for query param for either "mine" or "all" viewable
def get_all_condition_profiles_statuses():
    pass


@router.get("status/{spot_id}")
# allow for query param for either "mine" or "all" viewable
def get_all_spot_condition_profile_statuses():
    pass
