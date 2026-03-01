import pytest
from pydantic import ValidationError

from schemas.surf_spot_schema import SurfSpotCreate, SurfSpotUpdate


def make_geometry(lon: float = -156.3, lat: float = 20.8) -> dict:
    return {"type": "Point", "coordinates": [lon, lat]}


@pytest.mark.unit
class TestSurfSpotCreate:
    def test_valid_geometry(self):
        spot = SurfSpotCreate(name="Honolua Bay", geometry=make_geometry())
        assert spot.geometry["type"] == "Point"

    def test_non_point_type_rejected(self):
        with pytest.raises(ValidationError):
            SurfSpotCreate(
                name="Test",
                geometry={"type": "LineString", "coordinates": [[-156.3, 20.8]]},
            )

    def test_missing_coordinates_rejected(self):
        with pytest.raises(ValidationError):
            SurfSpotCreate(name="Test", geometry={"type": "Point"})

    def test_wrong_coordinate_count_rejected(self):
        with pytest.raises(ValidationError):
            SurfSpotCreate(
                name="Test",
                geometry={"type": "Point", "coordinates": [-156.3]},
            )

    def test_non_numeric_coordinates_rejected(self):
        with pytest.raises(ValidationError):
            SurfSpotCreate(
                name="Test",
                geometry={"type": "Point", "coordinates": ["west", "north"]},
            )

    def test_longitude_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            SurfSpotCreate(name="Test", geometry=make_geometry(lon=181.0))

    def test_latitude_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            SurfSpotCreate(name="Test", geometry=make_geometry(lat=91.0))

    def test_boundary_coordinates_valid(self):
        assert SurfSpotCreate(name="Test", geometry=make_geometry(lon=180.0, lat=90.0))
        assert SurfSpotCreate(
            name="Test", geometry=make_geometry(lon=-180.0, lat=-90.0)
        )


@pytest.mark.unit
class TestSurfSpotUpdate:
    def test_none_geometry_allowed(self):
        spot = SurfSpotUpdate(name="Updated Name", geometry=None)
        assert spot.geometry is None

    def test_valid_geometry_update(self):
        spot = SurfSpotUpdate(geometry=make_geometry())
        assert spot.geometry is not None
        assert spot.geometry["type"] == "Point"

    def test_invalid_geometry_update_rejected(self):
        with pytest.raises(ValidationError):
            SurfSpotUpdate(geometry={"type": "Point", "coordinates": [999.0, 20.8]})
