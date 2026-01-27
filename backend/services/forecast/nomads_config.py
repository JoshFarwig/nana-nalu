import logging
from datetime import date, time
from enum import Enum
from urllib.parse import quote
from pydantic import BaseModel, ConfigDict, Field, field_validator

from utils.region import Region, RegionGrid, get_enabled_regions
from utils.geo_validation import longitude_to_360

logger = logging.getLogger(__name__)

# =======================
# CORE CONFIGURATIONS
# =======================


class NOMADSModel(str, Enum):
    """
    Available NOMADS ocean models.

    Generic model types - location determines regional variant.
    """

    NWPS = "nwps"
    # TODO: add GFS Global model?
    # may not be needed with pacioos provided models


class WFO(str, Enum):
    HONOLULU = "hfo"


class NWPSConfig(BaseModel):
    """Base configuration for NWPS model from NOMADS provider."""

    model_config = ConfigDict(frozen=True)

    region: Region  # Geographic region (MAUI, OAHU, etc.)
    model_name: NOMADSModel
    provider_name: str = "nomads"
    wfo: WFO

    # NWPS computational grid identifier (CG0-CG5)
    cg: str = Field(pattern=r"^CG\d+$")

    # Human-readable descriptions of data categories for client context
    data_summary: dict[str, str] = Field(
        default={},
        description="Category-level descriptions of what each data type represents",
    )

    # NOTE: NWPS model run times are highly variable and unpredictable
    # model completions usually take 1-1.5hrs after start time,
    # start times vary by WFO due to model dependencies (WW3, wind grids, etc.).
    # example: HFO's "00z" run may start at 06:52 UTC and complete at 08:03 UTC.
    # this is why we use polling + availability checking instead of fixed schedules.

    # NOTE: NWPS provides a status file for monitoring:
    # https://www.nco.ncep.noaa.gov/pmb/spa/nwps/status_file.txt
    # can be used for additional run status verification if needed

    # maximum age of forecast data to accept before considering it stale
    # used by polling system to skip fetching old runs

    max_forecast_age_hours: int = 6
    grib_filter_base_url: str

    # NOTE: filename pattern template for grib2 files
    # seem to primarily follow the default format set here,
    # however for CG0's, it is set to include a _Trkng_
    # field as shown in the examples. not too sure why or
    # what the difference is in this CG0, but I will look into
    # it later on. make sure to double check the filename pattern
    # for the grib2 files for a specific WFO, and override if nessicary.
    # CG# example: "{wfo}_nwps_{cg}_{date}_{time}.grib2"
    # CG0 example: "{wfo}_nwps_CG0_Trkng_{date}_{time}.grib2"

    # NOTE: for general interest and future reference, the grib filter UI
    # is accessible for the NWPS: pacifc region at:
    # https://nomads.ncep.noaa.gov/gribfilter.php?ds=prnwps
    # change ds={region}nwps for your specific region

    # NOTE: IMPORTANT!!! nearest neighbor search for ocean
    # lat/lons using a cKDTree requires a max distance. this field
    # will essentially make sure that IF any SurfSpots are placed
    # very inland, they won't select the nearest ocean cell outside
    # of the max distance set. Refer to the NWPS resolution of your
    # region / grib2 file to calculate the max distance.

    # EXAMPLE:
    # maui's NWPS resolution ~500m x 500m. want around ~4 cells
    # radius so set the max distance to 2.0
    # this may change in the future with some like of rough polygon
    # check to ensure spots are not created inland, but its good
    # defensive programming as of now.

    max_nearest_neighbor_distance_km: float = 4.5

    filename_pattern: str = "{wfo}_nwps_{cg}_{date}_{time}.grib2"
    nomads_region: str  # NOMADS region code (e.g., "pr" for Pacific)
    params: list[str]
    levels: list[str]

    @property
    def grid(self) -> RegionGrid:
        """Get grid bounds from the region."""
        return self.region.grid

    @field_validator("params")
    @classmethod
    def validate_params(cls, params: list[str]) -> list[str]:
        if "all_var" in params and len(params) > 1:
            raise ValueError("params cannot contain 'all_var' with other parameters")
        return params

    @field_validator("levels")
    @classmethod
    def validate_levels(cls, levels: list[str]) -> list[str]:
        if "all_lev" in levels and len(levels) > 1:
            raise ValueError("levels cannot contain 'all_lev' with other levels")
        return levels

    def _prepare_filename_components(
        self, analysis_time: time, forecast_date: date
    ) -> tuple[str, str, str, str]:
        """
        Prepare common components needed for filename and URL construction.

        Returns:
            tuple of (date_str, analysis_time_str, analysis_time_hour, filename)
        """

        date_str = forecast_date.strftime("%Y%m%d")
        analysis_time_str = analysis_time.strftime("%H%M")
        analysis_time_hour = analysis_time.strftime("%H")

        filename = self.filename_pattern.format(
            wfo=self.wfo.value, cg=self.cg, date=date_str, time=analysis_time_str
        )

        return date_str, analysis_time_str, analysis_time_hour, filename

    def construct_filename(self, analysis_time: time, forecast_date: date) -> str:
        _, _, _, filename = self._prepare_filename_components(
            analysis_time, forecast_date
        )
        return filename

    def construct_grib_filter_url(
        self, analysis_time: time, forecast_date: date
    ) -> str:
        date_str, _, analysis_time_hour, filename = self._prepare_filename_components(
            analysis_time, forecast_date
        )

        # construct dir path
        dir_path = f"/{self.nomads_region}.{date_str}/{self.wfo.value}/{analysis_time_hour}/{self.cg}"

        # build all query parameters
        query_parts = [
            f"dir={quote(dir_path, safe='')}",
            f"file={filename}",
            *[f"{param}=on" for param in self.params],
            *[f"{level}=on" for level in self.levels],
            "subregion=",
            f"toplat={self.grid.lat_max}",
            f"leftlon={longitude_to_360(self.grid.long_min, precision=3)}",
            f"rightlon={longitude_to_360(self.grid.long_max, precision=3)}",
            f"bottomlat={self.grid.lat_min}",
        ]

        query_params = "&".join(query_parts)
        return f"{self.grib_filter_base_url}?{query_params}"


