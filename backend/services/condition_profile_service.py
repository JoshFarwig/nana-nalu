from datetime import datetime, timezone
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from models.condition_profile_model import ConditionProfile
from schemas.condition_profile_schema import ProviderConditionEntry
from services.forecast.forecast_schema import ForecastPoint, ProviderForecast
from services.forecast.forecast_service import ForecastService
from repositories.condition_profile_repository import AsyncConditionProfileRepository
from repositories.surf_spot_repository import AsyncSurfSpotRepository


class ConditionProfileService:
    def __init__(
        self,
        forecast_service: ForecastService,
        profile_repo: AsyncConditionProfileRepository,
        spot_repo: AsyncSurfSpotRepository,
        session: AsyncSession,
    ):
        self.forecast_service = forecast_service
        self.profile_repo = profile_repo
        self.spot_repo = spot_repo
        self.session = session

    async def evalute_all_viewable_condition_profiles(self, user_id: int):
        # get all viewable spots, i.e. user owned spots + crew spots
        # load all profiles via get all for spot ids
        # group profiles by spot id

        viewable_spots = await self.spot_repo.get_all_user_viewable_spots(user_id)

        spot_ids = {spot.id for spot in viewable_spots}

        spot_condition_profiles = await self.profile_repo.get_all_for_spot_ids(spot_ids)

        spots_with_profiles: dict[int, list[ConditionProfile]] = defaultdict(list)
        for profile in spot_condition_profiles:
            if profile.spot_id in spot_ids:
                spots_with_profiles[profile.spot_id].append(profile)

        # for each spot with a matching profile, fetch all provider forecasts from redis
        # 1) build the provider lookup find key closest to the time right now
        # 2) evaluate each profile against the lookup
        # build spot condition status responses
        # return the batched conition status response with evalute at timestamp

        for spot_id, profiles in spots_with_profiles.items():
            redis_forecast_keys = {
                f"{entry.provider}:{entry.model}"
                for profile in profiles
                for entry in profile.conditions
            }

        pass

    async def evaluate_user_condition_profiles(self, user_id: int):
        # Same thing but only for condition prorfiles created by the user.
        pass

    async def _build_provider_forecast_lookup(
        self, spot_id: int
    ) -> ForecastPoint | None:
        """
        Build a lookup of provider_key → nearest ForecastPoint to now().

        Each provider's forecast timeseries is searched for the point closest
        to the current time. Since forecasts are hourly timesteps from model
        runs that happen 1-2x/day, "nearest to now" gives the best available
        prediction for current conditions.

        Returns:
            {"nomads:nwps": ForecastPoint, "pacioos:tide_mhi": ForecastPoint, ...}
        """

        forecasts: list[ProviderForecast] = await self.forecast_service.get_forecasts(
            spot_id
        )
        now = datetime.now(timezone.utc)

        lookup = {}
        for pf in forecasts:
            provider_key = f"{pf.provider.value}:{pf.model.value}"
            nearest = self._find_nearest_forecast_point(pf.forecast, now)
            if nearest:
                lookup[provider_key] = nearest

        return lookup

    async def _evaluate_profile(
        self, profile: ConditionProfile, provider_lookup: dict[str, ForecastPoint]
    ):
        """
        Evaluate a profile against provider forecast data.

        ALL entries in the profile's conditions list must match (AND logic).
        Each entry specifies a provider and conditions to check against that
        provider's nearest forecast point.
        """

        condition_entries = [ProviderConditionEntry(**e) for e in profile.conditions]

        pass

    async def _entry_matches(
        self, entry: ProviderConditionEntry, point: ForecastPoint
    ) -> bool:
        # check if a single provider's forecast point mathches the entrie's conditions
        return True

    async def _swell_matches(self) -> bool:
        # helper to check if swell partition matches conditions
        return True

    @staticmethod
    def _in_range(value: float | None, condition) -> bool:
        """Check if value falls within a min/max range. Either bound may be None."""
        if value is None:
            return False
        if condition.min is not None and value < condition.min:
            return False
        if condition.max is not None and value > condition.max:
            return False
        return True

    @staticmethod
    def _direction_in_range(value: float | None, condition) -> bool:
        """
        Check if a direction falls within a range, handling north-crossing wraps.

        Wrapping only applies when both bounds are set and min > max (e.g., 330°→030°).
        One-sided bounds fall back to standard comparison.
        """
        if value is None:
            return False
        if condition.min is not None and condition.max is not None:
            if condition.min > condition.max:
                return value >= condition.min or value <= condition.max
            return condition.min <= value <= condition.max
        if condition.min is not None and value < condition.min:
            return False
        if condition.max is not None and value > condition.max:
            return False
        return True
