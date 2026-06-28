from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap
from PIL import Image, ImageEnhance
from rasterio.transform import Affine


def load_profile_txt(path: str | Path) -> np.ndarray:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="ignore")
    values: list[float] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for token in re.split(r"[\s,;]+", stripped):
            if not token:
                continue
            try:
                value = float(token)
            except ValueError as exc:
                raise ValueError("TXT файл содержит некорректные данные. Загрузите другой файл.") from exc
            if math.isinf(value):
                raise ValueError("TXT файл содержит некорректные данные. Загрузите другой файл.")
            values.append(value)

    if len(values) < 5:
        raise ValueError("TXT файл содержит некорректные данные. Загрузите другой файл.")
    return np.asarray(values, dtype=float)


def read_geotiff(path: str | Path) -> dict:
    p = Path(path)
    with rasterio.open(p) as src:
        arr = src.read(1, masked=True).astype(np.float32)
        elevation = np.asarray(arr.filled(np.nan), dtype=np.float32)
        if src.nodata is not None:
            elevation[elevation == src.nodata] = np.nan
        transform = src.transform
        width = src.width
        height = src.height
        bounds = src.bounds
        crs = src.crs.to_string() if src.crs else None
        is_geographic = bool(src.crs.is_geographic) if src.crs else False

        preview_width = min(1600, width)
        preview_height = max(1, int(round(height * preview_width / width)))
        if preview_height > 1600:
            preview_height = 1600
            preview_width = max(1, int(round(width * preview_height / height)))

        return {
            "elevation": elevation,
            "transform": transform,
            "width": width,
            "height": height,
            "bounds": {
                "left": float(bounds.left),
                "bottom": float(bounds.bottom),
                "right": float(bounds.right),
                "top": float(bounds.top),
            },
            "crs": crs,
            "is_geographic": is_geographic,
            "preview_size": (int(preview_width), int(preview_height)),
        }


def pixel_size_m(transform: Affine, crs_is_geographic: bool, y_ref: float | None = None) -> float:
    a = float(abs(transform.a))
    e = float(abs(transform.e))
    base = max(1e-9, (a + e) / 2.0)
    if not crs_is_geographic:
        return base

    lat = float(y_ref) if y_ref is not None else 0.0
    lat_rad = math.radians(lat)
    meters_per_deg_lat = (
        111132.92
        - 559.82 * math.cos(2.0 * lat_rad)
        + 1.175 * math.cos(4.0 * lat_rad)
        - 0.0023 * math.cos(6.0 * lat_rad)
    )
    meters_per_deg_lon = (
        111412.84 * math.cos(lat_rad)
        - 93.5 * math.cos(3.0 * lat_rad)
        + 0.118 * math.cos(5.0 * lat_rad)
    )
    return max(1e-9, (a * abs(meters_per_deg_lon) + e * abs(meters_per_deg_lat)) / 2.0)


def save_preview_png(elevation: np.ndarray, path: str | Path, preview_size: tuple[int, int]) -> tuple[int, int]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = np.asarray(elevation, dtype=np.float32)
    valid = np.isfinite(data)
    if not valid.any():
        raise ValueError("GeoTIFF не содержит валидных значений высот")

    vmin = float(np.nanpercentile(data, 2))
    vmax = float(np.nanpercentile(data, 98))
    if not np.isfinite(vmin) or not np.isfinite(vmax) or abs(vmax - vmin) < 1e-9:
        vmin = float(np.nanmin(data[valid]))
        vmax = vmin + 1.0

    # Мягкая, более дружелюбная палитра без кислотности
    cmap = LinearSegmentedColormap.from_list(
        "terrain_soft_rich",
        [
            "#16212d",
            "#253849",
            "#355462",
            "#4e6b67",
            "#6f8365",
            "#9b9a76",
            "#c0a07a",
            "#a06f4d",
        ],
        N=256,
    )

    width, height = int(preview_size[0]), int(preview_size[1])
    fig = plt.figure(figsize=(width / 160.0, height / 160.0), dpi=160)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_facecolor("#15202b")
    ax.imshow(np.ma.masked_invalid(data), cmap=cmap, vmin=vmin, vmax=vmax, interpolation="bilinear")
    fig.savefig(path, bbox_inches=None, pad_inches=0)
    plt.close(fig)

    img = Image.open(path).convert("RGB")
    img = ImageEnhance.Color(img).enhance(0.88)
    img = ImageEnhance.Contrast(img).enhance(0.96)
    img.save(path)
    return img.size


def world_to_pixel(transform: Affine, x: float, y: float) -> tuple[float, float]:
    inv = ~transform
    col, row = inv * (x, y)
    return float(row), float(col)


def pixel_to_world(transform: Affine, row: float, col: float) -> tuple[float, float]:
    x, y = transform * (col, row)
    return float(x), float(y)
