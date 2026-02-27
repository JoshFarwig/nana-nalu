import logging
from collections.abc import Sequence

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.exceptions.condition_profiles import (
    ConditionProfileError,
    ConditionProfileNotFoundError,
    ConditionProfilePermissionError,
)

from models.condition_profile_model import ConditionProfile
from models.surf_spot_model import SurfSpot
from models.crew_member_model import CrewMember


from schemas.condition_profile_schema import (
    ProviderConditionEntry,
    ConditionProfileCreate,
    ConditionProfileUpdate,
    ConditionProfileResponse,
    BatchConditionStatusResponse,
)

logger = logging.getLogger(__name__)


class AsyncConditionProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, profile_id: int):
        result = await self.session.execute(
            select(ConditionProfile).where(ConditionProfile.id == profile_id)
        )
        condition_profile = result.scalar_one_or_none()

        if not condition_profile:
            raise ConditionProfileNotFoundError(profile_id, "profile_id")

        return condition_profile

    async def get_all_by_spot_id(self, spot_id: int) -> Sequence[ConditionProfile]:
        result = await self.session.execute(
            select(ConditionProfile).where(ConditionProfile.spot_id == spot_id)
        )
        return result.scalars().all()

    async def get_all_by_user_id(self, user_id: int) -> Sequence[ConditionProfile]:
        result = await self.session.execute(
            select(ConditionProfile).where(ConditionProfile.user_id == user_id)
        )
        return result.scalars().all()

    async def get_all_for_spot_ids(
        self, spot_ids: set[int]
    ) -> Sequence[ConditionProfile]:
        result = await self.session.execute(
            select(ConditionProfile).where(ConditionProfile.spot_id.in_(spot_ids))
        )
        return result.scalars().all()

    async def get_all_viewable_for_user(
        self, user_id: int
    ) -> Sequence[ConditionProfile]:
        """
        Return all active profiles on spots the user can view
        (spots they own OR spots in a crew they're a member of).
        """
        stmt = (
            select(ConditionProfile)
            .join(SurfSpot, ConditionProfile.spot_id == SurfSpot.id)
            .outerjoin(CrewMember, SurfSpot.crew_id == CrewMember.crew_id)
            .where(
                ConditionProfile.is_active,
                or_(
                    SurfSpot.user_id == user_id,
                    CrewMember.user_id == user_id,
                ),
            )
            .distinct()
        )
        results = await self.session.execute(stmt)
        return results.scalars().all()

    async def create(self, profile_data: dict):
        condition_profile = ConditionProfile(
            **profile_data,
        )
        self.session.add(condition_profile)

        return condition_profile

    async def create_from_user(
        self, user_id: int, spot_id: int, profile_data: ConditionProfileCreate
    ):
        profile_dict = profile_data.model_dump()
        profile_dict["user_id"] = user_id
        profile_dict["spot_id"] = spot_id

        return await self.create(profile_data=profile_dict)

    async def update(self, profile_id: int, profile_data: dict):
        condition_profile = await self.get_by_id(profile_id)

        for k, v in profile_data.items():
            if hasattr(condition_profile, k):
                setattr(condition_profile, k, v)

        return condition_profile

    async def update_from_user(
        self, profile_id: int, profile_data: ConditionProfileUpdate
    ):
        profile_dict = profile_data.model_dump(exclude_unset=True)
        return await self.update(profile_id, profile_dict)

    async def delete(self, profile_id: int):
        condition_profile = await self.get_by_id(profile_id)
        await self.session.delete(condition_profile)
