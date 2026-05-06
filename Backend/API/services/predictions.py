"""
Per-river prediction cache.

Wraps `ML.predictor.run_prediction` with a 1-hour in-memory cache so the
expensive feature-engineering + autoregressive rollout doesn't run on every
HTTP request.
"""

from datetime import datetime, timedelta

from fastapi import HTTPException

from Backend.API.config import CACHE_TTL_MINUTES
from Backend.API.services.scheduled import synthesize_results
from ML.predictor import run_prediction
from ML.rivers import RIVERS

# Scheduled rivers re-synthesize on every call (cheap), but we still keep their
# updated_at fresh in the cache so /rivers can show a sensible timestamp.
_SCHEDULED_TTL_MINUTES = 1

_caches: dict[str, dict] = {
    river_id: {"results": None, "updated_at": None}
    for river_id in RIVERS
}


def get_results(river_id: str, force: bool = False) -> dict:
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail=f"River '{river_id}' not found")

    cache = _caches[river_id]
    river = RIVERS[river_id]
    now = datetime.now()
    ttl = _SCHEDULED_TTL_MINUTES if river.kind == "scheduled" else CACHE_TTL_MINUTES
    stale = (
        cache["results"] is None
        or cache["updated_at"] is None
        or (now - cache["updated_at"]) > timedelta(minutes=ttl)
    )
    if force or stale:
        if river.kind == "scheduled":
            cache["results"] = synthesize_results(river)
        else:
            print(f"[{now:%H:%M:%S}] Running prediction for {river.name}...")
            cache["results"] = run_prediction(river=river, verbose=False)
            print(f"[{datetime.now():%H:%M:%S}] Done — {river.name}")
        cache["updated_at"] = datetime.now()
    return cache["results"]


def get_updated_at(river_id: str) -> datetime:
    return _caches[river_id]["updated_at"]


def set_results(river_id: str, results: dict) -> datetime:
    if river_id not in RIVERS:
        raise HTTPException(status_code=404, detail=f"River '{river_id}' not found")
    now = datetime.now()
    _caches[river_id]["results"] = results
    _caches[river_id]["updated_at"] = now
    return now


def warmup() -> None:
    for river_id in RIVERS:
        try:
            get_results(river_id)
        except Exception as e:
            print(f"Warning: could not warm up {river_id}: {e}")
