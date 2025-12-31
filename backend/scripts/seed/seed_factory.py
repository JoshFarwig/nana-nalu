import logging
from models.surf_spot_model import SurfSpot
from utils.region import Region, get_enabled_regions

logger = logging.getLogger(__name__)


class SeedFactory:
    _SEED_MAP = {}

    @classmethod
    def _initialize_seed_map(cls):
        """Lazy-load seed functions to avoid circular imports."""
        if cls._SEED_MAP:
            return

        from scripts.seed.surf_spots import maui
        # TODO: import additional region modules as you create them i.e.
        # from scripts.seed.surf_spots import maui, oahu, big_island

        cls._SEED_MAP = {
            Region.MAUI: maui.get_maui_spots,
            # TODO: create oahu spots and nwps config
            # Region.OAHU: oahu.get_oahu_spots,
        }

    @classmethod
    def get_surf_spots(cls, region: Region, admin_user_id: int) -> list[SurfSpot]:
        cls._initialize_seed_map()

        seed_func = cls._SEED_MAP.get(region)
        if not seed_func:
            raise ValueError(f"No seed data available for region: {region.value}")

        return seed_func(admin_user_id)

    @classmethod
    def get_all_surf_spots(cls, admin_user_id: int) -> list[SurfSpot]:
        """
        Get surf spots for ALL enabled regions based on REGIONS env var.

        Args:
            admin_user_id: Admin user ID for creating spots

        Returns:
            Aggregated list of SurfSpot instances from all enabled regions
            that have seed data available. Logs warnings for regions without
            seed data but continues processing.
        """
        cls._initialize_seed_map()

        enabled_regions = get_enabled_regions()
        all_spots = []

        for region in enabled_regions:
            try:
                spots = cls.get_surf_spots(region, admin_user_id)
                all_spots.extend(spots)

                logger.info(
                    f"Loaded {len(spots)} surf spots for {region.value}",
                    extra={
                        "region": region.value,
                        "count": len(spots),
                    },
                )
            except ValueError as e:
                logger.warning(
                    f"No surf spots set up for {region.value}",
                    extra={"region": region.value, "error": str(e)},
                )
            except Exception as e:
                logger.exception(
                    f"Error loading surf spots for {region.value}: {e}",
                    extra={
                        "region": region.value,
                        "error": str(e),
                    },
                )

        logger.info(
            f"Aggregated {len(all_spots)} total surf spots from "
            f"{len(enabled_regions)} enabled regions",
            extra={
                "total_spots": len(all_spots),
                "enabled_regions": [r.value for r in enabled_regions],
            },
        )

        return all_spots
