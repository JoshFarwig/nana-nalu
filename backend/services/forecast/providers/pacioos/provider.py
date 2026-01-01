from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Callable

import numpy as np
import xarray as xr

from core.http import SyncHTTPManager
from repositories.surf_spot_repository import SyncSurfSpotRepository
from schemas.forecast_schema import ProviderForecast
from services.forecast.providers.pacioos.config import (
    PacIOOSModel,
    PacIOOSModelConfig,
    PACIOOS_CONFIG_REGISTRY,
)
from services.forecast.providers.pacioos.mapper import (
    map_pacioos_tide_forecast,
    map_pacioos_swan_forecast,
    map_pacioos_wrf_forecast,
)
from utils.geo_spatial import build_forecast_kdtree, query_nearest_forecast_points
from utils.region import Region

logger = logging.getLogger(__name__)

# Model-specific mapper registry
PACIOOS_MAPPER_REGISTRY: dict[PacIOOSModel, Callable] = {
    PacIOOSModel.TIDE: map_pacioos_tide_forecast,
    PacIOOSModel.SWAN: map_pacioos_swan_forecast,
    PacIOOSModel.WRF: map_pacioos_wrf_forecast,
}


class PacIOOSProvider:
    """
    PacIOOS forecast provider using ERDDAP GridDAP.
    Downloads regional NetCDF subsets via ERDDAP's GridDAP service for fast data access.
    """

    provider_name: str = "PacIOOS"
    processing_mode: str = "file"
    file_path: str = "/tmp/pacioos/"

    def __init__(
        self,
        config: PacIOOSModelConfig,
        http_manager: SyncHTTPManager,
        surf_spot_repo: SyncSurfSpotRepository,
    ):
        self.config = config
        self.http_manager = http_manager
        self.surf_spot_repo = surf_spot_repo

    @classmethod
    def supports_region(cls, region: Region) -> bool:
        """
        Check if PacIOOS has configuration for the given region.

        Returns True if region is in PACIOOS_CONFIG_REGISTRY, False otherwise.
        """
        return any(r == region for r, _ in PACIOOS_CONFIG_REGISTRY.keys())

    def download_file(self) -> Path:
        """
        Download NetCDF file from PacIOOS ERDDAP GridDAP service.

        Uses ERDDAP GridDAP to download only the required
        spatial and temporal subset for efficient data transfer.

        Returns:
            Path to downloaded NetCDF file
        """
        url = self.config.construct_griddap_url()
        filename = self.config.construct_filename()

        # ensure download directory exists
        download_dir = Path(self.file_path)
        download_dir.mkdir(parents=True, exist_ok=True)

        file_path = download_dir / filename

        logger.info(
            "Downloading NetCDF subset via GridDAP",
            extra={
                "url": url,
                "file": filename,
                "variables": self.config.data_variables,
                "grid": {
                    "lat_min": self.config.grid.lat_min,
                    "lat_max": self.config.grid.lat_max,
                    "lon_min": self.config.grid.long_min,
                    "lon_max": self.config.grid.long_max,
                },
            },
        )

        # Download with streaming (GridDAP files are typically small, 1-10MB)
        self.http_manager.download_stream(
            url, file_path=str(file_path), chunk_size=512 * 1024
        )

        logger.info(
            "NetCDF file downloaded successfully",
            extra={
                "file": filename,
                "size_mb": round(file_path.stat().st_size / (1024 * 1024), 2),
            },
        )

        return file_path

    def extract_forecasts(self, file_path: Path) -> dict[int, ProviderForecast]:
        """
        Extract forecasts for all spots from downloaded NetCDF file.

        Args:
            file_path: Path to downloaded NetCDF file

        Returns:
            Dictionary mapping spot_id -> ProviderForecast (unified schema ready for Redis)
        """
        # get surf spots in configured grid region
        spots = self.surf_spot_repo.get_all_in_grid(
            self.config.grid.lat_min,
            self.config.grid.lat_max,
            self.config.grid.long_min,
            self.config.grid.long_max,
            is_active=True,
        )

        if not spots:
            logger.warning(
                "No active surf spots found in grid",
                extra={
                    "grid": {
                        "lat_min": self.config.grid.lat_min,
                        "lat_max": self.config.grid.lat_max,
                        "lon_min": self.config.grid.long_min,
                        "lon_max": self.config.grid.long_max,
                    }
                },
            )
            return {}

        # open downloaded NetCDF file
        logger.info(
            "Opening NetCDF file",
            extra={
                "file": file_path.name,
            },
        )

        ds = xr.open_dataset(str(file_path))

        logger.info(
            "NetCDF dataset loaded",
            extra={
                "dataset_dims": dict(
                    ds.sizes
                ),  # Use .sizes instead of .dims to avoid FutureWarning
                "dataset_vars": list(ds.data_vars.keys()),
            },
        )

        # build KDTree from first timestep to identify valid ocean cells
        tree, valid_lats, valid_lons = build_forecast_kdtree(
            ds, valid_var=self.config.data_variables[0], time_slice={"time": 0}
        )

        # prepare surf spot coordinates
        spot_ids = np.array([spot["id"] for spot in spots])
        spot_lats = np.array([spot["latitude"] for spot in spots])
        spot_lons = np.array([spot["longitude"] for spot in spots])

        # query nearest neighbors
        selected_lats, selected_lons, distances = query_nearest_forecast_points(
            tree,
            valid_lats,
            valid_lons,
            spot_lats,
            spot_lons,
            max_distance_km=self.config.max_nearest_neighbor_distance_km,
        )

        # filter out spots that are out of bounds
        valid_mask = ~np.isnan(selected_lats)

        # log warnings for filtered spots
        if not valid_mask.all():
            filtered_indices = np.where(~valid_mask)[0]
            for idx in filtered_indices:
                logger.warning(
                    "Spot filtered - exceeds max distance",
                    extra={
                        "spot_id": int(spot_ids[idx]),
                        "lat": float(spot_lats[idx]),
                        "lon": float(spot_lons[idx]),
                        "distance_km": float(np.round(distances[idx], 2)),
                        "max_distance_km": self.config.max_nearest_neighbor_distance_km,
                    },
                )

        # get valid spots only
        valid_spot_ids = spot_ids[valid_mask]
        valid_spot_lats = spot_lats[valid_mask]
        valid_spot_lons = spot_lons[valid_mask]
        valid_selected_lats = selected_lats[valid_mask]
        valid_selected_lons = selected_lons[valid_mask]
        valid_distances = distances[valid_mask]

        # build spot-specific forecast dataset
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

        # close dataset
        ds.close()

        # get the appropriate mapper for this model type
        mapper = PACIOOS_MAPPER_REGISTRY.get(self.config.model_name)
        if not mapper:
            raise ValueError(
                f"No mapper registered for PacIOOS model: {self.config.model_name}"
            )

        # map to unified schema (region comes from config)
        region = self.config.region.value
        provider_forecasts = {
            spot_id: mapper(spot_id, region, raw_data, self.config.data_summary)
            for spot_id, raw_data in raw_forecasts.items()
        }

        logger.info(
            "Forecast extraction complete",
            extra={
                "num_forecasts": len(provider_forecasts),
                "spot_ids": list(provider_forecasts.keys()),
            },
        )

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
        Build spot-specific forecast dataset from grid data.
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
                }
            )
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

        # extract time coordinates
        valid_times = [Timestamp(vt) for vt in spot_forecast.time.values]

        # get all data variable names (exclude coordinate variables)
        data_vars = [var for var in spot_forecast.data_vars if var not in ["time"]]

        # vectorized extraction
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
                "valid_times": valid_times,
                "data": {var: data_arrays[var][i].tolist() for var in data_vars},
            }

        return forecasts
