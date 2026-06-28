from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .kalman import smooth_profile_kalman
from .profiles import correlation_interpolated, sample_profile


@dataclass
class MatchParams:
    destination_x: float
    destination_y: float
    drone_speed_m_s: float
    altimeter_freq_hz: float
    use_kalman: bool
    kalman_q: float
    kalman_r: float
    coarse_step: int
    fine_step: int
    corr_threshold: float
    search_span_deg: float = 120.0


def _top_angles(correlations: np.ndarray, n: int = 8) -> list[dict]:
    pairs: list[tuple[int, float]] = []
    for angle, corr in enumerate(correlations):
        if np.isfinite(corr):
            pairs.append((int(angle), float(corr)))
    pairs.sort(key=lambda item: item[1], reverse=True)
    return [{"angle": angle, "correlation": corr} for angle, corr in pairs[:n]]


def _window_angles(center: float, span: float, step: int) -> list[int]:
    half = max(0, int(round(span / 2.0)))
    angles = []
    a = int(round(center)) - half
    b = int(round(center)) + half
    for angle in range(a, b + 1, int(step)):
        angles.append(int(angle % 360))
    ordered = []
    seen = set()
    for angle in angles:
        if angle not in seen:
            seen.add(angle)
            ordered.append(angle)
    return ordered


