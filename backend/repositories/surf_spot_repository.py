import logging
import json
from re import S
from collections.abc import Sequence
from sqlalchemy import RowMapping, or_, select, exists
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

from models.crew_member_model import CrewMember
from models.crew_model import Crew
from models.surf_spot_model import SurfSpot

from schemas.surf_spot_schema import SurfSpotCreate, SurfSpotUpdate

from utils.geo_validation import valid_latitude_range, valid_longitude_range
from utils.region import resolve_region


logger = logging.getLogger(__name__)


class AsyncSurfSpotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, surf_spot_id: int) -> SurfSpot:
        """Get surf spot by ID."""
        result = await self.session.execute(
            select(SurfSpot).where(SurfSpot.id == surf_spot_id)
        )
        spot = result.scalar_one_or_none()

        if not spot:
            raise SurfSpotNotFoundError(surf_spot_id)

        return spot

    async def get_all_by_user_id(self, user_id: int) -> Sequence[SurfSpot]:
        """Get all surf spots owned by a user"""

        results = await self.session.execute(
            select(SurfSpot).where(SurfSpot.user_id == user_id)
        )

        return results.scalars().all()

    async def get_all_by_crew_id(self, crew_id: int) -> Sequence[SurfSpot]:
        """Get all spots that exist in a crew"""
        results = await self.session.execute(
            select(SurfSpot).where(SurfSpot.crew_id == crew_id)
        )

        return results.scalars().all()

    async def get_all_user_spots_in_crew(
        self, crew_id: int, user_id: int
    ) -> Sequence[SurfSpot]:
        """Get all spots that belong to a user in a specific crew"""

        stmt = (
            select(SurfSpot)
            .join(Crew, SurfSpot.crew_id == crew_id)
            .where(SurfSpot.user_id == user_id)
        )

        results = await self.session.execute(stmt)

        return results.scalars().all()

    async def get_all_user_viewable_spots(self, user_id: int) -> Sequence[SurfSpot]:
        """Get all spots that that are viewable for a user (user owned spots + spots in a crew a user exists in)"""

        stmt = (
            select(SurfSpot)
            .outerjoin(CrewMember, SurfSpot.crew_id == CrewMember.crew_id)
            .where(
                or_(
                    SurfSpot.user_id == user_id,
                    CrewMember.user_id == user_id,
                )
            )
            .distinct()
        )

        results = await self.session.execute(stmt)

        return results.scalars().all()

    async def get_all(
        self,
        offset: int,
        limit: int,
        is_active: bool,
        is_demo: bool,
    ) -> Sequence[SurfSpot]:
        """Get all surf spots with pagination and active status filter."""
        results = await self.session.execute(
            select(SurfSpot)
            .where(SurfSpot.is_active == is_active, SurfSpot.is_demo == is_demo)
            .offset(offset)
            .limit(limit)
        )
        return results.scalars().all()

    async def get_demo(self, is_active: bool):
        pass

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
                SurfSpot.is_demo,
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
        ).where(
            SurfSpot.is_active == is_active,
            ST_Within(SurfSpot.location, bbox),
        )

        results = await self.session.execute(query)
        return results.mappings().all()

    async def get_with_coordinates(self, surf_spot_id: int) -> dict:
        """Get surf spot by ID with GeoJSON coordinates."""
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

    async def create(self, surf_spot_data: dict) -> SurfSpot:
        """
        Create a new surf spot - internal/admin method.

        Handles GeoJSON to PostGIS geometry conversion and region validation.
        Accepts any valid SurfSpot model fields including admin-only is_demo.

        Args:
            surf_spot_data: Dictionary of fields to set on the new surf spot
                           Must include: user_id, name, geometry (GeoJSON dict)
                           Optional: description, is_active, is_demo

        Returns:
            Created SurfSpot model instance

        Raises:
            SurfSpotNotInRegionError: If geometry is outside supported regions
        """
        # extract and validate geometry
        geometry = surf_spot_data.pop("geometry")
        lon, lat = geometry["coordinates"]

        # validate region
        region = resolve_region(lat, lon)
        if region is None:
            spot_name = surf_spot_data.get("name", "Unknown")
            raise SurfSpotNotInRegionError(spot_name, lat, lon)

        # create surf spot with PostGIS geometry
        surf_spot = SurfSpot(
            **surf_spot_data,
            location=ST_GeomFromGeoJSON(json.dumps(geometry)),
            region=region,
        )

        self.session.add(surf_spot)
        return surf_spot

    async def create_from_user(
        self, user_id: int, surf_spot_data: SurfSpotCreate
    ) -> SurfSpot:
        """
        Create a new surf spot from user input - public-facing method.

        Automatically sets: is_demo=False (enforced by not allowing it in dict).
        User provides: name, description, geometry, is_active.

        Args:
            user_id: The ID of the user creating the spot
            surf_spot_data: Validated SurfSpotCreate schema with spot data

        Returns:
            Created SurfSpot model instance

        Raises:
            SurfSpotNotInRegionError: If geometry is outside supported regions
        """
        spot_dict = surf_spot_data.model_dump()
        spot_dict["user_id"] = user_id
        return await self.create(surf_spot_data=spot_dict)

    async def update(self, surf_spot_id: int, surf_spot_data: dict) -> SurfSpot:
        """
        Update surf spot by ID - internal/admin method.

        Handles geometry conversion and region validation. Can update any field
        including admin-only fields like is_demo.

        Args:
            surf_spot_id: The ID of the surf spot to update
            surf_spot_data: Dictionary of fields to update

        Returns:
            Updated SurfSpot model instance

        Raises:
            SurfSpotNotFoundError: If spot doesn't exist
            SurfSpotNotInRegionError: If new geometry is outside supported regions
        """
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

    async def update_profile(
        self, surf_spot_id: int, surf_spot_data: SurfSpotUpdate
    ) -> SurfSpot:
        """
        Update surf spot profile - user-facing method.

        Allows updating: name, description, geometry (location), is_active.
        This is the method to use when a spot creator updates their own spot.

        Args:
            surf_spot_id: The ID of the surf spot to update
            profile_data: Validated SurfSpotUpdate schema with user-editable fields

        Returns:
            Updated SurfSpot model instance

        Raises:
            SurfSpotNotFoundError: If spot doesn't exist
            SurfSpotNotInRegionError: If new geometry is outside supported regions
        """

        data = surf_spot_data.model_dump(exclude_unset=True)
        return await self.update(surf_spot_id, surf_spot_data=data)

    async def delete(self, surf_spot_id: int) -> bool:
        """Delete surf spot by ID."""
        surf_spot = await self.get_by_id(surf_spot_id)
        await self.session.delete(surf_spot)
        return True


class SyncSurfSpotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def any_exist(self) -> bool:
        """Check if any surf spots exist in database."""
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
