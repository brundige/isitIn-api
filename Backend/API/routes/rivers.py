"""River endpoints — index, status, forecasts, performance, refresh, push."""

import os
from io import StringIO

import pandas as pd
from fastapi import APIRouter, Header, HTTPException

from Backend.API.schemas import (
    DayForecast,
    HourlyForecast,
    Performance,
    PushPayload,
    RiverSummary,
    Status,
)
from Backend.API.services import formatters
from Backend.API.services.predictions import get_results, get_updated_at, set_results
from ML.rivers import RIVERS

router = APIRouter(prefix="/rivers", tags=["rivers"])


@router.get("", response_model=list[RiverSummary])
def list_rivers():
    out = []
    for river_id, river in RIVERS.items():
        try:
            results = get_results(river_id)
            out.append(formatters.to_river_summary(
                river_id, river, results, get_updated_at(river_id)
            ))
        except Exception as e:
            print(f"  /rivers: {river_id} failed: {e}")
            out.append(formatters.river_summary_error(river_id, river))
    return out


def _require(river_id: str):
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail="River not found")
    return RIVERS[river_id]


@router.get("/{river_id}/status", response_model=Status)
def get_status(river_id: str):
    river = _require(river_id)
    return formatters.to_status(river, get_results(river_id), get_updated_at(river_id))


@router.get("/{river_id}/forecast/daily", response_model=list[DayForecast])
def get_daily(river_id: str):
    _require(river_id)
    return formatters.to_daily_forecast(get_results(river_id))


@router.get("/{river_id}/forecast/hourly", response_model=HourlyForecast)
def get_hourly(river_id: str):
    river = _require(river_id)
    return formatters.to_hourly_forecast(river, get_results(river_id))


@router.get("/{river_id}/performance", response_model=Performance)
def get_performance(river_id: str):
    river = _require(river_id)
    if river.kind == "scheduled":
        # Scheduled rivers have no ML model to evaluate. Frontend already
        # treats a non-200 response here as "no card to show".
        raise HTTPException(status_code=404, detail="No performance data for scheduled rivers")
    return formatters.to_performance(river_id, river, get_results(river_id))


@router.post("/{river_id}/refresh")
def refresh(river_id: str):
    _require(river_id)
    get_results(river_id, force=True)
    return {"refreshed_at": get_updated_at(river_id).isoformat()}


@router.post("/{river_id}/push")
def push_results(
    river_id: str,
    payload: PushPayload,
    x_push_key: str = Header(None),
):
    push_key = os.environ.get("PUSH_KEY")
    if push_key and x_push_key != push_key:
        raise HTTPException(status_code=401, detail="Invalid push key")

    river = _require(river_id)
    if river.kind == "scheduled":
        raise HTTPException(
            status_code=400,
            detail="Scheduled rivers are synthesized server-side and don't accept pushes",
        )

    def load_df(json_str: str) -> pd.DataFrame:
        df = pd.read_json(StringIO(json_str), orient="split")
        df.index = pd.to_datetime(df.index)
        return df

    updated_at = set_results(river_id, {
        "current_cfs":        payload.current_cfs,
        "metrics":            payload.metrics,
        "daily":              load_df(payload.daily),
        "hourly":             load_df(payload.hourly),
        "gauge_hist":         load_df(payload.gauge_hist),
        "holdout_comparison": load_df(payload.holdout_comparison),
    })
    return {"status": "ok", "river_id": river_id, "updated_at": updated_at.isoformat()}
