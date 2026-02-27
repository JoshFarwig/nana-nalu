from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions.condition_profiles import (
    ConditionProfilePermissionError,
)

from models.condition_profile_model import ConditionProfile
from models.crew_member_model import CrewMember
from models.surf_spot_model import SurfSpot


class ConditionProfilePolicy:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    def require_ownership(self, user_id: int, profile: ConditionProfile, action: str):
        if profile.user_id != user_id:
            raise ConditionProfilePermissionError(user_id, profile.id, action)

    async def require_view_access(self, user_id: int, profile: ConditionProfile):
        if profile.user_id == user_id:
            return

        result = await self.session.execute(
            select(CrewMember)
            .join(SurfSpot, SurfSpot.crew_id == CrewMember.crew_id)
            .where(
                SurfSpot.id == profile.spot_id,
                CrewMember.user_id == user_id,
            )
        )

        if not result.scalar_one_or_none():
            raise ConditionProfilePermissionError(user_id, profile.id, "view")
