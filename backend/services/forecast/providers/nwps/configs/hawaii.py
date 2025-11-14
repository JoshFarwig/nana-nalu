from datetime import time, timedelta, timezone

from pydantic import HttpUrl
from .config import NWPSModelConfig, NWPSGridConfig, WFOCode

# NOTE: very important consideration, model time completions are variable
# i.e. 1-2hrs after start time. AND start time is typically 6-8 hours AFTER
# run internal i.e. for 00 -> starts at 06:52.
# NWPS does include a status file as:
# https://www.nco.ncep.noaa.gov/pmb/spa/nwps/status_file.txt
# for each WFO. So can pull from this for the WFO code and check
# the done tag after wait time, if its still not done, have
# a more aggresive poll time? OR, just request for the file
# directly and if it returns 404, run the short aggresive delay


class NWPSMauiGrid(NWPSGridConfig):
    cg: str = "CG4"
    lat_max: float = 0.0
    lat_min: float = 0.0
    long_max: float = 0.0
    long_min: float = 0.0


class NWPSMauiModel(NWPSModelConfig):
    site_code: WFOCode = WFOCode.HONOLULU

    # NOTE: after observing run times from the model for Maui,
    # looks like 00Z and 12Z are the most common run times,
    # but I saw a 00Z and 06Z runtime? yet, the 06 runtime completed at 18:32.
    # strange. this was on 11/10/25.
    # regardless, it seems like the 00 run completes around 06:20-07:15 +/-
    # and the 12Z run completes in range 18:20-19:15 +/-
    # today for all of HFO, completed start time for model run was 1739, end time 1849
    # for 12Z
    # for now, doing single forecast fetch at 00Z
    # since this seems to be the most consistent
    # and always provided grib data.

    model_run_times: list[time] = [
        time(0, 0, tzinfo=timezone.utc),
    ]

    model_long_wait_time: timedelta = timedelta(hours=6, minutes=30)
    model_short_wait_time: timedelta = timedelta(minutes=10)
    grib_filter_base_url: HttpUrl = (
        "https://nomads.ncep.noaa.gov/gribfilter.php?ds=prnwps"
    )
    grid = NWPSMauiGrid()
