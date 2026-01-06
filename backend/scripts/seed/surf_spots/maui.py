from models.surf_spot_model import SurfSpot
from geoalchemy2.elements import WKTElement
from utils.region import Region


def get_maui_spots(admin_user_id: int) -> list[SurfSpot]:
    surf_spots = [
        SurfSpot(
            name="Ho'okipa (Point)",
            description="The iconic NSB grom-grounds (Point, Middles, Pavillions)",
            location=WKTElement("POINT(-156.3596 20.9342)", srid=4326),
            region=Region.MAUI.value,
            is_active=True,
            is_demo=True,
            created_by_id=admin_user_id,
        ),
        SurfSpot(
            name="Honolua Bay (Point)",
            description="The legendary west-side point break",
            location=WKTElement("POINT(-156.6410 21.0176)", srid=4326),
            region=Region.MAUI.value,
            is_active=True,
            is_demo=True,
            created_by_id=admin_user_id,
        ),
        SurfSpot(
            name="Dumps",
            description="Iconic south-side left (and right if you're nutz)",
            location=WKTElement("POINT(-156.5480 20.6129)", srid=4326),
            region=Region.MAUI.value,
            is_active=True,
            is_demo=True,
            created_by_id=admin_user_id,
        ),
    ]

    return surf_spots
