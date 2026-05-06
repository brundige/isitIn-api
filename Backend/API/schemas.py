"""
Pydantic models — the API contract derived from the React Native frontend.

Every shape here corresponds to a TypeScript interface in Frontend/src/.
Field names are normalised on `runnable_*` (replacing the old mixed
`runnable_*` / `paddable_*` split that used to exist in /rivers vs /status).
"""

from pydantic import BaseModel


class Range(BaseModel):
    runnable_min: float
    runnable_max: float
    sweet_min: float
    sweet_max: float


class RiverSummary(BaseModel):
    id: str
    name: str
    current_cfs: float
    status: str
    runnable: bool
    sweet_spot: bool
    updated_at: str
    range: Range


class Status(BaseModel):
    river: str
    current_cfs: float
    display_unit: str
    status: str
    runnable: bool
    sweet_spot: bool
    updated_at: str
    range: Range


class DayForecast(BaseModel):
    date: str
    day: str
    peak_cfs: int
    mean_cfs: int
    precip_in: float
    status: str
    runnable: bool
    sweet_spot: bool


class TimePoint(BaseModel):
    time: str
    cfs: float


class HourlyForecast(BaseModel):
    history: list[TimePoint]
    forecast: list[TimePoint]


class DailyAccuracy(BaseModel):
    day: int
    accuracy_pct: float


class Performance(BaseModel):
    river_id: str
    river_name: str
    display_unit: str
    accuracy_90h: int
    overall_accuracy_pct: float
    r2: float
    mae: float
    holdout_days: int
    daily_accuracy: list[DailyAccuracy]


class RiverRequestPayload(BaseModel):
    river_name: str
    location: str = ""
    gauge_id: str = ""
    notes: str = ""


class PushPayload(BaseModel):
    current_cfs:        float
    metrics:            dict
    daily:              str   # DataFrame as JSON (orient='split')
    hourly:             str
    gauge_hist:         str   # trimmed to last 7 days
    holdout_comparison: str
