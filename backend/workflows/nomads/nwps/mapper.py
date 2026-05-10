import numpy as np
from pandas import Timestamp


# NWPS GRIB2 variable → payload key path. tuple = nested dict path.
NWPS_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "swh": ("wave", "significant_height"),
    "perpw": ("wave", "peak_period"),
    "dirpw": ("wave", "peak_direction"),
    "shts": ("wave", "primary_swell", "height"),
    "ws": ("wind", "speed"),
    "wdir": ("wind", "direction"),
    "zos": ("tide", "height"),
}


def _set_nested(d: dict, path: tuple[str, ...], value: float) -> None:
    """Insert value into nested dict, creating intermediate dicts as needed."""
    cur = d
    for key in path[:-1]:
        cur = cur.setdefault(key, {})
    cur[path[-1]] = value


def build_nwps_rows(
    lats: np.ndarray,
    lons: np.ndarray,
    valid_times: list[Timestamp],
    arrs: dict[str, np.ndarray],
    model_run_id: int,
) -> list[dict]:
    """
    Vectorized NWPS row builder for bulk insert into forecast_data.

    Skips Pydantic, produces DB-ready dicts directly from numpy arrays.
    Output payload shape mirrors ForecastPoint.model_dump(exclude_none=True)
    so the API read path can re-validate without a shim.

    Shape contract (per row payload):
        {
            "valid_time": "<isoformat>",
            "wave": {"significant_height", "peak_period", "peak_direction",
                     "primary_swell": {"height": ...}},
            "wind": {"speed", "direction"},
            "tide": {"height"},
        }
    Empty category dicts (all NaN) are omitted.
    """
    n_steps = len(valid_times)
    n_cells = len(lats)

    # pre-flatten all arrays
    # arr shape: (n_steps, n_cells) → .T → (n_cells, n_steps) → ravel → 1D cell-major
    # accessing flat[var][idx] is pure Python list indexing, no numpy overhead per row
    flat: dict[str, list[float]] = {
        var: arr.T.ravel().tolist() for var, arr in arrs.items()
    }
    nan_masks: dict[str, list[bool]] = {
        var: np.isnan(arr).T.ravel().tolist() for var, arr in arrs.items()
    }
    flat_lats: list[float] = np.repeat(lats, n_steps).tolist()
    flat_lons: list[float] = np.repeat(lons, n_steps).tolist()

    # python list multiplication is O(n) copy, no numpy needed for Timestamp/str
    vt_iso: list[str] = [vt.isoformat() for vt in valid_times] * n_cells
    vt_py: list[Timestamp] = valid_times * n_cells

    def _build_payload(idx: int) -> dict:
        payload = {"valid_time": vt_iso[idx]}

        for var, path in NWPS_FIELD_MAP.items():
            if nan_masks[var][idx]:
                continue  # avoids writing then deleting
            _set_nested(payload, path, flat[var][idx])

        for cat in ("wave", "wind", "tide"):
            if cat in payload and not payload[cat]:
                del payload[cat]

        return payload

    return [
        {
            "valid_time": vt_py[idx],
            "model_run_id": model_run_id,
            "lat": flat_lats[idx],
            "lon": flat_lons[idx],
            "payload": _build_payload(idx),
        }
        for idx in range(n_cells * n_steps)
    ]
