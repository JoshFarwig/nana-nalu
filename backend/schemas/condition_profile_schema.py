from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class RangeCondition(BaseModel):
    """
    A min/max range for a single measurement.

    Supports a selected min, a selected max, ranges (min < max) and single values (min == max).
    """

    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def at_least_one_bound(self):
        if self.min is None and self.max is None:
            raise ValueError("Must specify at least one min or max")
        return self

    @model_validator(mode="after")
    def min_lte_max(self):
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("Min must be less than or equal to max")
        return self


class DirectionRangeCondition(BaseModel):
    """A min/max range for direction fields (degrees, 0–360).

    Bounds are validated individually; min > max is valid for north-crossing ranges (e.g., 330°→030°)."""

    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def at_least_one_bound(self):
        if self.min is None and self.max is None:
            raise ValueError("Must specify at least one min or max")
        return self

    @model_validator(mode="after")
    def bounds_in_compass_range(self):
        for name, val in [("min", self.min), ("max", self.max)]:
            if val is not None and not (0 <= val <= 360):
                raise ValueError(
                    f"Direction {name} must be between 0 and 360, got {val}"
                )
        return self


def in_range(value: float | None, condition: RangeCondition) -> bool:
    """Check if value falls within a min/max range. Either bound may be None."""
    if value is None:
        return False
    if condition.min is not None and value < condition.min:
        return False
    if condition.max is not None and value > condition.max:
        return False
    return True


def direction_in_range(value: float | None, condition: DirectionRangeCondition) -> bool:
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


class SwellConditions(BaseModel):
    """
    Condition ranges for a swell partition.

    Maps to SwellPartition fields in ForecastPoint.wave.primary_swell,
    ForecastPoint.wave.secondary_swell, etc.
    """

    height: RangeCondition | None = None  # → swell.height (m)
    period: RangeCondition | None = None  # → swell.period (s)
    direction: DirectionRangeCondition | None = (
        None  # → swell.direction (degrees, wraps around north)
    )


class WaveConditions(BaseModel):
    """
    Condition ranges for wave data.

    Maps to ForecastPoint.wave (WaveData) fields.
    All directions are in "from" convention (0-360°).
    """

    # Total sea state (combined)
    significant_height: RangeCondition | None = None  # → wave.significant_height (m)
    peak_period: RangeCondition | None = None  # → wave.peak_period (s)
    peak_direction: DirectionRangeCondition | None = (
        None  # → wave.peak_direction (degrees, wraps)
    )

    # Wind waves (locally generated)
    wind_wave_height: RangeCondition | None = None  # → wave.wind_wave_height (m)
    wind_wave_period: RangeCondition | None = None  # → wave.wind_wave_period (s)
    wind_wave_direction: DirectionRangeCondition | None = (
        None  # → wave.wind_wave_direction (degrees, wraps)
    )

    # Swell partitions (remotely generated)
    primary_swell: SwellConditions | None = None  # → wave.primary_swell.*
    secondary_swell: SwellConditions | None = None  # → wave.secondary_swell.*


class WindConditions(BaseModel):
    """
    Condition ranges for wind data.

    Maps to ForecastPoint.wind (WindData) fields.
    Direction is in "from" convention (meteorological).
    """

    speed: RangeCondition | None = None  # → wind.speed (m/s)
    direction: DirectionRangeCondition | None = (
        None  # → wind.direction (degrees, wraps)
    )


class TideConditions(BaseModel):
    """
    Condition ranges for tide data.

    Maps to ForecastPoint.tide (TideData) fields.
    """

    height: RangeCondition | None = None  # → tide.height (m)


class ProviderConditionEntry(BaseModel):
    """
    Conditions to match against a specific forecast provider.

    One entry = one provider + one model check. A profile can have multiple entries
    to AND conditions across providers (e.g., NWPS wave + PacIOOS tide).
    """

    provider: str = Field(description='Provider (e.g., "nomads", "pacioos")')
    model: str = Field(description='Model (e.g., "nwps", "tide_mhi")')

    wave: WaveConditions | None = None
    wind: WindConditions | None = None
    tide: TideConditions | None = None
    # TODO: consider adding currents conditions

    @model_validator(mode="after")
    def at_least_one_condition(self):
        """Entry must specify at least one condition category."""
        if not any([self.wave, self.wind, self.tide]):
            raise ValueError(
                "Entry must specify at least one condition category (wave, wind, or tide)"
            )
        return self


# ============================
# Shared Base Models
# ============================


class ConditionProfileBase(BaseModel):
    """Shared fields across condition profile schemas."""

    name: str = Field(min_length=1, max_length=100)
    conditions: list[ProviderConditionEntry]
    is_active: bool = True

    @model_validator(mode="after")
    def no_duplicate_provider_model(self):
        seen = set()
        for entry in self.conditions:
            key = (entry.provider, entry.model)
            if key in seen:
                raise ValueError(
                    f"Duplicate provider+model in conditions: {entry.provider}:{entry.model}. "
                    "Combine into a single entry."
                )
            seen.add(key)
        return self


# ============================
# API Request Schemas
# ============================


class ConditionProfileCreate(ConditionProfileBase):
    """Request schema for creating a condition profile."""

    @field_validator("conditions")
    @classmethod
    def at_least_one_entry(cls, v):
        if not v:
            raise ValueError("Must have at least one provider condition entry")
        return v


class ConditionProfileUpdate(BaseModel):
    """
    Request schema for updating a condition profile.

    All fields optional. conditions is full replacement (not a merge).
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    conditions: list[ProviderConditionEntry] | None = None
    is_active: bool | None = None

    @field_validator("conditions", mode="before")
    @classmethod
    def at_least_one_entry_if_provided(cls, v):
        if v is None or (isinstance(v, list) and not v):
            raise ValueError(
                "Field 'conditions' cannot be null or empty; omit the field to leave unchanged"
            )
        return v

    @model_validator(mode="after")
    def no_duplicate_provider_model(self):
        if self.conditions is None:
            return self
        seen = set()
        for entry in self.conditions:
            key = (entry.provider, entry.model)
            if key in seen:
                raise ValueError(
                    f"Duplicate provider+model in conditions: {entry.provider}:{entry.model}. "
                    "Combine into a single entry."
                )
            seen.add(key)
        return self


# ============================
# API Response Schemas
# ============================


class ConditionProfileResponse(ConditionProfileBase):
    """Response schema for a single condition profile."""

    id: int
    spot_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileMatchResult(BaseModel):
    """Result of matching a single profile against current conditions."""

    profile_id: int
    profile_name: str
    user_id: int
    matched: bool


class ConditionStatus(BaseModel):
    """Condition status for a single surf spot (map view)."""

    spot_id: int
    is_matching: bool  # True if ANY profile matches (OR across profiles)
    matched_count: int  # How many profiles matched
    total_profiles: int  # Total active profiles for this spot
    profiles: list[ProfileMatchResult]


class BatchConditionStatusResponse(BaseModel):
    """Response for batch condition status (all user-visible spots)."""

    spots: list[ConditionStatus]
    evaluated_at: datetime
