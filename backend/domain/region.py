import os
import logging
from enum import Enum
from functools import cache

from pydantic import BaseModel, ConfigDict, model_validator

logger = logging.getLogger(__name__)


class RegionGrid(BaseModel):
    """Geographic bounds for a region."""

    model_config = ConfigDict(frozen=True)

    lat_min: float
    lat_max: float
    long_min: float
    long_max: float

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.lat_min >= self.lat_max:
            raise ValueError(
                f"lat_min ({self.lat_min}) must be less than lat_max ({self.lat_max})"
            )
        if self.long_min >= self.long_max:
            raise ValueError(
                f"long_min ({self.long_min}) must be less than long_max ({self.long_max})"
            )
        return self

    def contains(self, lat: float, lon: float) -> bool:
        return (
            self.lat_min <= lat <= self.lat_max
            and self.long_min <= lon <= self.long_max
        )


class Region(str, Enum):
    """
    Geographic regions for forecast coverage.

    Each region has associated grid bounds defining its geographic extent.
    Enable/disable regions via the REGIONS environment variable.
    """

    MAUI = "maui"
    # future: OAHU, BIG_ISLAND, KAUAI, etc.

    @property
    def grid(self) -> RegionGrid:
        return REGION_GRIDS[self]


REGION_GRIDS: dict[Region, RegionGrid] = {
    Region.MAUI: RegionGrid(
        lat_min=20.553,
        lat_max=21.042,
        long_min=-156.720,
        long_max=-155.954,
    ),
}


def load_regions(regions_str: str | None = None) -> set[Region]:
    if regions_str is None:
        regions_str = os.getenv("REGIONS", "")

    valid_regions: set[Region] = set()
    invalid_regions: list[str] = []

    for region in regions_str.split(","):
        region_clean = region.strip().lower()
        if not region_clean:
            continue
        try:
            valid_regions.add(Region(region_clean))
        except ValueError:
            invalid_regions.append(region_clean)

    if invalid_regions:
        valid_names = [r.value for r in Region]
        logger.warning(
            f"Ignoring invalid regions: {invalid_regions}. Valid regions: {valid_names}"
        )

    if not valid_regions:
        logger.warning("No valid regions configured. Defaulting to maui.")
        valid_regions.add(Region.MAUI)

    return valid_regions


@cache
def get_enabled_regions() -> frozenset[Region]:
    return frozenset(load_regions(regions_str=None))


def resolve_region(lat: float, lon: float) -> Region | None:
    for region in get_enabled_regions():
        if region.grid.contains(lat, lon):
            return region
    return None