# =======================
# HFO CONFIGURATIONS
# =======================


class MauiNWPSConfig(NWPSConfig):
    model_config = ConfigDict(frozen=True)

    region: Region = Region.MAUI
    model_name: NOMADSModel = NOMADSModel.NWPS
    wfo: WFO = WFO.HONOLULU
    cg: str = "CG4"

    # NOTE: HFO runs twice daily but at highly unpredictable times
    # observed patterns: early run finishes ~7-9:30 UTC, late run finishes ~17-20 UTC
    # polling system checks 3x daily to catch both runs regardless of timing

    # maximum age of forecast data to accept
    # HFO runs twice daily (~12h gaps), so 18h allows for one missed run + buffer

    max_forecast_age_hours: int = 18

    max_nearest_neighbor_distance_km: float = 2.0
    grib_filter_base_url: str = "https://nomads.ncep.noaa.gov/cgi-bin/filter_prnwps.pl"
    filename_pattern: str = "{wfo}_nwps_{cg}_{date}_{time}.grib2"
    nomads_region: str = "pr"

    # Category-level descriptions for client tooltips and context
    data_summary: dict[str, str] = {
        "tide": "Total water level including astronomical tide, storm surge, and wind setup",
        "wave": "Nearshore wave predictions including wind waves and swell components",
        "wind": "Surface-level wind forecasts from atmospheric model",
    }

    # refer to https://nomads.ncep.noaa.gov/gribfilter.php?ds=prnwps for the valid params / levels
    # removed current speed and dir since RTOFS-Global is turned off on the model runs (and its like a 9km
    # resolution, so wouldn't really provide any valiable data for computational grids of 500m).
    # refer to: (replace the HFO.date.txt to the current date or forecast run)
    # example: https://www.nco.ncep.noaa.gov/pmb/spa/nwps/warnings/Warn_Forecaster_HFO.20251126.txt

    params: list[str] = [
        "var_DIRPW",
        "var_DSLM",
        "var_HTSGW",
        "var_PERPW",
        "var_SWDIR",
        "var_SWELL",
        "var_SWPER",
        "var_WDIR",
        "var_WIND",
    ]
    levels: list[str] = ["lev_surface"]


# =================================
# CONFIG REGISTRY / KEY VALUE STORE
# =================================

# registry maps (Region, Model) -> Config class
# region determines geographic variant, Model determines NOMADS model type
NOMADS_CONFIG_REGISTRY: dict[tuple[Region, NOMADSModel], NWPSConfig] = {
    # maui region
    (Region.MAUI, NOMADSModel.NWPS): MauiNWPSConfig(),
}


def get_nomads_config(region: Region, model: NOMADSModel) -> NWPSConfig:
    """
    Get a specific NOMADS configuration.

    Args:
        region: Geographic region
        model: NOMADS model type

    Returns:
        Instantiated config

    Raises:
        ValueError: If no configuration exists for this region/model combo
    """
    key = (region, model)
    if key not in NOMADS_CONFIG_REGISTRY:
        available = ", ".join(
            f"{r.value}/{m.value}" for r, m in NOMADS_CONFIG_REGISTRY.keys()
        )
        raise ValueError(
            f"No NOMADS configuration for {region.value}/{model.value}. "
            f"Available configurations: {available}"
        )

    config_cls = NOMADS_CONFIG_REGISTRY[key]
    return config_cls


def get_enabled_regions_for_model(model: NOMADSModel) -> list[Region]:
    """
    Get all enabled regions that have configuration for a specific model.

    Args:
        model: NOMADS model type (NWPS, etc.)

    Returns:
        List of enabled regions that support this model
    """
    enabled_regions = get_enabled_regions()
    regions = []

    for (region, model_type), _ in NOMADS_CONFIG_REGISTRY.items():
        if model_type == model and region in enabled_regions:
            regions.append(region)

    return regions
