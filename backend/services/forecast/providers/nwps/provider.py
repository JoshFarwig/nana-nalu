import asyncio
from datetime import time
from pathlib import Path
import logging
import xarray as xr
import numpy as np

from core.http import AsyncHTTPManager
from repositories.surf_spot_repository import SurfSpotRepository
from services.forecast.providers.nwps.config import NWPSModelConfig
from utils.geo import (
    longitude_to_360,
    build_forecast_kdtree,
    query_nearest_forecast_points,
)

logger = logging.getLogger(__name__)


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

    async def extract_forecasts(self, file_path: Path) -> dict:
        """Core NWPS provider function to extract forecasts for all spots that exist in grid"""

        # extract all spots that exist in grid configured in NWPS{LOCATION}GridConfig
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

        # transform spot data into np arrays for xarray data
        spot_ids = np.array([spot["id"] for spot in spots])
        spot_lats = np.array([spot["latitude"] for spot in spots])
        spot_lons = np.array(
            [longitude_to_360(spot["longitude"], precision=4) for spot in spots]
        )

        # NOTE: curently building a KDtree every time this function exes. consider moving to some
        # kind of cache stored in provider state so that it lives throughout the lifespan of the celery worker,
        # but as of now, fine as is.

        # build kdtree that filters out land cells with no data to
        # run nearest neighbor search only on valid ocean cells
        # offload to thread pool as this can be CPU-intensive for larger grids
        tree, valid_lats, valid_lons = await asyncio.to_thread(
            build_forecast_kdtree, ds, valid_var="swh", time_slice={"step": 0}
        )

        # retrieve the selected lats, lons, and distances from the nearest neighbor search
        # use max_distance_km to generate NaN's  for spots that do not have
        # any nearby cells in a 2km radius. select a radius wisely, with
        # Maui's NWPS data, grid resolutions are
        # 500m x 500m, so 2km range ensures ~ 4 cell distance
        max_distance_threshold = 2

        selected_lats, selected_lons, distances = query_nearest_forecast_points(
            tree,
            valid_lats,
            valid_lons,
            spot_lats,
            spot_lons,
            max_distance_km=max_distance_threshold,
        )

        # filter out spots that are out of bounds (have NaN coordinates)
        valid_mask = ~np.isnan(selected_lats)

        # log warnings for filtered spots
        if not valid_mask.all():
            filtered_indices = np.where(~valid_mask)[0]
            for idx in filtered_indices:
                logger.warning(
                    f"Spot with id: {spot_ids[idx]} filtered - out of bounds.",
                    f"Spot exceeds max distance threshold of {max_distance_threshold}km",
                    extra={
                        "id": spot_ids[idx],
                        "lat": spot_lats[idx],
                        "lon": spot_lons[idx],
                        "distance_km": float(np.round(distances[idx], 2)),
                    },
                )

        # retrieve spots that found nearest neighbors in max_distance_threshold range
        valid_spot_ids = spot_ids[valid_mask]
        valid_spot_lats = spot_lats[valid_mask]
        valid_spot_lons = spot_lons[valid_mask]
        valid_selected_lats = selected_lats[valid_mask]
        valid_selected_lons = selected_lons[valid_mask]
        valid_distances = distances[valid_mask]

        # build new dataset for grib2 forecasts for each valid surf spot
        spot_forecast = (
            ds.sel(
                latitude=xr.DataArray(valid_selected_lats, dims="spot"),
                longitude=xr.DataArray(valid_selected_lons, dims="spot"),
            )
            .assign_coords(
                spot_id=("spot", valid_spot_ids),
                spot_lat=("spot", valid_spot_lats),
                spot_lon=("spot", valid_spot_lons),
                distance_km=("spot", valid_distances),
            )
            .rename(
                {
                    "latitude": "selected_lat",
                    "longitude": "selected_lon",
                    "time": "analysis_time",
                }
            )
            .swap_dims({"step": "valid_time"})
        )

        # build forecast dictionary - offload to thread for CPU-bound operations
        forecasts = await asyncio.to_thread(
            self._build_forecast_dict,
            spot_forecast,
            valid_spot_ids,
            valid_spot_lats,
            valid_spot_lons,
            valid_selected_lats,
            valid_selected_lons,
            valid_distances,
        )

        # close datasets
        ds.close()
        spot_forecast.close()

        return forecasts

    def _build_forecast_dict(
        self,
        spot_forecast: xr.Dataset,
        spot_ids: np.ndarray,
        spot_lats: np.ndarray,
        spot_lons: np.ndarray,
        selected_lats: np.ndarray,
        selected_lons: np.ndarray,
        distances: np.ndarray,
    ) -> dict:
        """
        Build forecast dictionary from xarray Dataset.

        This is a CPU-bound operation run in a thread pool to avoid blocking
        the event loop. Vectorizes data extraction where possible.
        """
        forecasts = {}

        # extract common data once (shared across all spots)
        analysis_time = spot_forecast.analysis_time.values.tolist()
        valid_times = spot_forecast.valid_time.values.tolist()

        # get all data variable names (exclude coordinates)
        data_vars = [
            var for var in spot_forecast.data_vars if var not in ["analysis_time"]
        ]

        # vectorized extraction: convert all data to numpy arrays first
        # this is much faster than doing .isel() in a loop
        data_arrays = {var: spot_forecast[var].values for var in data_vars}

        # build dictionary for each spot
        for i, spot_id in enumerate(spot_ids):
            forecasts[str(spot_id)] = {
                "spot_id": int(spot_id),
                "spot_latitude": float(spot_lats[i]),
                "spot_longitude": float(spot_lons[i]),
                "selected_latitude": float(selected_lats[i]),
                "selected_longitude": float(selected_lons[i]),
                "distance_km": float(distances[i]),
                "analysis_time": analysis_time,
                "valid_times": valid_times,
                "data": {var: data_arrays[var][i].tolist() for var in data_vars},
            }

        return forecasts
