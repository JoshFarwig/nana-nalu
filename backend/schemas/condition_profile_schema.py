"""
Data Schema used by the condition profiles
Stored as the JSONB condition field in the ConditionProfile table
Uses exact same format as the ProviderForecast Schema setup
"""

from pydantic import BaseModel


class RangeCondition(BaseModel):
    min: float
    max: float


class WaveConditions(BaseModel):
    height: RangeCondition | None = None
    primary_swell_height: RangeCondition | None = None
    primay_swell_period: RangeCondition | None = None
    primary_swell_direction: RangeCondition | None = None