def hierarchical_match(
    elevation: np.ndarray,
    start_pixel: tuple[float, float],
    ref_heights_raw: np.ndarray,
    pixel_size_m: float,
    params: MatchParams,
    reference_angle_deg: float,
    emit: Optional[Callable[[dict], None]] = None,
) -> dict:
    def send(payload: dict) -> None:
        if emit is not None:
            emit(payload)

    if params.drone_speed_m_s <= 0 or params.altimeter_freq_hz <= 0:
        raise ValueError("drone_speed_m_s and altimeter_freq_hz must be positive")

    center_row, center_col = float(start_pixel[0]), float(start_pixel[1])
    sample_step_m = params.drone_speed_m_s / params.altimeter_freq_hz
    if sample_step_m <= 0:
        raise ValueError("computed sample step must be positive")

    if params.use_kalman:
        ref_heights = smooth_profile_kalman(ref_heights_raw, params.kalman_q, params.kalman_r)
    else:
        ref_heights = np.asarray(ref_heights_raw, dtype=float)

    ref_dist = np.arange(len(ref_heights), dtype=float) * sample_step_m
    valid_ref = np.isfinite(ref_heights)
    if valid_ref.sum() < 5:
        raise ValueError("reference profile has too few valid values")
    ref_heights = ref_heights[valid_ref]
    ref_dist = ref_dist[valid_ref]

    height, width = elevation.shape
    edge_dists = [
        np.sqrt(center_row ** 2 + center_col ** 2),
        np.sqrt(center_row ** 2 + (width - center_col) ** 2),
        np.sqrt((height - center_row) ** 2 + center_col ** 2),
        np.sqrt((height - center_row) ** 2 + (width - center_col) ** 2),
    ]
    max_possible_m = min(edge_dists) * pixel_size_m
    ref_length_m = float(ref_dist[-1]) if len(ref_dist) else 0.0
    max_dist_m = max(10.0, min(max_possible_m, ref_length_m))

    common_step = max(0.25 * sample_step_m, 0.25 * pixel_size_m, 1e-3)
    common_dist = np.arange(0.0, max_dist_m + common_step, common_step, dtype=float)
    if len(common_dist) < 8:
        common_dist = np.linspace(0.0, max_dist_m, 8)

    send({"type": "status", "message": "Сканирование направления от стартовой точки"})

    coarse_angles = _window_angles(reference_angle_deg, params.search_span_deg, params.coarse_step)
    if not coarse_angles:
        coarse_angles = [int(round(reference_angle_deg)) % 360]

    coarse_corrs: dict[int, float] = {}
    candidates: list[int] = []

    for i, angle in enumerate(coarse_angles, start=1):
        vals, dist_m, _ = sample_profile(
            elevation,
            center_row,
            center_col,
            angle,
            max_dist_m,
            sample_step_m,
            pixel_size_m,
        )
        corr = correlation_interpolated(vals, dist_m, ref_heights, ref_dist, common_dist) if vals is not None else float("nan")
        coarse_corrs[int(angle)] = corr
        if np.isfinite(corr) and corr >= params.corr_threshold:
            candidates.append(int(angle))
        pct = 5 + int(35 * i / max(1, len(coarse_angles)))
        send({"type": "progress", "value": pct, "message": f"Грубый проход {i}/{len(coarse_angles)}"})

    if not candidates and coarse_corrs:
        candidates = [int(max(coarse_corrs, key=lambda key: coarse_corrs[key]))]

    send({"type": "status", "message": "Уточнение направления"})
    final_corrs = np.full(360, np.nan, dtype=float)
    processed: set[int] = set()
    best_profile = None
    best_angle = None
    best_corr = float("-inf")

    for ci, cand in enumerate(candidates, start=1):
        start_a = cand - int(params.coarse_step) // 2
        end_a = cand + int(params.coarse_step) // 2
        sector = np.arange(start_a, end_a + int(params.fine_step), int(params.fine_step), dtype=int)
        for angle in sector:
            ang = int(angle % 360)
            if ang in processed:
                continue
            processed.add(ang)
            vals, dist_m, _ = sample_profile(
                elevation,
                center_row,
                center_col,
                ang,
                max_dist_m,
                sample_step_m,
                pixel_size_m,
            )
            corr = correlation_interpolated(vals, dist_m, ref_heights, ref_dist, common_dist) if vals is not None else float("nan")
            final_corrs[ang] = corr
            if np.isfinite(corr) and corr > best_corr:
                best_corr = float(corr)
                best_angle = ang
                best_profile = {
                    "distances_m": dist_m.tolist() if dist_m is not None else [],
                    "heights_m": vals.tolist() if vals is not None else [],
                }
        pct = 40 + int(50 * ci / max(1, len(candidates)))
        send({"type": "progress", "value": pct, "message": f"Точный проход {ci}/{len(candidates)}"})

    for ang, corr in coarse_corrs.items():
        if not np.isfinite(final_corrs[ang]):
            final_corrs[ang] = corr

    valid = np.isfinite(final_corrs)
    if valid.any():
        if best_angle is None:
            best_angle = int(np.nanargmax(final_corrs))
            best_corr = float(final_corrs[best_angle])
    else:
        best_angle = int(round(reference_angle_deg)) % 360
        best_corr = float("nan")

    if best_profile is None and best_angle is not None:
        vals, dist_m, _ = sample_profile(
            elevation,
            center_row,
            center_col,
            best_angle,
            max_dist_m,
            sample_step_m,
            pixel_size_m,
        )
        if vals is not None:
            best_profile = {
                "distances_m": dist_m.tolist(),
                "heights_m": vals.tolist(),
            }

    top8 = _top_angles(final_corrs, 8)

    return {
        "best_angle": int(best_angle) if best_angle is not None else None,
        "best_correlation": None if not np.isfinite(best_corr) else float(best_corr),
        "top_angles": top8,
        "correlations": [None if not np.isfinite(x) else float(x) for x in final_corrs.tolist()],
        "reference_profile": {
            "distances_m": ref_dist.tolist(),
            "heights_m": ref_heights.tolist(),
        },
        "best_profile": best_profile,
        "analysis": {
            "sample_step_m": float(sample_step_m),
            "pixel_size_m": float(pixel_size_m),
            "max_distance_m": float(max_dist_m),
            "coarse_step": int(params.coarse_step),
            "fine_step": int(params.fine_step),
            "corr_threshold": float(params.corr_threshold),
            "use_kalman": bool(params.use_kalman),
            "kalman_q": float(params.kalman_q),
            "kalman_r": float(params.kalman_r),
            "search_span_deg": float(params.search_span_deg),
            "reference_angle_deg": float(reference_angle_deg),
            "candidates": len(candidates),
            "processed_angles": len(processed),
        },
        "start_pixel": {"row": float(center_row), "col": float(center_col)},
        "best_ray_end_pixel": None,
    }
