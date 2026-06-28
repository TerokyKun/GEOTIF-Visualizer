from __future__ import annotations

import asyncio
import json
import math
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    CONFIG_FILENAME,
    DATA_DIR,
    DEFAULT_ANALYSIS,
    HEIGHTS_FILENAME,
    INPUT_DIR,
    MAP_FILENAME,
    PREVIEW_FILENAME,
    RUNTIME_DIR,
    UPLOADS_DIR,
)
from app.core.io import load_profile_txt, pixel_size_m, pixel_to_world, read_geotiff, save_preview_png, world_to_pixel
from app.core.matching import MatchParams, hierarchical_match

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STATIC_DIR = ROOT_DIR / "static"

app = FastAPI(title="Визуализатор алгоритма")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

STATE: dict[str, Any] = {
    "mode": "demo",
    "source_id": "demo",
    "bundle": None,
    "raw": None,
    "files": None,
}


@dataclass(frozen=True)
class ProjectFiles:
    map_path: Path
    heights_path: Path
    config_path: Path | None
    preview_path: Path
    source_id: str
    mode: str
    label: str


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _read_config(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _merge_analysis_config(raw: dict[str, Any]) -> dict[str, Any]:
    merged = dict(DEFAULT_ANALYSIS)
    analysis_block = raw.get("analysis") if isinstance(raw.get("analysis"), dict) else raw
    if isinstance(analysis_block, dict):
        for key, value in analysis_block.items():
            if key in merged:
                merged[key] = value
    return merged


def _center_pixel(geo: dict[str, Any]) -> tuple[float, float]:
    return float(geo["height"]) / 2.0, float(geo["width"]) / 2.0


def _default_destination_pixel(geo: dict[str, Any]) -> tuple[float, float]:
    center_row, center_col = _center_pixel(geo)
    row = center_row - max(20.0, geo["height"] * 0.12)
    col = center_col + max(20.0, geo["width"] * 0.18)
    row = min(max(0.0, row), float(geo["height"] - 1))
    col = min(max(0.0, col), float(geo["width"] - 1))
    return row, col


def _angle_from_center_to_dest(center_row: float, center_col: float, dest_row: float, dest_col: float) -> float:
    dx = dest_col - center_col
    dy = center_row - dest_row
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return 0.0
    return float((math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0)


def _project_files_demo() -> ProjectFiles:
    return ProjectFiles(
        map_path=INPUT_DIR / MAP_FILENAME,
        heights_path=INPUT_DIR / HEIGHTS_FILENAME,
        config_path=INPUT_DIR / CONFIG_FILENAME,
        preview_path=RUNTIME_DIR / PREVIEW_FILENAME,
        source_id="demo",
        mode="demo",
        label="Демо",
    )


def _build_bundle(files: ProjectFiles) -> tuple[dict[str, Any], dict[str, Any]]:
    geo = read_geotiff(files.map_path)
    preview_size = save_preview_png(geo["elevation"], files.preview_path, geo["preview_size"])
    ref_values = load_profile_txt(files.heights_path)
    raw_config = _read_config(files.config_path)
    analysis = _merge_analysis_config(raw_config)
    center_row, center_col = _center_pixel(geo)
    center_world = pixel_to_world(geo["transform"], center_row, center_col)
    dest_row, dest_col = _default_destination_pixel(geo)
    dest_world = pixel_to_world(geo["transform"], dest_row, dest_col)
    pixel_m = pixel_size_m(geo["transform"], geo["is_geographic"], y_ref=center_world[1])

    bundle = {
        "ready": True,
        "mode": files.mode,
        "mode_label": files.label,
        "source_id": files.source_id,
        "message": "Демо готово" if files.mode == "demo" else "Свои файлы загружены",
        "files": {
            "map": str(files.map_path),
            "heights": str(files.heights_path),
            "config": str(files.config_path) if files.config_path else None,
        },
        "analysis_defaults": analysis,
        "preview_path": str(files.preview_path),
        "preview_url": "/api/preview",
        "preview_size": {"width": int(preview_size[0]), "height": int(preview_size[1])},
        "preview_scale": {
            "x": float(preview_size[0]) / float(geo["width"]),
            "y": float(preview_size[1]) / float(geo["height"]),
        },
        "start_pixel": {"row": float(center_row), "col": float(center_col)},
        "start_world": {"x": float(center_world[0]), "y": float(center_world[1])},
        "default_destination_pixel": {"row": float(dest_row), "col": float(dest_col)},
        "default_destination_world": {"x": float(dest_world[0]), "y": float(dest_world[1])},
        "raster": {
            "width": int(geo["width"]),
            "height": int(geo["height"]),
            "bounds": geo["bounds"],
            "crs": geo["crs"],
            "transform": [
                float(geo["transform"].a),
                float(geo["transform"].b),
                float(geo["transform"].c),
                float(geo["transform"].d),
                float(geo["transform"].e),
                float(geo["transform"].f),
            ],
            "pixel_size_m": float(pixel_m),
        },
        "reference_length": int(len(ref_values)),
    }

    raw = {
        "geo": geo,
        "ref_values": ref_values,
        "analysis": analysis,
        "files": files,
    }
    return bundle, raw


def _set_state(bundle: dict[str, Any], raw: dict[str, Any], files: ProjectFiles) -> dict[str, Any]:
    STATE["mode"] = files.mode
    STATE["source_id"] = files.source_id
    STATE["bundle"] = bundle
    STATE["raw"] = raw
    STATE["files"] = {
        "map": str(files.map_path),
        "heights": str(files.heights_path),
        "config": str(files.config_path) if files.config_path else None,
        "preview": str(files.preview_path),
    }
    return bundle


def _load_demo(force: bool = False) -> dict[str, Any]:
    _ensure_dirs()
    current = STATE.get("bundle")
    if current is not None and not force and STATE.get("mode") == "demo":
        return current
    files = _project_files_demo()
    if not files.map_path.exists() or not files.heights_path.exists():
        bundle = {
            "ready": False,
            "mode": "demo",
            "mode_label": "Демо",
            "message": "Не найдены demo-файлы в data/",
            "missing": [str(p) for p in [files.map_path, files.heights_path, files.config_path] if p and not p.exists()],
            "files": {
                "map": str(files.map_path),
                "heights": str(files.heights_path),
                "config": str(files.config_path),
            },
        }
        STATE["bundle"] = bundle
        STATE["raw"] = None
        STATE["files"] = None
        return bundle
    bundle, raw = _build_bundle(files)
    return _set_state(bundle, raw, files)


def _load_upload(force: bool = False) -> dict[str, Any]:
    if STATE.get("mode") != "upload" or STATE.get("bundle") is None:
        raise HTTPException(status_code=409, detail="Нет пользовательского набора файлов")
    if not force:
        return STATE["bundle"]
    files = STATE.get("files")
    if not files:
        return STATE["bundle"]
    project_files = ProjectFiles(
        map_path=Path(files["map"]),
        heights_path=Path(files["heights"]),
        config_path=Path(files["config"]) if files.get("config") else None,
        preview_path=Path(files["preview"]),
        source_id=STATE.get("source_id") or "upload",
        mode="upload",
        label="Свои файлы",
    )
    bundle, raw = _build_bundle(project_files)
    return _set_state(bundle, raw, project_files)


def _current_bundle() -> dict[str, Any]:
    if STATE.get("mode") == "upload":
        return _load_upload(force=False)
    return _load_demo(force=False)


def _validate_analysis(payload: dict[str, Any], defaults: dict[str, Any]) -> MatchParams:
    try:
        destination_x = float(payload["destination_x"])
        destination_y = float(payload["destination_y"])
    except Exception:
        raise HTTPException(status_code=422, detail="Нужно передать координаты точки 2")

    merged = dict(defaults)
    for key in DEFAULT_ANALYSIS:
        if key in payload:
            merged[key] = payload[key]

    try:
        drone_speed_m_s = float(merged["drone_speed_m_s"])
        altimeter_freq_hz = float(merged["altimeter_freq_hz"])
        use_kalman = bool(merged["use_kalman"])
        kalman_q = float(merged["kalman_q"])
        kalman_r = float(merged["kalman_r"])
        coarse_step = int(merged["coarse_step"])
        fine_step = int(merged["fine_step"])
        corr_threshold = float(merged["corr_threshold"])
        search_span_deg = float(merged.get("search_span_deg", 120.0))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Некорректные параметры анализа: {exc}")

    return MatchParams(
        destination_x=destination_x,
        destination_y=destination_y,
        drone_speed_m_s=drone_speed_m_s,
        altimeter_freq_hz=altimeter_freq_hz,
        use_kalman=use_kalman,
        kalman_q=kalman_q,
        kalman_r=kalman_r,
        coarse_step=coarse_step,
        fine_step=fine_step,
        corr_threshold=corr_threshold,
        search_span_deg=search_span_deg,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/project")
def project() -> dict[str, Any]:
    return _current_bundle()


@app.post("/api/demo")
def demo() -> dict[str, Any]:
    STATE["mode"] = "demo"
    STATE["source_id"] = "demo"
    return _load_demo(force=True)


@app.post("/api/reload")
def reload_project() -> dict[str, Any]:
    if STATE.get("mode") == "upload":
        return _load_upload(force=True)
    return _load_demo(force=True)


@app.get("/api/preview")
def preview() -> FileResponse:
    bundle = _current_bundle()
    if not bundle.get("ready"):
        raise HTTPException(status_code=404, detail="Карта не готова")
    return FileResponse(bundle["preview_path"], media_type="image/png")


@app.post("/api/upload")
async def upload(tiff: UploadFile = File(...), profile: UploadFile = File(...), config: UploadFile | None = File(None)) -> dict[str, Any]:
    if not tiff.filename.lower().endswith((".tif", ".tiff")):
        raise HTTPException(status_code=400, detail="Нужен файл GeoTIFF (.tif/.tiff)")
    if not profile.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Нужен TXT-файл")
    if config is not None and not config.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="Конфиг должен быть JSON")

    _ensure_dirs()
    job_id = uuid.uuid4().hex[:12]
    base = UPLOADS_DIR / job_id
    base.mkdir(parents=True, exist_ok=True)
    tif_path = base / "terrain.tif"
    txt_path = base / "heights.txt"
    cfg_path = base / "config.json"
    preview_path = base / "terrain_preview.png"

    with tif_path.open("wb") as out:
        shutil.copyfileobj(tiff.file, out)
    with txt_path.open("wb") as out:
        shutil.copyfileobj(profile.file, out)
    if config is not None:
        with cfg_path.open("wb") as out:
            shutil.copyfileobj(config.file, out)
    else:
        cfg_path = None

    files = ProjectFiles(
        map_path=tif_path,
        heights_path=txt_path,
        config_path=cfg_path,
        preview_path=preview_path,
        source_id=job_id,
        mode="upload",
        label="Свои файлы",
    )

    try:
        bundle, raw = _build_bundle(files)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _set_state(bundle, raw, files)


@app.post("/api/analyze")
async def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    bundle = _current_bundle()
    if not bundle.get("ready"):
        raise HTTPException(status_code=409, detail="Файлы проекта не загружены")

    params = _validate_analysis(payload, bundle["analysis_defaults"])
    raw = STATE.get("raw") or {}
    geo = raw.get("geo")
    ref_values_raw = raw.get("ref_values")
    if geo is None or ref_values_raw is None:
        raise HTTPException(status_code=409, detail="Сервер не готов к анализу")

    center_row, center_col = _center_pixel(geo)
    dest_row, dest_col = world_to_pixel(geo["transform"], params.destination_x, params.destination_y)
    dest_row = float(min(max(0.0, dest_row), geo["height"] - 1))
    dest_col = float(min(max(0.0, dest_col), geo["width"] - 1))
    reference_angle = _angle_from_center_to_dest(center_row, center_col, dest_row, dest_col)
    pixel_m = pixel_size_m(geo["transform"], geo["is_geographic"], y_ref=params.destination_y)

    result = await asyncio.to_thread(
        hierarchical_match,
        np.asarray(geo["elevation"], dtype=float),
        (center_row, center_col),
        np.asarray(ref_values_raw, dtype=float),
        pixel_m,
        params,
        reference_angle,
        None,
    )

    best_angle = result.get("best_angle")
    top_angles = result.get("top_angles", [])

    return {
        "ok": True,
        "message": "Анализ завершён",
        "analysis": result,
        "path": {
            "start": {
                "pixel": {"row": float(center_row), "col": float(center_col)},
                "world": bundle["start_world"],
            },
            "destination": {
                "pixel": {"row": float(dest_row), "col": float(dest_col)},
                "world": {"x": float(params.destination_x), "y": float(params.destination_y)},
            },
        },
        "top_angles": top_angles,
        "best_angle": best_angle,
        "best_correlation": result.get("best_correlation"),
        "center": {"row": float(center_row), "col": float(center_col)},
        "meta": {
            "reference_length": bundle["reference_length"],
            "pixel_size_m": float(pixel_m),
            "reference_angle": float(reference_angle),
            "mode": bundle.get("mode"),
        },
    }
