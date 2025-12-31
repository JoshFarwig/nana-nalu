from models.surf_spot_model import SurfSpot
from models.surfline_spot import SurflineSpot
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
            created_by_id=admin_user_id,
            surfline_spot=SurflineSpot(surfline_id="5842041f4e65fad6a7708de8"),
        ),
        SurfSpot(
            name="Honolua Bay (Point)",
            description="The legendary west-side point break",
            location=WKTElement("POINT(-156.6410 21.0176)", srid=4326),
            region=Region.MAUI.value,
            is_active=True,
            created_by_id=admin_user_id,
            surfline_spot=SurflineSpot(surfline_id="5842041f4e65fad6a7708de4"),
        ),
        SurfSpot(
            name="Olowalu",
            description="West-side beach break",
            location=WKTElement("POINT(-156.6309 20.8216)", srid=4326),
            region=Region.MAUI.value,
            is_active=True,
            created_by_id=admin_user_id,
            surfline_spot=SurflineSpot(surfline_id="5842041f4e65fad6a7708de0"),
        ),
        SurfSpot(
            name="Dumps",
            description="Iconic south-side left (and right if you're nutz)",
            location=WKTElement("POINT(-156.5480 20.6129)", srid=4326),
            region=Region.MAUI.value,
            is_active=True,
            created_by_id=admin_user_id,
            surfline_spot=SurflineSpot(surfline_id="5842041f4e65fad6a7708b2b"),
        ),
        SurfSpot(
            name="Hamoa beach",
            description="Hana's day dream point and beach break (and sandbar one bay over)",
            location=WKTElement("POINT(-155.9865 20.7184)", srid=4326),
            region=Region.MAUI.value,
            is_active=True,
            created_by_id=admin_user_id,
        ),
    ]

    return surf_spots
