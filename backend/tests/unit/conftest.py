"""
Unit test fixtures

Provides factory helpers for building forecast data and condition profiles
used across unit tests.
"""

import pytest
from datetime import datetime, timezone

from services.forecast.forecast_schema import (
    ForecastPoint,
    WaveData,
    WindData,
    TideData,
    SwellPartition,
)


@pytest.fixture
def make_forecast_point():
    """Factory for building ForecastPoint with optional overrides."""

    def _make(
        valid_time: datetime | None = None,
        wave: dict | None = None,
        wind: dict | None = None,
        tide: dict | None = None,
    ) -> ForecastPoint:
        return ForecastPoint(
            valid_time=valid_time or datetime.now(timezone.utc),
            wave=WaveData(**wave) if wave else None,
            wind=WindData(**wind) if wind else None,
            tide=TideData(**tide) if tide else None,
        )

    return _make


@pytest.fixture
def make_swell():
    """Factory for building SwellPartition dicts."""

    def _make(
        height: float | None = None,
        period: float | None = None,
        direction: float | None = None,
    ) -> dict:
        return {
            k: v
            for k, v in {
                "height": height,
                "period": period,
                "direction": direction,
            }.items()
            if v is not None
        }

    return _make


@pytest.fixture
def typical_wave_point(make_forecast_point):
    """A realistic Maui north shore forecast point."""

    return make_forecast_point(
        wave={
            "significant_height": 2.1,
            "peak_period": 14.0,
            "peak_direction": 350.0,
            "wind_wave_height": 0.8,
            "wind_wave_period": 6.0,
            "wind_wave_direction": 45.0,
            "primary_swell": SwellPartition(height=1.8, period=15.0, direction=340.0),
            "secondary_swell": SwellPartition(height=0.6, period=10.0, direction=200.0),
        },
        wind={"speed": 5.5, "direction": 60.0},
        tide={"height": 0.3},
    )
