from functools import lru_cache
from pydantic import BaseModel

from utils.location import Location


# TODO: this may need to be split into sub-models, since a
# an NWPS site typically has multiple cgrids. so idk. but this is also
# supposed to encompass the location configuration specifics,
# so maybe I should seperate the two. will decide on how to setup fully
# once forecast pipeline is working.
class LocationConfig(BaseModel):
    """Configuration for location-specific settings"""

    # NWPS/forecast configuration
    nwps_site_code: str
    nwps_cg_id: int


class MauiLocationConfig(LocationConfig):
    """Maui location configuration"""

    nwps_site_code: str = "HFO"
    nwps_cg_id: int = 4


class OahuLocationConfig(LocationConfig):
    """Oahu location configuration"""

    nwps_site_code: str = "HFO"
    nwps_cg_id: int = 2


LOCATION_CONFIG_REGISTRY: dict[Location, type[LocationConfig]] = {
    Location.MAUI: MauiLocationConfig,
    Location.OAHU: OahuLocationConfig,
}


@lru_cache()
def get_location_config(location: Location | str | None = None) -> LocationConfig:
    """
    Get location configuration based on Location enum or string.

    Args:
        location: Location to load. If None, reads from LOCATION env variable.
                 Can be Location enum or string that will be normalized.

    Returns:
        LocationConfig instance for the specified location
    """
    from utils.location import LocationMapper

    # normalize location using LocationMapper
    if isinstance(location, str):
        normalized_location = LocationMapper.normalize(location)
    elif location is None:
        normalized_location = LocationMapper.normalize()
    else:
        normalized_location = location

    config_cls = LOCATION_CONFIG_REGISTRY[normalized_location]
    return config_cls()  # type: ignore[call-arg] BaseSettings loads from environment
