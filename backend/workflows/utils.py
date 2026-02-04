from datetime import datetime, timedelta, timezone
from prefect.runtime.flow_run import get_scheduled_start_time


def stale_flow(fresh_threshold: timedelta) -> bool:
    scheduled_start_time = get_scheduled_start_time()
    if scheduled_start_time is None:
        return False

    now = datetime.now(tz=timezone.utc)
    difference = now - scheduled_start_time

    return difference > fresh_threshold
