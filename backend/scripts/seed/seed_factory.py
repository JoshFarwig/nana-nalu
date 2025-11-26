import logging
from models.user_model import User
from models.surf_spot_model import SurfSpot
from utils.location import Location, load_locations

logger = logging.getLogger(__name__)


class SeedFactory:
    _SEED_MAP = {}

    @classmethod
    def _initialize_seed_map(cls):
        """Lazy-load seed functions to avoid circular imports."""
        if cls._SEED_MAP:
            return

        from scripts.seed.surf_spots import maui
        # TODO: import additional location modules as you create them i.e.
        # from scripts.seed.surf_spots import maui, oahu, big_island

        cls._SEED_MAP = {
            Location.MAUI: maui.get_maui_spots,
            # TODO: create oahu spots and nwps config
            # Location.OAHU: oahu.get_oahu_spots,
        }

    @classmethod
    def get_surf_spots(cls, location: Location, admin_user: User) -> list[SurfSpot]:
        cls._initialize_seed_map()

        seed_func = cls._SEED_MAP.get(location)
        if not seed_func:
            raise ValueError(f"No seed data available for location: {location.value}")

        return seed_func(admin_user)

    @classmethod
    def get_all_surf_spots(cls, admin_user: User) -> list[SurfSpot]:
        """
        Get surf spots for ALL enabled locations based on LOCATIONS env var.

        Args:
            admin_user: Admin user reference for creating spots

        Returns:
            Aggregated list of SurfSpot instances from all enabled locations
            that have seed data available. Logs warnings for locations without
            seed data but continues processing.
        """
        cls._initialize_seed_map()

        enabled_locations = load_locations()
        all_spots = []

        for location in enabled_locations:
            try:
                spots = cls.get_surf_spots(location, admin_user)
                all_spots.extend(spots)

                logger.info(
                    f"Loaded {len(spots)} surf spots for {location.value}",
                    extra={
                        "location": location.value,
                        "count": len(spots),
                    },
                )
            except ValueError as e:
                logger.warning(
                    f"No surf spots set up for {location.value}",
                    extra={"location": location.value, "error": str(e)},
                )
            except Exception as e:
                logger.exception(
                    f"Error loading surf spots for {location.value}: {e}",
                    extra={
                        "location": location.value,
                        "error": str(e),
                    },
                )

        logger.info(
            f"Aggregated {len(all_spots)} total surf spots from "
            f"{len(enabled_locations)} enabled locations",
            extra={
                "total_spots": len(all_spots),
                "enabled_locations": [loc.value for loc in enabled_locations],
            },
        )

        return all_spots
