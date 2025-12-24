from fastapi import APIRouter

# add response schemas

router = APIRouter(prefix="/surf_spots", tags=["forecast", "surf_spots"])

# api/surf_spots
#   - return all surf spots with base data
#
# api/surf_spots/{id}
#   - return base data of the surf_spot
#
# api/surf_spots/{id}/forecasts -> can have different providers
#   - this would return all forecast proviers and their data for this spot
#
# api/surf_spots/{id}/forecasts/{provider}
#   - returns specific provider forecast data


@router.get("/")
def get_all_surfspots():
    pass

@router.get("/{id}")
