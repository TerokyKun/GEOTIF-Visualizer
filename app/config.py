from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DATA_DIR = ROOT_DIR / "data"
RUNTIME_DIR = ROOT_DIR / "runtime"
UPLOADS_DIR = RUNTIME_DIR / "uploads"

INPUT_DIR = DATA_DIR
MAP_FILENAME = "terrain.tif"
HEIGHTS_FILENAME = "heights.txt"
CONFIG_FILENAME = "config.json"
PREVIEW_FILENAME = "terrain_preview.png"

DEFAULT_ANALYSIS = {
    "drone_speed_m_s": 10.0,
    "altimeter_freq_hz": 10.0,
    "use_kalman": True,
    "kalman_q": 0.10,
    "kalman_r": 1.0,
    "coarse_step": 10,
    "fine_step": 1,
    "corr_threshold": 0.30,
    "search_span_deg": 120.0,
}
