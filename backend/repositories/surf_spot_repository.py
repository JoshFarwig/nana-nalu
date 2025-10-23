from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.surf_spot_model import SurfSpot


class SurfSpotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, surf_spot_data: dict) -> SurfSpot:
        """Add a surf spot (no commit)."""
        surf_spot = SurfSpot(**surf_spot_data)
        self.session.add(surf_spot)
        await self.session.flush()
        return surf_spot

    async def get_by_id(self, surf_spot_id: int) -> SurfSpot | None:
        """Get surf spot by ID"""
        result = await self.session.execute(
            select(SurfSpot).where(SurfSpot.id == surf_spot_id)
        )
        return result.scalar_one_or_none()

    async def get_by_is_active(self, is_active: bool) -> Sequence[SurfSpot] | None:
        """Get surf spots by system active status"""
        results = await self.session.execute(
            select(SurfSpot).where(SurfSpot.is_active == is_active)
        )
        return results.scalars().all()

    async def get_all(self, skip: int = 0, limit: int = 20) -> Sequence[SurfSpot]:
        """Get all surf spots"""
        results = await self.session.execute(select(SurfSpot).offset(skip).limit(limit))
        return results.scalars().all()

    async def get_by_location(
        self, surf_spot_latitude: float, surf_spot_longitude: float
    ) -> SurfSpot | None:
        """Unclear requirement as of now, implement later"""
        raise NotImplementedError

    async def update(self, surf_spot_id: int, surf_spot_data: dict) -> SurfSpot | None:
        """Update surf spot by ID (no commit)"""
        surf_spot = await self.get_by_id(surf_spot_id)
        if not surf_spot:
            return None

        for key, value in surf_spot_data.items():
            if hasattr(surf_spot, key):
                setattr(surf_spot, key, value)

        await self.session.flush()
        return surf_spot

    async def delete(self, surf_spot_id: int) -> bool:
        """Delete a surf spot by ID (no_commit)"""
        surf_spot = await self.get_by_id(surf_spot_id)
        if not surf_spot:
            return False

        await self.session.delete(surf_spot)
        await self.session.flush()
        return True
