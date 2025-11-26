import os
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class Location(str, Enum):
    MAUI = "maui"
    # OAHU = "oahu"


def load_locations(locations_str: str | None = None) -> set[Location]:
    if locations_str is None:
        locations_str = os.getenv("LOCATIONS", "")

    valid_locations = set()
    invalid_locations = []

    for loc in locations_str.split(","):
        loc_clean = loc.strip().lower()
        if not loc_clean:
            continue
        try:
            valid_locations.add(Location(loc_clean))
        except ValueError:
            invalid_locations.append(loc_clean)

    if invalid_locations:
        valid_locs = [loc.value for loc in Location]
        logger.warning(
            f"Ignoring invalid locations: {invalid_locations}. "
            f"Valid locations: {valid_locs}"
        )

    if not valid_locations:
        logger.warning("No valid locations configured. Defaulting to maui.")
        valid_locations.add(Location.MAUI)

    logger.info(f"Enabled locations: {sorted([loc.value for loc in valid_locations])}")

    return valid_locations
