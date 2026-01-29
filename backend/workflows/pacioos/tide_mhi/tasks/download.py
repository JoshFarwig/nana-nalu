"""
NetCDF file download task for PacIOOS ERDDAP GridDAP.

Downloads regional NetCDF subsets via ERDDAP's GridDAP service.
PacIOOS tide files are typically small (1-5MB) compared to GRIB2 files.
"""

from pathlib import Path

from prefect import task, get_run_logger

from workflows.resources import get_resources
from services.forecast.pacioos_config import PacIOOSModelConfig


DOWNLOAD_DIR = Path("/backend/.tmp/pacioos/")


@task(name="tide-mhi-download-netcdf", retries=3, retry_delay_seconds=60)
async def download_netcdf(
    config: PacIOOSModelConfig,
) -> Path:
    """
    Download NetCDF file from PacIOOS ERDDAP GridDAP service.

    Uses ERDDAP GridDAP to download only the required spatial and temporal
    subset for efficient data transfer. GridDAP files are typically small
    (1-5MB) due to the constrained grid region.

    Args:
        config: PacIOOS model configuration

    Returns:
        Path to downloaded NetCDF file
    """
    logger = get_run_logger()
    resources = await get_resources()

    url = config.construct_griddap_url()
    filename = config.construct_filename()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DOWNLOAD_DIR / filename

    logger.info(
        "Downloading NetCDF subset via GridDAP",
        extra={
            "model": config.model_name.value,
            "region": config.region.value,
            "netcdf_file": filename,
            "variables": config.data_variables,
            "url": url[:100] + "...",
        },
    )

    # 512KB chunks for 1-5MB files
    total_bytes = await resources.http.download_stream(
        url,
        file_path=str(file_path),
        chunk_size=512 * 1024,
    )

    logger.info(
        "Download complete",
        extra={
            "netcdf_file": filename,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
        },
    )

    return file_path


def cleanup_netcdf_file(file_path: Path) -> None:
    """
    Remove NetCDF file after successful extraction.

    Called after successful extraction to free disk space.
    """
    if file_path.exists():
        file_path.unlink()
