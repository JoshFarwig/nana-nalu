from datetime import datetime, time, timedelta, timezone
from enum import Enum
from functools import lru_cache
from urllib.parse import quote
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from utils.location import Location, LocationMapper

# =======================
# CORE CONFIGURATIONS
# =======================


def ensure_utc(t: time) -> time:
    if t.tzinfo is None:
        raise ValueError("Time must include tzinfo=timezone.utc")
    if t.tzinfo != timezone.utc:
        raise ValueError("Time must be UTC")
    return t


class WFO(str, Enum):
    HONOLULU = "hfo"


class NWPSGridConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    cg: str = Field(
        pattern=r"^CG\d+$",
    )
    lat_max: float = Field(
        ge=-90,
        le=90,
    )
    lat_min: float = Field(
        ge=-90,
        le=90,
    )
    long_max: float = Field(
        ge=0,
        le=360,
    )
    long_min: float = Field(
        ge=0,
        le=360,
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


class NWPSModelConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    wfo: WFO

    # NOTE: model time completions are semi-variable, usually take an 1-1.5hrs
    # to complete after start time. actual start time is extremely variable per WFO.
    # each WFO has different due to model dependencies i.e. WWW3, a wfo's wind grid, etc.
    # for example, HFO model set to 00 analysis time ~ 2pm HST starts at 06:52 UTC
    # ~ 9pm HST and completes at 08:03 UTC ~ 10pm HST

    # NOTE: NWPS does include a status file as:
    # https://www.nco.ncep.noaa.gov/pmb/spa/nwps/status_file.txt
    # for each WFO. So can pull from this for the WFO code and check
    # the tags to see some more status on the model runs.

    model_analysis_times: dict[str, time]
    model_long_wait_time: timedelta
    model_short_wait_time: timedelta

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

    filename_pattern: str = "{wfo}_nwps_{cg}_{date}_{time}.grib2"
    region: str
    params: list[str]
    levels: list[str]
    grid: NWPSGridConfig

    @field_validator("model_analysis_times", mode="before")
    @classmethod
    def validate_model_analysis_times(cls, times):
        return [ensure_utc(time) for time in times]

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

    def construct_grib_filter_url(
        self,
        analysis_time: time,
    ) -> str:
        """
        Construct the full GRIB filter URL for a specific model run.

        Args:
            analysis_time: The model's initial time point for data gathering (must be in model_analysis_times)

        Returns:
            Full GRIB filter URL with dir and file parameters
        """

        if analysis_time not in self.model_analysis_times.values():
            raise ValueError(
                f"analysis_time {analysis_time} not in configured model_analysis_times_times: {self.model_analysis_times}"
            )

        forecast_date = datetime.now(timezone.utc).date()
        date_str = forecast_date.strftime("%Y%m%d")
        analysis_time_str = analysis_time.strftime("%H%M")
        analysis_time_hour = analysis_time.strftime("%H")

        # construct dir and file query params
        # format for dir: /{region}.{YYYYMMDD}/{wfo}/{HH}/{CG}/
        dir_path = f"/{self.region}.{date_str}/{self.wfo.value}/{analysis_time_hour}/{self.grid.cg}"
        filename = self.filename_pattern.format(
            wfo=self.wfo.value, cg=self.grid.cg, date=date_str, time=analysis_time_str
        )

        # build all query parameters as a list, then join
        query_parts = [
            f"dir={quote(dir_path, safe='')}",
            f"file={filename}",
            *[f"{param}=on" for param in self.params],
            *[f"{level}=on" for level in self.levels],
            "subregion=",
            f"toplat={self.grid.lat_max}",
            f"leftlon={self.grid.long_min}",
            f"rightlon={self.grid.long_max}",
            f"bottomlat={self.grid.lat_min}",
        ]

        query_params = "&".join(query_parts)
        return f"{self.grib_filter_base_url}?{query_params}"


# =======================
# HFO CONFIGURATIONS
# =======================


class NWPSMauiGridConfig(NWPSGridConfig):
    model_config = ConfigDict(frozen=True)

    cg: str = "CG4"
    lat_max: float = 21.042
    lat_min: float = 20.553
    long_max: float = 204.046
    long_min: float = 203.285


class NWPSMauiModelConfig(NWPSModelConfig):
    model_config = ConfigDict(frozen=True)

    wfo: WFO = WFO.HONOLULU

    model_analysis_times: dict[str, time] = {
        "00": time(0, 0, tzinfo=timezone.utc),
        "12": time(12, 0, tzinfo=timezone.utc),
    }

    model_long_wait_time: timedelta = timedelta(hours=6, minutes=30)
    model_short_wait_time: timedelta = timedelta(minutes=10)

    grib_filter_base_url: str = "https://nomads.ncep.noaa.gov/cgi-bin/filter_prnwps.pl"
    filename_pattern: str = "{wfo}_nwps_{cg}_{date}_{time}.grib2"
    region: str = "pr"
    params: list[str] = ["all_var"]
    levels: list[str] = ["surface"]
    grid: NWPSGridConfig = NWPSMauiGridConfig()


# =================================
# CONFIG REGISTRY / KEY VALUE STORE
# =================================

NWPS_CONFIG_REGISTRY: dict[Location, type[NWPSModelConfig]] = {
    Location.MAUI: NWPSMauiModelConfig
}


@lru_cache()
def get_nwps_config(location: Location | str | None = None) -> NWPSModelConfig:
    if isinstance(location, Location):
        normalized_location = location
    else:
        normalized_location = LocationMapper.normalize(location)

    if normalized_location not in NWPS_CONFIG_REGISTRY:
        avialable = ", ".join(loc.value for loc in NWPS_CONFIG_REGISTRY.keys())
        raise ValueError(
            f"No NWPS configuration for location: {normalized_location}. "
            f"Available: {avialable}"
        )

    config_cls = NWPS_CONFIG_REGISTRY[normalized_location]
    return config_cls()  # type: ignore[arg-type] all vars in NWPSModelConfig MUST be defined in their child classes
