"""
Is It In? — FastAPI backend
============================
Multi-river support. Each river has its own prediction cache and model.

Run with:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import json
from pathlib import Path

import os

import pandas as pd
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from rivers import RIVERS, RiverConfig, stage_to_visual
from tellico_predictor import run_prediction
from dashboard import build_figure

RIVER_REQUESTS_FILE = Path(__file__).parent / "river_requests.json"

# ---------------------------------------------------------------------------
# Per-river cache
# ---------------------------------------------------------------------------

_caches: dict[str, dict] = {
    river_id: {"results": None, "updated_at": None}
    for river_id in RIVERS
}

CACHE_TTL_MINUTES = 60


def get_results(river_id: str, force: bool = False) -> dict:
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail=f"River '{river_id}' not found")

    cache = _caches[river_id]
    river = RIVERS[river_id]
    now = datetime.now()
    stale = (
        cache["results"] is None
        or cache["updated_at"] is None
        or (now - cache["updated_at"]) > timedelta(minutes=CACHE_TTL_MINUTES)
    )
    if force or stale:
        print(f"[{now:%H:%M:%S}] Running prediction for {river.name}...")
        cache["results"] = run_prediction(river=river, verbose=False)
        cache["updated_at"] = datetime.now()
        print(f"[{datetime.now():%H:%M:%S}] Done — {river.name}")
    return cache["results"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfs_status(cfs: float, river: RiverConfig) -> str:
    if cfs < river.runnable_min:
        return "TOO LOW"
    elif cfs > river.runnable_max:
        return "TOO HIGH"
    elif river.sweet_spot_min <= cfs <= river.sweet_spot_max:
        return "SWEET SPOT"
    return "RUNNABLE"

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm up runs in a background thread so the port binds immediately
    import asyncio, concurrent.futures
    def _warmup():
        for river_id in RIVERS:
            try:
                get_results(river_id)
            except Exception as e:
                print(f"Warning: could not warm up {river_id}: {e}")
    loop = asyncio.get_event_loop()
    loop.run_in_executor(concurrent.futures.ThreadPoolExecutor(max_workers=1), _warmup)
    yield


app = FastAPI(title="Is It In?", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {"message": "Is It In? API", "docs": "/docs", "rivers": list(RIVERS.keys())}


@app.get("/rivers")
def list_rivers():
    """Index of all rivers with current status — powers the home screen."""
    items = []
    for river_id, river in RIVERS.items():
        try:
            results = get_results(river_id)
            cfs = float(results["current_cfs"])
            status = _cfs_status(cfs, river)
            items.append({
                "id":          river_id,
                "name":        river.name,
                "gauge_id":    river.gauge_id,
                "current_cfs": round(cfs),
                "status":      status,
                "runnable":    river.runnable_min <= cfs <= river.runnable_max,
                "sweet_spot":  river.sweet_spot_min <= cfs <= river.sweet_spot_max,
                "updated_at":  _caches[river_id]["updated_at"].isoformat(),
                "range": {
                    "runnable_min":  river.runnable_min,
                    "runnable_max":  river.runnable_max,
                    "sweet_min":     river.sweet_spot_min,
                    "sweet_max":     river.sweet_spot_max,
                },
            })
        except Exception as e:
            items.append({
                "id": river_id, "name": river.name, "error": str(e),
                "current_cfs": 0, "status": "UNKNOWN", "runnable": False, "sweet_spot": False,
                "updated_at": datetime.now().isoformat(),
                "range": {
                    "runnable_min": river.runnable_min, "runnable_max": river.runnable_max,
                    "sweet_min": river.sweet_spot_min, "sweet_max": river.sweet_spot_max,
                },
            })
    return items


@app.get("/rivers/{river_id}/status")
def get_status(river_id: str):
    river = RIVERS.get(river_id)
    if not river:
        raise HTTPException(status_code=404, detail="River not found")
    results = get_results(river_id)
    cfs = float(results["current_cfs"])
    status = _cfs_status(cfs, river)
    return {
        "river":        river.name,
        "gauge_id":     river.gauge_id,
        "current_cfs":  round(cfs, 2),
        "display_unit": river.display_unit,
        "status":       status,
        "paddable":     river.runnable_min <= cfs <= river.runnable_max,
        "sweet_spot":   river.sweet_spot_min <= cfs <= river.sweet_spot_max,
        "range": {
            "paddable_min": river.runnable_min,
            "paddable_max": river.runnable_max,
            "sweet_min":    river.sweet_spot_min,
            "sweet_max":    river.sweet_spot_max,
        },
        "updated_at": _caches[river_id]["updated_at"].isoformat(),
    }


@app.get("/rivers/{river_id}/forecast/daily")
def get_daily(river_id: str):
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail="River not found")
    results = get_results(river_id)
    rows = []
    for date, row in results["daily"].iterrows():
        rows.append({
            "date":       date.strftime("%Y-%m-%d"),
            "day":        date.strftime("%a %m/%d"),
            "peak_cfs":   int(row["predicted_cfs_max"]),
            "mean_cfs":   int(row["predicted_cfs_mean"]),
            "precip_in":  round(float(row["total_precip_mm"]) / 25.4, 2),
            "status":     row["status"],
            "paddable":   bool(row["paddable"]),
            "sweet_spot": bool(row["sweet_spot"]),
        })
    return rows


@app.get("/rivers/{river_id}/forecast/hourly")
def get_hourly(river_id: str):
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail="River not found")
    river = RIVERS[river_id]
    results = get_results(river_id)
    gauge = results["gauge_hist"]
    cutoff = gauge.index.max() - timedelta(days=7)
    col = river.target_param  # "cfs" or "stage"
    if river.target_param == "stage":
        history = [
            {"time": ts.isoformat(), "cfs": round(stage_to_visual(float(v), river), 2)}
            for ts, v in gauge.loc[gauge.index >= cutoff, col].dropna().items()
        ]
    else:
        history = [
            {"time": ts.isoformat(), "cfs": round(float(v))}
            for ts, v in gauge.loc[gauge.index >= cutoff, col].dropna().items()
        ]
    forecast = [
        {"time": ts.isoformat(), "cfs": round(float(row["predicted_cfs"]), 2)}
        for ts, row in results["hourly"].iterrows()
    ]
    return {"history": history, "forecast": forecast}


@app.get("/rivers/{river_id}/chart", response_class=HTMLResponse)
def get_chart(river_id: str):
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail="River not found")
    results = get_results(river_id)
    fig = build_figure(results)
    return fig.to_html(
        include_plotlyjs="cdn",
        full_html=True,
        config={"scrollZoom": True, "displayModeBar": False, "responsive": True},
    )


@app.get("/rivers/{river_id}/performance")
def get_performance(river_id: str):
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail="River not found")

    river = RIVERS[river_id]
    results = get_results(river_id)
    comp = results["holdout_comparison"].copy()
    metrics = results["metrics"]

    # Relative accuracy: 1 - |error| / actual, floored so low-flow noise doesn't dominate
    actual_floor = max(float(comp["actual_cfs"].quantile(0.1)), 0.01)
    comp["accuracy_pct"] = (
        (1 - comp["error_cfs"].abs() / comp["actual_cfs"].clip(lower=actual_floor))
        .clip(0, 1) * 100
    )

    holdout_start = comp.index.min()
    comp["hour_offset"] = (
        (comp.index - holdout_start).total_seconds() / 3600
    ).round().astype(int)

    # 6-hour rolling mean to smooth spike events
    hourly_acc = comp.groupby("hour_offset")["accuracy_pct"].mean()
    rolling_acc = hourly_acc.rolling(6, min_periods=1).mean()

    # Consecutive hours from hour 0 where rolling accuracy >= 90%
    accuracy_90h = 0
    for h, val in rolling_acc.items():
        if val >= 90.0:
            accuracy_90h = int(h) + 1
        else:
            break

    comp["day"] = (comp["hour_offset"] // 24) + 1
    daily_acc = (
        comp.groupby("day")["accuracy_pct"]
        .mean().round(1)
        .reset_index()
        .to_dict(orient="records")
    )

    return {
        "river_id":             river_id,
        "river_name":           river.name,
        "display_unit":         river.display_unit,
        "accuracy_90h":         accuracy_90h,
        "overall_accuracy_pct": round(float(comp["accuracy_pct"].mean()), 1),
        "r2":                   round(float(metrics["r2"]), 3),
        "mae":                  round(float(metrics["mae_cfs"]), 1),
        "holdout_days":         int(metrics["holdout_days"]),
        "daily_accuracy":       daily_acc,
    }


@app.post("/rivers/{river_id}/refresh")
def refresh(river_id: str):
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail="River not found")
    get_results(river_id, force=True)
    return {"refreshed_at": _caches[river_id]["updated_at"].isoformat()}


# ---------------------------------------------------------------------------
# Push endpoint — local machine computes predictions and pushes here
# ---------------------------------------------------------------------------

class PushPayload(BaseModel):
    current_cfs:        float
    metrics:            dict
    daily:              str   # DataFrame as JSON (orient='split')
    hourly:             str
    gauge_hist:         str   # trimmed to last 7 days
    holdout_comparison: str


@app.post("/rivers/{river_id}/push")
def push_results(
    river_id: str,
    payload: PushPayload,
    x_push_key: str = Header(None),
):
    push_key = os.environ.get("PUSH_KEY")
    if push_key and x_push_key != push_key:
        raise HTTPException(status_code=401, detail="Invalid push key")
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail="River not found")

    def load_df(json_str: str) -> pd.DataFrame:
        from io import StringIO
        df = pd.read_json(StringIO(json_str), orient="split")
        df.index = pd.to_datetime(df.index)
        return df

    _caches[river_id]["results"] = {
        "current_cfs":        payload.current_cfs,
        "metrics":            payload.metrics,
        "daily":              load_df(payload.daily),
        "hourly":             load_df(payload.hourly),
        "gauge_hist":         load_df(payload.gauge_hist),
        "holdout_comparison": load_df(payload.holdout_comparison),
    }
    _caches[river_id]["updated_at"] = datetime.now()
    return {"status": "ok", "river_id": river_id,
            "updated_at": _caches[river_id]["updated_at"].isoformat()}


# ---------------------------------------------------------------------------
# River requests
# ---------------------------------------------------------------------------

class RiverRequest(BaseModel):
    river_name: str
    location: str = ""
    gauge_id: str = ""
    notes: str = ""


@app.post("/river-requests", status_code=201)
def submit_river_request(req: RiverRequest):
    if not req.river_name.strip():
        raise HTTPException(status_code=422, detail="river_name is required")
    entry = {
        "river_name": req.river_name.strip(),
        "location":   req.location.strip(),
        "gauge_id":   req.gauge_id.strip(),
        "notes":      req.notes.strip(),
        "submitted_at": datetime.now().isoformat(),
    }
    existing = []
    if RIVER_REQUESTS_FILE.exists():
        existing = json.loads(RIVER_REQUESTS_FILE.read_text())
    existing.append(entry)
    RIVER_REQUESTS_FILE.write_text(json.dumps(existing, indent=2))
    return {"status": "received", "river_name": entry["river_name"]}


@app.get("/river-requests")
def list_river_requests():
    if not RIVER_REQUESTS_FILE.exists():
        return []
    return json.loads(RIVER_REQUESTS_FILE.read_text())


# ---------------------------------------------------------------------------
# Legacy Tellico shortcuts (keeps old app working during transition)
# ---------------------------------------------------------------------------

@app.get("/status")
def legacy_status():
    return get_status("tellico")

@app.get("/forecast/daily")
def legacy_daily():
    return get_daily("tellico")

@app.get("/forecast/hourly")
def legacy_hourly():
    return get_hourly("tellico")

@app.post("/refresh")
def legacy_refresh():
    return refresh("tellico")
