import logging
import asyncio

from datetime import datetime, timezone
from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from models.condition_profile_model import ConditionProfile

from schemas.condition_profile_schema import (
    ProviderConditionEntry,
    ConditionStatus,
    ProfileMatchResult,
    BatchConditionStatusResponse,
    direction_in_range,
    in_range,
)

from services.forecast.forecast_schema import ForecastPoint
from services.forecast.forecast_service import ForecastService

from repositories.condition_profile_repository import AsyncConditionProfileRepository
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from services.policies.condition_profile_policy import ConditionProfilePolicy
from services.policies.surf_spot_policy import SurfSpotPolicy

from schemas.condition_profile_schema import (
    ConditionProfileCreate,
    ConditionProfileUpdate,
)


logger = logging.getLogger(__name__)


class ConditionProfileService:
    def __init__(
        self,
        forecast_service: ForecastService,
        profile_repo: AsyncConditionProfileRepository,
        spot_repo: AsyncSurfSpotRepository,
        profile_policy: ConditionProfilePolicy,
        spot_policy: SurfSpotPolicy,
        session: AsyncSession,
    ):
        self.forecast_service = forecast_service
        self.profile_repo = profile_repo
        self.spot_repo = spot_repo
        self.profile_policy = profile_policy
        self.spot_policy = spot_policy
        self.session = session

    async def get_profile(self, user_id: int, profile_id: int) -> ConditionProfile:
        profile = await self.profile_repo.get_by_id(profile_id)
        await self.profile_policy.require_view_access(user_id, profile)
        return profile

    async def get_user_profiles(self, user_id: int) -> Sequence[ConditionProfile]:
        return await self.profile_repo.get_all_by_user_id(user_id)

    async def get_spot_profiles(
        self, user_id: int, spot_id: int
    ) -> Sequence[ConditionProfile]:
        spot = await self.spot_repo.get_by_id(spot_id)
        await self.spot_policy.require_view_access(user_id, spot)
        return await self.profile_repo.get_all_by_spot_id(spot_id)

    async def create_profile(
        self, user_id: int, spot_id: int, data: ConditionProfileCreate
    ) -> ConditionProfile:
        spot = await self.spot_repo.get_by_id(spot_id)
        await self.spot_policy.require_view_access(user_id, spot)
        profile = await self.profile_repo.create_from_user(user_id, spot_id, data)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def update_profile(
        self, user_id: int, profile_id: int, data: ConditionProfileUpdate
    ) -> ConditionProfile:
        profile = await self.profile_repo.get_by_id(profile_id)
        self.profile_policy.require_ownership(user_id, profile, "update")
        profile = await self.profile_repo.update_from_user(profile_id, data)
        await self.session.commit()
        await self.session.refresh(profile)
        return profile

    async def delete_profile(self, user_id: int, profile_id: int) -> bool:
        profile = await self.profile_repo.get_by_id(profile_id)
        self.profile_policy.require_ownership(user_id, profile, "delete")
        await self.profile_repo.delete(profile_id)
        await self.session.commit()
        return True

    async def evalute_all_viewable_condition_profiles(
        self, user_id: int
    ) -> BatchConditionStatusResponse:
        """Evaluate all profiles the user owns or has been shared with them."""

        profiles = await self.profile_repo.get_all_viewable_for_user(user_id)
        return await self._evaluate_profiles(profiles)

    async def evalute_all_user_condition_profiles(
        self, user_id: int
    ) -> BatchConditionStatusResponse:
        """Evaluate only profiles owned by the user (excludes shared profiles)."""

        profiles = await self.profile_repo.get_all_by_user_id(user_id)
        return await self._evaluate_profiles(profiles)

    async def evalute_condition_profile(
        self, profile_id: int
    ) -> BatchConditionStatusResponse:
        """Evaluate a single profile by ID."""

        profile = await self.profile_repo.get_by_id(profile_id)
        return await self._evaluate_profiles([profile])

    async def _evaluate_profiles(
        self, profiles: Sequence[ConditionProfile]
    ) -> BatchConditionStatusResponse:
        """Batch-evaluate profiles: fetches only the needed forecasts per spot concurrently,
        then scores each profile against the nearest forecast point."""

        # group profiles by spot and collect only the provider+model pairs each spot needs
        spots_with_profiles: dict[int, list[ConditionProfile]] = defaultdict(list)
        needed_per_spot: dict[int, set[tuple[str, str]]] = defaultdict(set)

        for profile in profiles:
            spots_with_profiles[profile.spot_id].append(profile)
            for entry in [
                ProviderConditionEntry.model_validate(e) for e in profile.conditions
            ]:
                needed_per_spot[profile.spot_id].add((entry.provider, entry.model))

        # fetch only needed forecasts per spot
        # one pipeline round-trip per spot, all spots concurrent
        spot_id_list = list(spots_with_profiles.keys())
        raw_lookups = await asyncio.gather(
            *[
                self.forecast_service.get_forecasts_for_providers(
                    spot_id, needed_per_spot[spot_id]
                )
                for spot_id in spot_id_list
            ],
            return_exceptions=True,
        )

        # build flat (spot_id, provider, model) → nearest ForecastPoint lookup
        now = datetime.now(timezone.utc)
        forecast_lookup: dict[tuple[int, str, str], ForecastPoint | None] = {}
        for spot_id, provider_forecasts in zip(spot_id_list, raw_lookups):
            if isinstance(provider_forecasts, BaseException):
                logger.warning(
                    f"Forecast fetch failed for spot {spot_id}",
                    exc_info=provider_forecasts,
                    extra={
                        "spot_id": spot_id,
                        "error_type": type(provider_forecasts).__name__,
                    },
                )
                continue
            for (provider, model), pf in provider_forecasts.items():
                forecast_lookup[(spot_id, provider, model)] = (
                    self._find_nearest_forecast_point(pf.forecast, now) if pf else None
                )

        # evaluate each profile against the flat lookup
        results = []
        for spot_id, spot_profiles in spots_with_profiles.items():
            profile_results = []
            for profile in spot_profiles:
                matched = self._evaluate_profile(profile, forecast_lookup)
                profile_results.append(
                    ProfileMatchResult(
                        profile_id=profile.id,
                        profile_name=profile.name,
                        user_id=profile.user_id,
                        matched=matched,
                    )
                )

            matched_count = sum(1 for r in profile_results if r.matched)
            results.append(
                ConditionStatus(
                    spot_id=spot_id,
                    is_matching=matched_count > 0,
                    matched_count=matched_count,
                    total_profiles=len(spot_profiles),
                    profiles=profile_results,
                )
            )

        return BatchConditionStatusResponse(
            spots=results,
            evaluated_at=now,
        )

    def _find_nearest_forecast_point(
        self, forecasts: list[ForecastPoint], now: datetime
    ) -> ForecastPoint | None:
        """Finds nearest forecast point with a time closest to now
        (simple lambda w/ min, O(n) search for n ~ 200 forecast points)"""

        if not forecasts:
            return None

        return min(forecasts, key=lambda p: abs(p.valid_time - now))

    def _evaluate_profile(
        self,
        profile: ConditionProfile,
        forecast_lookup: dict[tuple[int, str, str], ForecastPoint | None],
    ) -> bool:
        """
        Evaluate a profile against the flat (spot_id, provider, model) forecast lookup.

        ALL entries in the profile's conditions list must match (AND logic).
        """
        entries = [ProviderConditionEntry.model_validate(e) for e in profile.conditions]

        for entry in entries:
            forecast_point = forecast_lookup.get(
                (profile.spot_id, entry.provider, entry.model)
            )

            if forecast_point is None:
                return False  # provider data unavailable, can't confirm

            if not self._entry_matches(entry, forecast_point):
                return False

        return True

    def _entry_matches(
        self, entry: ProviderConditionEntry, point: ForecastPoint
    ) -> bool:
        """
        Check if a single provider's forecast point matches all conditions in the entry.
        AND logic: every specified field must be in range for this to return True.
        """

        if entry.wave:
            if not point.wave:
                return False

            if entry.wave.significant_height:
                if not in_range(
                    point.wave.significant_height, entry.wave.significant_height
                ):
                    return False
            if entry.wave.peak_period:
                if not in_range(point.wave.peak_period, entry.wave.peak_period):
                    return False
            if entry.wave.peak_direction:
                if not direction_in_range(
                    point.wave.peak_direction, entry.wave.peak_direction
                ):
                    return False
            if entry.wave.wind_wave_height:
                if not in_range(
                    point.wave.wind_wave_height, entry.wave.wind_wave_height
                ):
                    return False
            if entry.wave.wind_wave_period:
                if not in_range(
                    point.wave.wind_wave_period, entry.wave.wind_wave_period
                ):
                    return False
            if entry.wave.wind_wave_direction:
                if not direction_in_range(
                    point.wave.wind_wave_direction, entry.wave.wind_wave_direction
                ):
                    return False
            if entry.wave.primary_swell:
                if not point.wave.primary_swell:
                    return False
                if not self._swell_matches(
                    point.wave.primary_swell, entry.wave.primary_swell
                ):
                    return False
            if entry.wave.secondary_swell:
                if not point.wave.secondary_swell:
                    return False
                if not self._swell_matches(
                    point.wave.secondary_swell, entry.wave.secondary_swell
                ):
                    return False

        if entry.wind:
            if not point.wind:
                return False
            if entry.wind.speed:
                if not in_range(point.wind.speed, entry.wind.speed):
                    return False
            if entry.wind.direction:
                if not direction_in_range(point.wind.direction, entry.wind.direction):
                    return False

        if entry.tide:
            if not point.tide:
                return False
            if entry.tide.height:
                if not in_range(point.tide.height, entry.tide.height):
                    return False

        return True

    def _swell_matches(
        self,
        swell,
        conditions,
    ) -> bool:
        """Check if a swell partition matches conditions (AND across specified fields)."""

        if conditions.height and not in_range(swell.height, conditions.height):
            return False
        if conditions.period and not in_range(swell.period, conditions.period):
            return False
        if conditions.direction and not direction_in_range(
            swell.direction, conditions.direction
        ):
            return False
        return True
