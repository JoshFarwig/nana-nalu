from enum import Enum

from domain.provider import ForecastProvider


class NOMADSModel(str, Enum):
    NWPS = "nwps"
    GFS_WAVE = "gfs_wave"


class PacIOOSModel(str, Enum):
    TIDE_MHI = "tide_mhi"
    SWAN = "swan"
    WRF = "wrf"
    ROMS = "roms"


# Provider → valid model enum members. Single source of truth.
PROVIDER_MODELS: dict[ForecastProvider, set[str]] = {
    ForecastProvider.NOMADS: {m.value for m in NOMADSModel},
    ForecastProvider.PACIOOS: {m.value for m in PacIOOSModel},
}
