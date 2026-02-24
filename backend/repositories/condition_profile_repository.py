import logging
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.exceptions.condition_profiles import (
    ConditionProfileError,
    ConditionProfileNotFoundError,
    ConditionProfilePermissionError,
)

from models.condition_profile_model import ConditionProfile

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
        condition_profiles = result.scalars().all()

        if not condition_profiles:
            raise ConditionProfileNotFoundError(spot_id, "spot_id")

        return condition_profiles

    async def get_all_by_user_id(self, user_id: int) -> Sequence[ConditionProfile]:
        result = await self.session.execute(
            select(ConditionProfile).where(ConditionProfile.user_id == user_id)
        )
        condition_profiles = result.scalars().all()

        if not condition_profiles:
            raise ConditionProfileNotFoundError(user_id, "user_id")

        return condition_profiles

    async def get_all_for_spot_ids(
        self, spot_ids: set[int]
    ) -> Sequence[ConditionProfile]:
        result = await self.session.execute(
            select(ConditionProfile).where(ConditionProfile.spot_id.in_(spot_ids))
        )
        condition_profiles = result.scalars().all()

        if not condition_profiles:
            raise ConditionProfileNotFoundError(spot_ids, "spot_id")

        return condition_profiles

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
