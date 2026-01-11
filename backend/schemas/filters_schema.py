from pydantic import BaseModel, Field


class FiltersBase(BaseModel):
    limit: int = Field(10, gt=0, le=100)
    offset: int = Field(0, ge=0)


class UserFilters(FiltersBase):
    pass


class SurfSpotFilters(FiltersBase):
    is_active: bool = True


class AdminSurfSpotFilters(SurfSpotFilters):
    is_demo: bool
