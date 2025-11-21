import os
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class Location(str, Enum):
    MAUI = "maui"


class LocationMapper:
    # normalization map
    _LOCATION_MAP = {
        "maui": Location.MAUI,
    }

    @classmethod
    def normalize(cls, location: str | None = None) -> Location:
        """Normalize location type and map to Enum"""

        # default to maui if no value exists for LOCATION
        location = location or os.getenv("LOCATION", Location.MAUI.value)

        normalized_location = cls._LOCATION_MAP.get(location.lower())

        if normalized_location is None:
            raise ValueError(
                f"Unknown location value: {location.lower()}. "
                "Please pass a valid value: " + ", ".join(cls._LOCATION_MAP.keys())
            )

        return normalized_location

    @classmethod
    def is_maui(cls, location: str | None = None) -> bool:
        """Helper method to check if location is Maui"""
        return cls.normalize(location) == Location.MAUI


def get_location(location: str | None = None) -> Location:
    """Get current location from environment"""
    return LocationMapper.normalize(location)


def is_maui() -> bool:
    return LocationMapper.is_maui()
