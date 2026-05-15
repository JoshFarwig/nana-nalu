from datetime import datetime

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

from core.exceptions.forecasts import (
    InvalidModelError,
    InvalidProviderError,
    UnknownRegionError,
)
from domain.keys import ModelRunKey, validate_run_combo
from domain.models import PROVIDER_MODELS
from domain.provider import ForecastProvider
from domain.region import Region, get_enabled_regions

_key_adapter = TypeAdapter(ModelRunKey)


class FiltersBase(BaseModel):
    limit: int = Field(10, gt=0, le=100)
    offset: int = Field(0, ge=0)


class ForecastTimeFilter(BaseModel):
    valid_time: datetime | None = None
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def validate_time_filter(self) -> "ForecastTimeFilter":
        if self.valid_time and (self.start or self.end):
            raise ValueError("Provide valid_time or start/end, not both")
        if bool(self.start) != bool(self.end):
            raise ValueError("Provide both start and end for range queries")
        return self


class ForecastProviderFilter(ForecastTimeFilter):
    """Shared base: validates (provider, model) pair before any subclass logic."""

    provider: ForecastProvider
    model: str

    @field_validator("provider", mode="before")
    @classmethod
    def validate_provider_value(cls, v: object) -> object:
        valid = [p.value for p in ForecastProvider]
        if isinstance(v, str) and v not in valid:
            raise InvalidProviderError(v, valid)
        return v

    @model_validator(mode="after")
    def validate_provider_model(self) -> "ForecastProviderFilter":
        valid = PROVIDER_MODELS.get(self.provider, set())
        if self.model not in valid:
            raise InvalidModelError(self.provider.value, self.model, sorted(valid))
        return self


class PointForecastFilter(ForecastProviderFilter):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(
        ...,
        ge=-180,
        le=360,
        description="Longitude (-180..180 or 0..360, normalized server-side)",
    )

    @field_validator("lon")
    @classmethod
    def _normalize_lon(cls, v: float) -> float:
        return v + 360 if v < 0 else v


class GridForecastFilter(ForecastProviderFilter):
    region: Region

    @field_validator("region", mode="before")
    @classmethod
    def validate_region_value(cls, v: object) -> object:
        valid = [r.value for r in Region]
        if isinstance(v, str) and v not in valid:
            raise UnknownRegionError(v, [r.value for r in get_enabled_regions()])
        return v

    @model_validator(mode="after")
    def validate_region_enabled(self) -> "GridForecastFilter":
        enabled = get_enabled_regions()
        if self.region not in enabled:
            raise UnknownRegionError(self.region.value, [r.value for r in enabled])
        return self

    @model_validator(mode="after")
    def validate_run_combo(self) -> "GridForecastFilter":
        key: ModelRunKey = _key_adapter.validate_python(
            {
                "provider": self.provider.value,
                "model": self.model,
                "region": self.region.value,
            }
        )
        validate_run_combo(key)
        return self
