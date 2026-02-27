from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from models.surf_spot_model import SurfSpot
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from schemas.surf_spot_schema import SurfSpotCreate, SurfSpotUpdate
from services.policies.surf_spot_policy import SurfSpotPolicy


class SurfSpotService:
    def __init__(
        self,
        spot_repo: AsyncSurfSpotRepository,
        spot_policy: SurfSpotPolicy,
        session: AsyncSession,
    ):
        self.spot_repo = spot_repo
        self.spot_policy = spot_policy
        self.session = session

    async def get_spot(self, user_id: int, spot_id: int) -> SurfSpot:
        spot = await self.spot_repo.get_by_id(spot_id)
        await self.spot_policy.require_view_access(user_id, spot)
        return spot

    async def get_user_spots(self, user_id: int) -> Sequence[SurfSpot]:
        return await self.spot_repo.get_all_by_user_id(user_id)

    async def get_all_viewable_spots(self, user_id: int) -> Sequence[SurfSpot]:
        return await self.spot_repo.get_all_user_viewable_spots(user_id)

    async def create_spot(self, user_id: int, data: SurfSpotCreate) -> SurfSpot:
        spot = await self.spot_repo.create_from_user(user_id, data)
        await self.session.commit()
        await self.session.refresh(spot)
        return spot

    async def update_spot(
        self, user_id: int, spot_id: int, data: SurfSpotUpdate
    ) -> SurfSpot:
        spot = await self.spot_repo.get_by_id(spot_id)
        self.spot_policy.require_ownership(user_id, spot, "update")
        spot = await self.spot_repo.update_profile(spot_id, data)
        await self.session.commit()
        await self.session.refresh(spot)
        return spot

    async def delete_spot(self, user_id: int, spot_id: int) -> bool:
        spot = await self.spot_repo.get_by_id(spot_id)
        self.spot_policy.require_ownership(user_id, spot, "delete")
        result = await self.spot_repo.delete(spot_id)
        await self.session.commit()
        return result
