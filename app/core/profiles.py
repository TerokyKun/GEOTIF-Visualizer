from __future__ import annotations

import math
from typing import Optional

import numpy as np
from scipy.interpolate import interp1d
from scipy.ndimage import map_coordinates


def sample_profile(
    elevation: np.ndarray,
    center_row: float,
    center_col: float,
    angle_deg: float,
    max_distance_m: float,
    sample_step_m: float,
    pixel_size_m: float,
) -> tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    if sample_step_m <= 0 or pixel_size_m <= 0:
        raise ValueError("sample_step_m and pixel_size_m must be positive")

    height, width = elevation.shape
    angle_rad = math.radians(angle_deg % 360.0)
    dx = math.cos(angle_rad)
    dy = -math.sin(angle_rad)

    step_px = sample_step_m / pixel_size_m
    max_dist_px = max_distance_m / pixel_size_m

    dist_px = np.arange(0.0, max_dist_px + 1e-9, step_px, dtype=float)
    rows = center_row + dy * dist_px
    cols = center_col + dx * dist_px

    mask = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)
    if mask.sum() < 5:
        return None, None, None

    rows_v = rows[mask]
    cols_v = cols[mask]
    dist_px_v = dist_px[mask]

    coords = np.array([rows_v, cols_v])
    values = map_coordinates(elevation, coords, order=1, mode="nearest")

    valid = np.isfinite(values)
    if valid.sum() < 5:
        return None, None, None

    values = values[valid].astype(float)
    dist_px_v = dist_px_v[valid].astype(float)
    dist_m = dist_px_v * pixel_size_m
    return values, dist_m, dist_px_v


def correlation_interpolated(
    p1_vals: np.ndarray,
    p1_dist: np.ndarray,
    p2_vals: np.ndarray,
    p2_dist: np.ndarray,
    common_dist: np.ndarray,
) -> float:
    try:
        if p1_vals is None or p2_vals is None:
            return float("nan")
        f1 = interp1d(p1_dist, p1_vals, kind="linear", bounds_error=False, fill_value=np.nan)
        f2 = interp1d(p2_dist, p2_vals, kind="linear", bounds_error=False, fill_value=np.nan)
        v1 = f1(common_dist)
        v2 = f2(common_dist)
        valid = np.isfinite(v1) & np.isfinite(v2)
        if valid.sum() < 5:
            return float("nan")
        a = v1[valid]
        b = v2[valid]
        if np.std(a) == 0 or np.std(b) == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])
    except Exception:
        return float("nan")
