from models.user_model import User
from models.surf_spot_model import SurfSpot
from utils.location import Location


class SeedFactory:
    """Factory for creating location-specific seed data"""

    @staticmethod
    def get_surf_spots(location: Location, admin_user: User) -> list[SurfSpot]:
        """
        Get surf spots for a specific location.

        Args:
            location: Location enum specifying which location's spots to retrieve
            admin_user: Admin user reference for creating spots

        Returns:
            List of SurfSpot instances for the specified location

        Raises:
            ValueError: If no seed data is available for the location
        """
        from scripts.seed.surf_spots import maui, oahu

        seed_map = {
            Location.MAUI: maui.get_maui_spots,
            Location.OAHU: oahu.get_oahu_spots,
        }

        seed_func = seed_map.get(location)
        if not seed_func:
            raise ValueError(f"No seed data available for location: {location.value}")

        return seed_func(admin_user)
