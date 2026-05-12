from datetime import datetime

from pydantic import BaseModel, Field, model_validator


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


class PointForecastFilter(ForecastTimeFilter):
    provider: str
    model: str
    region: str
    lat: float
    lon: float = Field(..., ge=0, le=360, description="Longitude 0-360")


class GridForecastFilter(ForecastTimeFilter):
    provider: str
    model: str
    region: str
