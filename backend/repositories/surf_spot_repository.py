import logging
from typing import Sequence
from sqlalchemy import RowMapping, select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_MakeEnvelope, ST_Within, ST_Y, ST_X
from sqlalchemy.orm import Session

from models.surf_spot_model import SurfSpot
from utils.geo_validation import valid_latitude_range, valid_longitude_range


class AsyncSurfSpotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    async def add(self, surf_spot_data: dict) -> SurfSpot:
        # TODO: add functionality to attach w/ surf spot.
        surf_spot = SurfSpot(**surf_spot_data)
        self.session.add(surf_spot)
        return surf_spot

    async def get_by_id(self, surf_spot_id: int) -> SurfSpot | None:
        result = await self.session.execute(
            select(SurfSpot).where(SurfSpot.id == surf_spot_id)
        )
        return result.scalar_one_or_none()

    async def get_by_is_active(self, is_active: bool) -> Sequence[SurfSpot] | None:
        results = await self.session.execute(
            select(SurfSpot).where(SurfSpot.is_active == is_active)
        )
        return results.scalars().all()

    async def get_all(self, skip: int = 0, limit: int = 20) -> Sequence[SurfSpot]:
        results = await self.session.execute(select(SurfSpot).offset(skip).limit(limit))
        return results.scalars().all()

    async def get_all_in_grid(
        self,
        lat_min: float,
        lat_max: float,
        long_min: float,
        long_max: float,
        is_active: bool = True,
    ) -> Sequence[RowMapping]:
        """Get spot id's with their associated latitude and longitudes from a grid"""
        if not valid_latitude_range(lat_min, lat_max) or not valid_longitude_range(
            long_min, long_max, range_type="signed"
        ):
            raise ValueError("latitude and longitude values are invalid")

        bbox = ST_MakeEnvelope(long_min, lat_min, long_max, lat_max, 4326)

        query = select(
            SurfSpot.id,
            ST_Y(SurfSpot.location).label("latitude"),
            ST_X(SurfSpot.location).label("longitude"),
        ).where(SurfSpot.is_active == is_active, ST_Within(SurfSpot.location, bbox))

        results = await self.session.execute(query)
        return results.mappings().all()

    async def get_coordinates(self, surf_spot_id: int) -> RowMapping | None:
        """Get latitude and longitude of a surf spot"""
        result = await self.session.execute(
            select(
                SurfSpot.id,
                ST_Y(SurfSpot.location).label("latitude"),
                ST_X(SurfSpot.location).label("longitude"),
            ).where(SurfSpot.id == surf_spot_id)
        )
        return result.mappings().one_or_none()

    async def update(self, surf_spot_id: int, surf_spot_data: dict) -> SurfSpot | None:
        surf_spot = await self.get_by_id(surf_spot_id)
        if not surf_spot:
            return None

        for key, value in surf_spot_data.items():
            if hasattr(surf_spot, key):
                setattr(surf_spot, key, value)

        return surf_spot

    async def delete(self, surf_spot_id: int) -> bool:
        surf_spot = await self.get_by_id(surf_spot_id)
        if not surf_spot:
            return False

        await self.session.delete(surf_spot)
        return True


class SyncSurfSpotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def any_exist(self) -> bool:
        result = self.session.execute(exists(SurfSpot.id).select())
        return bool(result.scalar())

    def get_all_in_grid(
        self,
        lat_min: float,
        lat_max: float,
        long_min: float,
        long_max: float,
        is_active: bool = True,
    ) -> Sequence[RowMapping]:
        """Get spot id's with their assocaited latitude and longitudes from a grid"""
        if not valid_latitude_range(lat_min, lat_max) or not valid_longitude_range(
            long_min, long_max, range_type="signed"
        ):
            raise ValueError("latitude and longitude values are invalid")

        bbox = ST_MakeEnvelope(long_min, lat_min, long_max, lat_max, 4326)

        query = select(
            SurfSpot.id,
            ST_Y(SurfSpot.location).label("latitude"),
            ST_X(SurfSpot.location).label("longitude"),
        ).where(SurfSpot.is_active == is_active, ST_Within(SurfSpot.location, bbox))

        results = self.session.execute(query)
        return results.mappings().all()
