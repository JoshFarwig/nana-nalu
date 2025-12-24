from pydantic import BaseModel, ConfigDict, Field, model_validator


class Grid(BaseModel):
    model_config = ConfigDict(frozen=True)

    lat_min: float = Field(
        ge=-90,
        le=90,
    )
    lat_max: float = Field(
        ge=-90,
        le=90,
    )
    long_min: float = Field(
        ge=-180,
        le=180,
    )
    long_max: float = Field(
        ge=-180,
        le=180,
    )

    @model_validator(mode="after")
    def validate_min_max(self):
        if self.lat_min >= self.lat_max:
            raise ValueError(
                f"lat_min ({self.lat_min}) must be less than lat_max ({self.lat_max})"
            )
        if self.long_min >= self.long_max:
            raise ValueError(
                f"long_min ({self.long_min}) must be less than long_max ({self.long_max})"
            )
        return self


class MauiGrid(Grid):
    lat_min: float = 20.553
    lat_max: float = 21.042
    long_min: float = -156.720
    long_max: float = -155.954
