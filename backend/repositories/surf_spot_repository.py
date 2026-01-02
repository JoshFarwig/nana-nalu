import logging
import json
from typing import Sequence
from sqlalchemy import RowMapping, select, exists, func
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import (
    ST_MakeEnvelope,
    ST_Within,
    ST_Y,
    ST_X,
    ST_GeomFromGeoJSON,
    ST_AsGeoJSON,
)
from sqlalchemy.orm import Session

from core.exceptions.surf_spots import (
    InvalidCoordBoundsError,
    SurfSpotNotFoundError,
    SurfSpotNotInRegionError,
)

from schemas.surf_spot_schema import SurfSpotCreate
from models.surf_spot_model import SurfSpot

from utils.geo_validation import valid_latitude_range, valid_longitude_range
from utils.region import resolve_region


logger = logging.getLogger(__name__)


class AsyncSurfSpotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, surf_spot_data: SurfSpotCreate) -> SurfSpot:
        # extract coordinates from GeoJSON for region validation
        lon, lat = surf_spot_data.geometry["coordinates"]

        # make sure spot exists in a valid region
        region = resolve_region(lat, lon)
        if region is None:
            raise SurfSpotNotInRegionError(surf_spot_data.name, lat, lon)

        # create surf spot with PostGIS geometry from GeoJSON
        surf_spot = SurfSpot(
            name=surf_spot_data.name,
            description=surf_spot_data.description,
            location=ST_GeomFromGeoJSON(json.dumps(surf_spot_data.geometry)),
            region=region,
            is_active=surf_spot_data.is_active,
        )

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
        """Get all surf spots with GeoJSON geometry."""
        results = await self.session.execute(
            select(
                SurfSpot.id,
                SurfSpot.name,
                SurfSpot.description,
                SurfSpot.region,
                SurfSpot.is_active,
                ST_AsGeoJSON(SurfSpot.location).label("geometry"),
            )
            .where(SurfSpot.is_active == is_active)
            .offset(offset)
            .limit(limit)
        )
        # parse GeoJSON strings to dicts
        spots = []
        for row in results.mappings():
            spot_dict = dict(row)
            spot_dict["geometry"] = json.loads(spot_dict["geometry"])
            spots.append(spot_dict)
        return spots

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
            raise InvalidCoordBoundsError(lat_min, lat_max, long_min, long_max)

        bbox = ST_MakeEnvelope(long_min, lat_min, long_max, lat_max, 4326)

        query = select(
            SurfSpot.id,
            ST_Y(SurfSpot.location).label("latitude"),
            ST_X(SurfSpot.location).label("longitude"),
        ).where(SurfSpot.is_active == is_active, ST_Within(SurfSpot.location, bbox))

        results = await self.session.execute(query)
        return results.mappings().all()

    async def get_with_coordinates(self, surf_spot_id: int) -> dict:
        result = await self.session.execute(
            select(
                SurfSpot.id,
                SurfSpot.name,
                SurfSpot.description,
                SurfSpot.region,
                SurfSpot.is_active,
                ST_AsGeoJSON(SurfSpot.location).label("geometry"),
            ).where(SurfSpot.id == surf_spot_id)
        )
        spot = result.mappings().one_or_none()

        if not spot:
            raise SurfSpotNotFoundError(surf_spot_id)

        # parse GeoJSON string to dict
        spot_dict = dict(spot)
        spot_dict["geometry"] = json.loads(spot_dict["geometry"])
        return spot_dict

    async def update(self, surf_spot_id: int, surf_spot_data: dict) -> SurfSpot:
        surf_spot = await self.get_by_id(surf_spot_id)

        for key, value in surf_spot_data.items():
            # handle geometry update - convert GeoJSON to PostGIS geometry
            if key == "geometry" and value is not None:
                # extract coordinates for region validation
                lon, lat = value["coordinates"]
                region = resolve_region(lat, lon)
                if region is None:
                    raise SurfSpotNotInRegionError(surf_spot.name, lat, lon)

                surf_spot.location = ST_GeomFromGeoJSON(json.dumps(value))
                surf_spot.region = region
            elif hasattr(surf_spot, key):
                setattr(surf_spot, key, value)

        return surf_spot

    async def delete(self, surf_spot_id: int) -> bool:
        surf_spot = await self.get_by_id(surf_spot_id)
        await self.session.delete(surf_spot)
        return True


class SyncSurfSpotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

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
            raise InvalidCoordBoundsError(lat_min, lat_max, long_min, long_max)

        bbox = ST_MakeEnvelope(long_min, lat_min, long_max, lat_max, 4326)

        query = select(
            SurfSpot.id,
            ST_Y(SurfSpot.location).label("latitude"),
            ST_X(SurfSpot.location).label("longitude"),
        ).where(SurfSpot.is_active == is_active, ST_Within(SurfSpot.location, bbox))

        results = self.session.execute(query)
        return results.mappings().all()
