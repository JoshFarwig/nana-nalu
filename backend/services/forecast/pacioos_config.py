import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from utils.region import Region, RegionGrid, get_enabled_regions

logger = logging.getLogger(__name__)


# =======================
# CORE CONFIGURATIONS
# =======================


class PacIOOSModel(str, Enum):
    """
    Available PacIOOS ocean models.

    Generic model types - location determines regional variant.
    """

    TIDE_MHI = "tide_mhi"
    SWAN = "swan"
    WRF = "wrf"
    ROMS = "roms"


class PacIOOSModelConfig(BaseModel):
    """Base configuration for all PacIOOS models."""

    model_config = ConfigDict(frozen=True)

    region: Region  # geographic region (MAUI, OAHU, etc.)
    model_name: PacIOOSModel
    provider_name: Literal["pacioos"] = "pacioos"

    # ERDDAP GridDAP access
    erddap_base_url: str = "https://pae-paha.pacioos.hawaii.edu/erddap"
    dataset_id: str

    forecast_horizon_days: int
    max_forecast_age_hours: int
    time_step_hours: int

    max_nearest_neighbor_distance_km: float

    # variables to fetch from dataset
    data_variables: list[str]

    # human-readable descriptions of data categories for client context
    data_summary: dict[str, str] = Field(
        default={},
        description="Category-level descriptions of what each data type represents",
    )

    @property
    def grid(self) -> RegionGrid:
        """Get grid bounds from the region."""
        return self.region.grid

    @property
    def griddap_url(self) -> str:
        """ERDDAP GridDAP URL for fast grid subset downloads."""
        return f"{self.erddap_base_url}/griddap/{self.dataset_id}"

    @property
    def catalog_url(self) -> str:
        """ERDDAP info page for dataset metadata."""
        return f"{self.erddap_base_url}/info/{self.dataset_id}/index.html"

    def construct_griddap_url(self) -> str:
        """
        Construct GridDAP URL for downloading regional grid subset.

        GridDAP syntax: dataset.nc?var[time_start:stride:time_end][lat_start:stride:lat_end][lon_start:stride:lon_end]

        Returns URL for fetching NetCDF file with spatial and temporal subset.
        """
        now = datetime.now(timezone.utc)
        end_time = now + timedelta(days=self.forecast_horizon_days)

        # Format timestamps for GridDAP (ISO 8601)
        time_start = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        time_end = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build variable queries with constraints
        # GridDAP format: var[time_start:stride:time_end][lat_start:stride:lat_end][lon_start:stride:lon_end]
        var_queries = []
        for var in self.data_variables:
            var_query = (
                f"{var}"
                f"[({time_start}):1:({time_end})]"
                f"[({self.grid.lat_min}):1:({self.grid.lat_max})]"
                f"[({self.grid.long_min}):1:({self.grid.long_max})]"
            )
            var_queries.append(var_query)

        # Join all variable queries with commas
        query_string = ",".join(var_queries)

        # Construct full URL
        url = f"{self.griddap_url}.nc?{query_string}"

        return url

    def construct_filename(self) -> str:
        """
        Construct filename for downloaded NetCDF file.

        Returns filename in format: {model}_{region}_{timestamp}.nc
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{self.model_name.value}_{self.region.value}_{timestamp}.nc"


# =======================
# TIDAL MODEL CONFIGURATIONS
# =======================


class MauiTideConfig(PacIOOSModelConfig):
    """
    Tide configuration for Maui region.

    Uses Main Hawaiian Islands (MHI) tide model which provides
    pre-computed tidal predictions (sea surface height) through December 2026.
    Data URL: https://pae-paha.pacioos.hawaii.edu/erddap/griddap/tide_mhi.html
    """

    model_config = ConfigDict(frozen=True)

    region: Region = Region.MAUI
    model_name: PacIOOSModel = PacIOOSModel.TIDE_MHI

    # tide model provides hourly predictions extending ~1 year into future
    # data is pre-computed, we only fetch for Redis TTL maintenance (weekly)

    max_forecast_age_hours: int = 168  # 7 days - weekly refresh sufficient
    forecast_horizon_days: int = 7  # Fetch 7 days of hourly predictions
    time_step_hours: int = 1  # Hourly resolution

    # tide model resolution ~1km, allow 1.5x radius for nearest neighbor
    max_nearest_neighbor_distance_km: float = 1.5

    # tide variable: ssh (sea surface height only, no currents)
    # Note: Tidal currents (u/v) are available in tide_mhi_vel dataset but not needed for surfers
    # For comprehensive currents, use ROMS model instead (includes tidal + wind + wave-driven)
    data_variables: list[str] = ["ssh"]

    # ERDDAP dataset identifier
    dataset_id: str = "tide_mhi"

    # Category-level descriptions for client tooltips and context
    data_summary: dict[str, str] = {
        "tide": "Astronomical tide predictions from harmonic analysis (does not include storm surge or wind effects)"
    }


# =======================
# REGISTRY & LOOKUP
# =======================

# registry maps (Region, Model) -> Config class
# region determines geographic variant, Model determines data type
PACIOOS_CONFIG_REGISTRY: dict[tuple[Region, PacIOOSModel], PacIOOSModelConfig] = {
    # maui region
    (Region.MAUI, PacIOOSModel.TIDE_MHI): MauiTideConfig(),
}


def get_pacioos_config(region: Region, model: PacIOOSModel) -> PacIOOSModelConfig:
    """
    Get a specific PacIOOS configuration.

    Args:
        region: Geographic region
        model: PacIOOS model type

    Returns:
        Instantiated config

    Raises:
        ValueError: If no configuration exists for this region/model combo
    """
    key = (region, model)
    if key not in PACIOOS_CONFIG_REGISTRY:
        available = ", ".join(
            f"{r.value}/{m.value}" for r, m in PACIOOS_CONFIG_REGISTRY.keys()
        )
        raise ValueError(
            f"No PacIOOS configuration for {region.value}/{model.value}. "
            f"Available configurations: {available}"
        )

    config_cls = PACIOOS_CONFIG_REGISTRY[key]
    return config_cls


def get_enabled_regions_for_model(model: PacIOOSModel) -> list[Region]:
    """
    Get all enabled regions that have configuration for a specific model.

    Args:
        model: PacIOOS model type (TIDE, SWAN, WRF)

    Returns:
        List of enabled regions that support this model
    """
    enabled_regions = get_enabled_regions()
    regions = []

    for (region, model_type), _ in PACIOOS_CONFIG_REGISTRY.items():
        if model_type == model and region in enabled_regions:
            regions.append(region)

    return regions
