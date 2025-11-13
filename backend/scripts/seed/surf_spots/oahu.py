from models import User, SurfSpot
from geoalchemy2.elements import WKTElement


def get_oahu_spots(admin_user: User) -> list[SurfSpot]:
    """Get Oahu surf spots for seeding"""

    raise NotImplementedError("Complete full forecasting pipeline first!")
