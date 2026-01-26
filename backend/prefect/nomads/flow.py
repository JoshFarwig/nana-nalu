from prefect import flow
from prefect.logging import get_run_logger

from utils.region import Region


@flow(name="nomads-nwps-regional", retries=3)
async def fetch_nwps_region(region: Region):
    logger = get_run_logger()

    pass


@flow(name="nomads-nwps-dispatcher")
async def fetch_all_nwps():
    logger = get_run_logger()
    pass
