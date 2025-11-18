import asyncio
from datetime import time
from pathlib import Path
import xarray as xr
import numpy as np

from core.http import AsyncHTTPManager
from models.surf_spot_model import SurfSpot
from repositories.surf_spot_repository import SurfSpotRepository
from services.forecast.providers.nwps.config import NWPSModelConfig
from utils.geo import longitude_to_360


class NWPSProvider:
    provider_name: str = "NWPS"
    processing_mode: str = "file"
    file_path: str = "/tmp/nwps/"

    def __init__(
        self,
        config: NWPSModelConfig,
        http_manager: AsyncHTTPManager,
        surf_spot_repo: SurfSpotRepository,
    ):
        self.config = config
        self.http_manager = http_manager
        self.surf_spot_repo = surf_spot_repo

    async def download_file(self, analysis_time: time) -> Path:
        """Download the GRIB2 file from the NWPS model configuration with streaming"""

        url = self.config.construct_grib_filter_url(analysis_time)
        filename = self.config.construct_filename(analysis_time)
        file_path = Path(self.file_path) / filename

        # NOTE: using 512KB chunks for grib files of 20-30MB
        await self.http_manager.download_stream(
            url, file_path=str(file_path), chunk_size=512 * 1024
        )

        return file_path

    async def extract_forecasts(self, analysis_time: time, file_path: Path) -> dict:
        """Core NWPS provider function to extract forecasts for all spots that exist in grid"""
        spots = await self.surf_spot_repo.get_all_in_grid(
            self.config.grid.lat_min,
            self.config.grid.lat_max,
            self.config.grid.long_min,
            self.config.grid.long_max,
            is_active=True,
        )

        # open dataset in thread pool to avoid blocking event loop (grib2 parsing can be slow)
        ds = await asyncio.to_thread(
            xr.open_dataset,
            str(file_path),
            engine="cfgrib",
            filter_by_keys={"dataType": "fc"},
        )

        # extract spot coordinates and prepare for xarray selection
        spot_ids = np.array([spot["id"] for spot in spots])
        spot_lats = np.array([spot["latitude"] for spot in spots])
        spot_lons = np.array([longitude_to_360(spot["longitude"]) for spot in spots])

        # NOTE: Euclidean vs Haversine for nearest neighbor
        # after going back and forth between using custom haversine nearest neighbor
        # logic vs using xarray's built-in .sel(method='nearest'), decided on the later.
        # The concern stems from xarray using Euclidean distance, which does not take
        # into consideration distance contortions that are created from the curvature of coords.
        # for regional NWPS grids, Euclidean distance has ~0.11% error vs true haversine
        # (great-circle) distance. typical grid resolutions for NWPS seems to be 500m-2km
        # and surf spot precision falls within ±11m (4 decimal places), this translates to
        # ~<6m error even at higher latitudes. model forecasting uncertainity probably outweighs
        # importance of EXACT nearest neighbor selection anyways. if this was all current / analysis data,
        # it could be a different story. but its not so: easier development over complexity demon

        # NOTE: FUCK, disregaurd everything above. nearest neighbor xarray datasets don't consider NaN
        # values and land-mass filter for GRIB2 files from NWPS are NaN values for all data vars.
        # therefore, need to create a custom nearest neighbor function anyways to handle creating
        # an ocean mask and selecting only valid lat / long values in the ocean mask. at this point,
        # it would be a 4-5 line change to use haversine so will be reimplementing haversine with some
        # custom logic. Need scipy unforunately, so extra dep size sucks but it is what is is. may
        # need scipy for somthing else in the future for this project.

        # CUSTOM FUNCTION TO RETURN DATASET WITH SPOT DIM
        # WITH SELECTED LAT / LONG VALUES IN OCEAN MASK

        # tree, ocean_lats, ocean_lons = build_ocean_kdtree(ds: xr.Dataset, var: str = "swh"
        # selected_lats, selected_lons, distances = query_nearest_ocean_point(tree, ocean_lats, ocean_lons, target_lats, target_lons, radius)
