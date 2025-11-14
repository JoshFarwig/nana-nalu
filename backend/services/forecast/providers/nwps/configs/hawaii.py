from datetime import time, timedelta, timezone

from .config import NWPSModelConfig, NWPSGridConfig, WFO

# NOTE: very important consideration, model time completions are variable
# i.e. 1-2hrs after start time. AND start time is typically 6-8 hours AFTER
# run internal i.e. for 00 -> starts at 06:52.
# NWPS does include a status file as:
# https://www.nco.ncep.noaa.gov/pmb/spa/nwps/status_file.txt
# for each WFO. So can pull from this for the WFO code and check
# the done tag after wait time, if its still not done, have
# a more aggresive poll time? OR, just request for the file
# directly and if it returns 404, run the short aggresive delay


# NOTE: example grib filter url with this boundingbox config:
# https://nomads.ncep.noaa.gov/cgi-bin/filter_prnwps.pl?dir=%2Fpr.20251114%2Fhfo%2F12%2FCG4&file=hfo_nwps_CG4_20251114_1200.grib2&all_var=on&all_lev=on&subregion=&toplat=21.043&leftlon=203.285&rightlon=204.046&bottomlat=20.553
class NWPSMauiGrid(NWPSGridConfig):
    cg: str = "CG4"
    lat_max: float = 21.042
    lat_min: float = 20.553
    long_max: float = 204.046
    long_min: float = 203.285


class NWPSMauiModel(NWPSModelConfig):
    wfo: WFO = WFO.HONOLULU

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
    grib_filter_base_url: str = "https://nomads.ncep.noaa.gov/cgi-bin/filter_prnwps.pl?"
    grid: NWPSGridConfig = NWPSMauiGrid()


# TODO: add an oahu configuration maybe?
