from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions.surf_spots import SurfSpotPermissionError
from models.crew_member_model import CrewMember
from models.surf_spot_model import SurfSpot


class SurfSpotPolicy:
    def __init__(
        self,
        session: AsyncSession,
    ):
        self.session = session

    def require_ownership(self, user_id: int, spot: SurfSpot, action: str):
        if spot.user_id != user_id:
            raise SurfSpotPermissionError(user_id, spot.id, action)

    async def require_view_access(self, user_id: int, spot: SurfSpot):
        if spot.user_id == user_id:
            return

        result = await self.session.execute(
            select(CrewMember).where(
                CrewMember.crew_id == spot.crew_id, CrewMember.user_id == user_id
            )
        )

        if not result.scalar_one_or_none():
            raise SurfSpotPermissionError(user_id, spot.id, "view")
