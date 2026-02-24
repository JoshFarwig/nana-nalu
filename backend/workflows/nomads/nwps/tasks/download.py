"""
GRIB2 file download task.

Downloads NWPS GRIB2 files from NOMADS grib filter with streaming
to handle large file sizes (20-30MB typical).
"""

from datetime import date, datetime, time, timezone
from pathlib import Path

from prefect import task, get_run_logger
from prefect.context import get_run_context

from workflows.resources import get_resources
from services.forecast.nomads_config import NWPSConfig


DOWNLOAD_DIR = Path("/backend/.tmp/nomads/")


@task(name="nwps-download-grib2", retries=3, retry_delay_seconds=60)
def download_grib2(
    config: NWPSConfig,
    analysis_time: time,
    forecast_date: date | None = None,
) -> Path:
    """
    Download GRIB2 file from NOMADS grib filter.

    Uses streaming download to handle large files efficiently.
    Files are saved to /backend/.tmp/nomads/ directory.

    Args:
        config: NWPS configuration for the region
        analysis_time: Model analysis time (e.g., 06:00 UTC)
        forecast_date: Forecast date, defaults to today UTC

    Returns:
        Path to downloaded GRIB2 file
    """
    logger = get_run_logger()
    resources = get_resources()

    if forecast_date is None:
        forecast_date = datetime.now(timezone.utc).date()

    url = config.construct_grib_filter_url(analysis_time, forecast_date)
    filename = config.construct_filename(analysis_time, forecast_date)

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # append task_name to file_path to ensure no back-scheduled tasks run concurrently on the same grib2 file
    ctx = get_run_context()
    task_name = ctx.task.name
    file_path = DOWNLOAD_DIR / filename.replace(".grib2", f"_{task_name}.grib2")

    logger.info(
        "Downloading GRIB2 file",
        extra={
            "region": config.region.value,
            "grib2_file": filename,
            "url": url[:100] + "...",
        },
    )

    # 512KB chunks for 20-30MB files
    total_bytes = resources.http.download_stream(
        url,
        file_path=str(file_path),
        chunk_size=512 * 1024,
    )

    logger.info(
        "Download complete",
        extra={
            "grib2_file": filename,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
        },
    )

    return file_path


def cleanup_grib2_file(file_path: Path) -> None:
    """
    Remove GRIB2 file and associated index files.

    Called after successful extraction to free disk space.
    """
    for idx_file in file_path.parent.glob(f"{file_path.name}.*.idx"):
        idx_file.unlink()

    if file_path.exists():
        file_path.unlink()
