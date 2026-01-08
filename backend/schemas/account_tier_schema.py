from pydantic import BaseModel, Field, model_validator


# ============================================================================
# Shared Base Models
# ============================================================================


class AccountTierBase(BaseModel):
    """Base fields for account tier"""

    display_name: str = Field(max_length=25)

    spots_quota: int = Field(gt=0)
    max_active_spots: int = Field(gt=0)

    max_crews: int = Field(gt=0)
    max_crew_members: int = Field(gt=0)

    price_monthly_cents: int = Field(ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_max_active_spots(self):
        """Validate max_active_spots against spots_quota."""
        if self.max_active_spots > self.spots_quota:
            raise ValueError(
                f"max_active_spots ({self.max_active_spots}) must be <= "
                f"spots_quota ({self.spots_quota})"
            )
        return self


# ============================================================================
# API Request Schemas
# ============================================================================


class AccountTierCreate(AccountTierBase):
    name: str = Field(max_length=25)


class AccountTierUpdate(BaseModel):
    """Schema for updating an account tier (all fields optional)."""

    display_name: str | None = Field(default=None, max_length=25)
    spots_quota: int | None = Field(default=None, gt=0)
    max_active_spots: int | None = Field(default=None, gt=0)
    max_crews: int | None = Field(default=None, gt=0)
    max_crew_members: int | None = Field(default=None, gt=0)
    price_monthly_cents: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_max_active_spots(self):
        """Validate max_active_spots against spots_quota."""
        if self.max_active_spots is not None and self.spots_quota is not None:
            if self.max_active_spots > self.spots_quota:
                raise ValueError(
                    f"max_active_spots ({self.max_active_spots}) must be <= "
                    f"spots_quota ({self.spots_quota})"
                )
        return self


# ============================================================================
# API Response Schemas
# ============================================================================


class AccountTierResponse(AccountTierBase):
    """Schema for account tier responses."""

    id: int
    name: str

    model_config = {"from_attributes": True}
