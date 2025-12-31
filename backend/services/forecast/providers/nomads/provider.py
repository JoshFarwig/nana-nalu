from datetime import time, date, datetime, timezone
from pathlib import Path
import logging
import xarray as xr
import numpy as np

from core.http import SyncHTTPManager
from repositories.surf_spot_repository import SyncSurfSpotRepository
from services.forecast.providers.nomads.config import (
    NWPSConfig,
    NOMADSModel,
    NOMADS_CONFIG_REGISTRY,
)
from services.forecast.providers.nomads.mapper import map_nwps_forecast
from schemas.forecast_schema import ProviderForecast
from utils.geo_validation import longitude_to_360
from utils.geo_spatial import build_forecast_kdtree, query_nearest_forecast_points
from utils.region import Region

logger = logging.getLogger(__name__)


class NOMADSProvider:
    provider_name: str = "nomads"
    processing_mode: str = "file"
    file_path: str = "/tmp/nomads/"

    def __init__(
        self,
        config: NWPSConfig,
        http_manager: SyncHTTPManager,
        surf_spot_repo: SyncSurfSpotRepository,
    ):
        self.config = config
        self.http_manager = http_manager
        self.surf_spot_repo = surf_spot_repo

    @classmethod
    def supports_region(cls, region: Region) -> bool:
        """
        Check if NOMADS has configuration for the given region.

        Returns True if region is in NOMADS_CONFIG_REGISTRY, False otherwise.
        """
        return any(r == region for r, _ in NOMADS_CONFIG_REGISTRY.keys())

    def download_file(
        self, analysis_time: time, forecast_date: date | None = None
    ) -> Path:
        """Download the GRIB2 file from the NWPS model configuration with streaming"""

        if forecast_date is None:
            forecast_date = datetime.now(timezone.utc).date()

        url = self.config.construct_grib_filter_url(analysis_time, forecast_date)
        filename = self.config.construct_filename(analysis_time, forecast_date)

        # ensure download directory exists
        download_dir = Path(self.file_path)
        download_dir.mkdir(parents=True, exist_ok=True)

        file_path = download_dir / filename

        # NOTE: using 512KB chunks for grib files of 20-30MB
        self.http_manager.download_stream(
            url, file_path=str(file_path), chunk_size=512 * 1024
        )

        return file_path

    def extract_forecasts(self, file_path: Path) -> dict[int, ProviderForecast]:
        """
        Core NWPS provider function to extract forecasts for all spots that exist in grid.

        Returns:
            Dictionary mapping spot_id -> ProviderForecast (unified schema ready for Redis)
        """

        # PERFORMANCE: for future implementations, if extract_forecasts ABSOLUTELY needs optimization
        # consider using a threadpoolexecutor for the cfgrib IO + decompression and the KDtree
        # build + query. some numpy / xarray operations could be justified IF they are operating on
        # very very large sets of data, which is not the case as of now. nothing else screams out
        # as a potiental optimization here that releases the GIL enough to justify using threading
        # w/ python's quirks

        # extract all spots that exist in grid configured in NWPS{LOCATION}GridConfig
        spots = self.surf_spot_repo.get_all_in_grid(
            self.config.grid.lat_min,
            self.config.grid.lat_max,
            self.config.grid.long_min,
            self.config.grid.long_max,
            is_active=True,
        )

        # clean up any old index files to prevent caching issues
        for idx_file in file_path.parent.glob(f"{file_path.name}.*.idx"):
            idx_file.unlink()
            logger.debug(f"Removed old index file: {idx_file}")

        # open dataset (grib2 parsing can be slow)
        ds = xr.open_dataset(
            str(file_path), engine="cfgrib", filter_by_keys={"dataType": "fc"}
        )

        # DEBUG: log all variables found in GRIB file
        logger.info(
            "GRIB variables found in dataset",
            extra={
                "file": file_path.name,
                "data_vars": list(ds.data_vars.keys()),
                "coords": list(ds.coords.keys()),
            },
        )

        # DEBUG: log detailed variable attributes
        for var_name in ds.data_vars:
            var = ds[var_name]
            logger.info(
                f"Variable details: {var_name}",
                extra={
                    "long_name": var.attrs.get("long_name", "N/A"),
                    "units": var.attrs.get("units", "N/A"),
                    "GRIB_paramId": var.attrs.get("GRIB_paramId", "N/A"),
                    "GRIB_shortName": var.attrs.get("GRIB_shortName", "N/A"),
                },
            )

        # transform spot data into np arrays for xarray data
        spot_ids = np.array([spot["id"] for spot in spots])
        spot_lats = np.array([spot["latitude"] for spot in spots])
        spot_lons = np.array(
            [longitude_to_360(spot["longitude"], precision=4) for spot in spots]
        )

        # NOTE: curently building a KDtree every time this function execs. consider moving to some
        # kind of cache stored in provider state so it persists throughout celery worker runtime.
        # this kind of thing may need to be shared across child processes, so idk, maybe not possible

        # build kdtree that filters out land cells with no data to
        # run nearest neighbor search only on valid ocean cells
        # offload to thread pool as this can be CPU-intensive for larger grids
        tree, valid_lats, valid_lons = build_forecast_kdtree(
            ds, valid_var="swh", time_slice={"step": 0}
        )

        # retrieve the selected lats, lons, and distances from the nearest neighbor search
        # use max_distance_km to generate NaN's  for spots that do not have
        # any nearby cells in a 2km radius. choose a distance wisely.
        # Maui's NWPS data grid resolutions are
        # ~500m x 500m, so 2km distance ensures ~ 4 cell radius

        # NOTE: ideally, there will some shapefile or simple polygon off the island's shape
        # or I guess if I am building this for various NA locations, some like of script to
        # add in a shapefile for a land mass and transform it into a polygon to ensure
        # any new SurfSpot's cross reference the polygon to ensure it is not within the
        # polygon. for now though, keeping this defensive query.
        #
        selected_lats, selected_lons, distances = query_nearest_forecast_points(
            tree,
            valid_lats,
            valid_lons,
            spot_lats,
            spot_lons,
            max_distance_km=self.config.max_nearest_neighbor_distance_km,
        )

        # filter out spots that are out of bounds (have NaN coordinates)
        valid_mask = ~np.isnan(selected_lats)

        # log warnings for filtered spots
        if not valid_mask.all():
            filtered_indices = np.where(~valid_mask)[0]
            for idx in filtered_indices:
                logger.warning(
                    f"Spot with id: {spot_ids[idx]} filtered - out of bounds.",
                    f"Spot exceeds max distance threshold of {self.config.max_nearest_neighbor_distance_km}km",
                    extra={
                        "id": spot_ids[idx],
                        "lat": spot_lats[idx],
                        "lon": spot_lons[idx],
                        "distance_km": float(np.round(distances[idx], 2)),
                    },
                )

        # retrieve spots that found nearest neighbors range
        valid_spot_ids = spot_ids[valid_mask]
        valid_spot_lats = spot_lats[valid_mask]
        valid_spot_lons = spot_lons[valid_mask]
        valid_selected_lats = selected_lats[valid_mask]
        valid_selected_lons = selected_lons[valid_mask]
        valid_distances = distances[valid_mask]

        # build new dataset for grib2 forecasts for each valid surf spot
        spot_forecast = self._build_spot_forecast_dataset(
            ds,
            valid_selected_lats,
            valid_selected_lons,
            valid_spot_ids,
            valid_spot_lats,
            valid_spot_lons,
            valid_distances,
        )

        # build raw forecast dictionary
        raw_forecasts = self._build_forecast_dict(
            spot_forecast,
            valid_spot_ids,
            valid_selected_lats,
            valid_selected_lons,
            valid_distances,
        )

        # close datasets
        ds.close()
        spot_forecast.close()

        # map to unified schema (region comes from config)
        region = self.config.region.value
        provider_forecasts = {
            spot_id: map_nwps_forecast(spot_id, region, raw_data)
            for spot_id, raw_data in raw_forecasts.items()
        }

        return provider_forecasts

    def _build_spot_forecast_dataset(
        self,
        ds: xr.Dataset,
        selected_lats: np.ndarray,
        selected_lons: np.ndarray,
        spot_ids: np.ndarray,
        spot_lats: np.ndarray,
        spot_lons: np.ndarray,
        distances: np.ndarray,
    ) -> xr.Dataset:
        """
        Build spot-specific forecast dataset from grid data
        """
        return (
            ds.sel(
                latitude=xr.DataArray(selected_lats, dims="spot"),
                longitude=xr.DataArray(selected_lons, dims="spot"),
            )
            .assign_coords(
                spot_id=("spot", spot_ids),
                spot_lat=("spot", spot_lats),
                spot_lon=("spot", spot_lons),
                distance_km=("spot", distances),
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

    def _build_forecast_dict(
        self,
        spot_forecast: xr.Dataset,
        spot_ids: np.ndarray,
        selected_lats: np.ndarray,
        selected_lons: np.ndarray,
        distances: np.ndarray,
    ) -> dict:
        """
        Build forecast dictionary from xarray Dataset.
        """
        from pandas import Timestamp

        forecasts = {}

        # extract common data once (shared across all spots)
        # convert numpy.datetime64 → pandas.Timestamp (subclass of datetime, Pydantic-compatible)
        # NOTE: GRIB2 forecast files have mandatory time coordinates; if missing, dataset open would fail
        analysis_time = Timestamp(spot_forecast.analysis_time.values)
        valid_times = [Timestamp(vt) for vt in spot_forecast.valid_time.values]

        # get all data variable names (exclude coordinates)
        data_vars = [
            var for var in spot_forecast.data_vars if var not in ["analysis_time"]
        ]

        # vectorized extraction: convert all data to numpy arrays first
        # this is much faster than doing .isel() in a loop
        # transpose to get shape (num_spots, num_timesteps) instead of (num_timesteps, num_spots)
        data_arrays = {var: spot_forecast[var].values.T for var in data_vars}

        # build dictionary for each spot
        for i, spot_id in enumerate(spot_ids):
            forecasts[int(spot_id)] = {
                "spot_id": int(spot_id),
                "grid_metadata": {
                    "selected_lat": float(selected_lats[i]),
                    "selected_lon": float(selected_lons[i]),
                    "distance_km": float(distances[i]),
                },
                "analysis_time": analysis_time,
                "valid_times": valid_times,
                "data": {var: data_arrays[var][i].tolist() for var in data_vars},
            }

        return forecasts
