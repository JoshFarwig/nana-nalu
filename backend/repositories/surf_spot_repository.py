import logging
from typing import Sequence
from sqlalchemy import RowMapping, select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_MakeEnvelope, ST_Within, ST_Y, ST_X
from sqlalchemy.orm import Session

from core.exceptions.surf_spots import InvalidGridBoundsError, SurfSpotNotFoundError
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

    async def get_by_id(self, surf_spot_id: int) -> SurfSpot:
        result = await self.session.execute(
            select(SurfSpot).where(SurfSpot.id == surf_spot_id)
        )
        spot = result.scalar_one_or_none()

        if not spot:
            raise SurfSpotNotFoundError(surf_spot_id)

        return spot

    async def get_all(
        self, offset: int, limit: int, is_active: bool
    ) -> Sequence[SurfSpot]:
        results = await self.session.execute(
            select(SurfSpot)
            .where(SurfSpot.is_active == is_active)
            .offset(offset)
            .limit(limit)
        )
        return results.scalars().all()

    async def get_all_with_coordinates(
        self, offset: int, limit: int, is_active: bool
    ) -> Sequence[RowMapping]:
        """Get all surf spots with lat/lon extracted via PostGIS functions."""
        results = await self.session.execute(
            select(
                SurfSpot.id,
                SurfSpot.name,
                SurfSpot.description,
                SurfSpot.is_active,
                SurfSpot.created_by_id,
                ST_Y(SurfSpot.location).label("latitude"),
                ST_X(SurfSpot.location).label("longitude"),
            )
            .where(SurfSpot.is_active == is_active)
            .offset(offset)
            .limit(limit)
        )
        return results.mappings().all()

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
            raise InvalidGridBoundsError(lat_min, lat_max, long_min, long_max)

        bbox = ST_MakeEnvelope(long_min, lat_min, long_max, lat_max, 4326)

        query = select(
            SurfSpot.id,
            ST_Y(SurfSpot.location).label("latitude"),
            ST_X(SurfSpot.location).label("longitude"),
        ).where(SurfSpot.is_active == is_active, ST_Within(SurfSpot.location, bbox))

        results = await self.session.execute(query)
        return results.mappings().all()

    async def get_coordinates(self, surf_spot_id: int) -> RowMapping:
        result = await self.session.execute(
            select(
                SurfSpot.id,
                ST_Y(SurfSpot.location).label("latitude"),
                ST_X(SurfSpot.location).label("longitude"),
            ).where(SurfSpot.id == surf_spot_id)
        )
        coords = result.mappings().one_or_none()

        if not coords:
            raise SurfSpotNotFoundError(surf_spot_id)

        return coords

    async def update(self, surf_spot_id: int, surf_spot_data: dict) -> SurfSpot:
        surf_spot = await self.get_by_id(surf_spot_id)

        for key, value in surf_spot_data.items():
            if hasattr(surf_spot, key):
                setattr(surf_spot, key, value)

        return surf_spot

    async def delete(self, surf_spot_id: int) -> bool:
        surf_spot = await self.get_by_id(surf_spot_id)
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
            raise InvalidGridBoundsError(lat_min, lat_max, long_min, long_max)

        bbox = ST_MakeEnvelope(long_min, lat_min, long_max, lat_max, 4326)

        query = select(
            SurfSpot.id,
            ST_Y(SurfSpot.location).label("latitude"),
            ST_X(SurfSpot.location).label("longitude"),
        ).where(SurfSpot.is_active == is_active, ST_Within(SurfSpot.location, bbox))

        results = self.session.execute(query)
        return results.mappings().all()
