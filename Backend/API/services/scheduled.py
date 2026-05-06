"""
Synthesizes a `results` dict for dam-controlled (scheduled) rivers, matching
the same shape that `ML.predictor.run_prediction` returns for gauge rivers.

This lets every downstream formatter / route stay agnostic of river kind.
"""

from datetime import datetime, timedelta

import pandas as pd

from ML.rivers import ReleaseWindow, RiverConfig


# ---------------------------------------------------------------------------
# Local-time helpers
# ---------------------------------------------------------------------------

# All Ocoee schedules are published in local (Eastern) time. We compare against
# the host clock — fine for a server in the same timezone. If the server clock
# moves, set TZ=America/New_York in the container env.

def _now() -> datetime:
    return datetime.now()


def _is_active(window: ReleaseWindow, t: datetime) -> bool:
    return (
        t.date() == window.day
        and window.start_hour <= t.hour < window.end_hour
    )


def _window_for(river: RiverConfig, t: datetime) -> ReleaseWindow | None:
    for w in river.release_windows:
        if _is_active(w, t):
            return w
    return None


# ---------------------------------------------------------------------------
# Per-shape synthesis
# ---------------------------------------------------------------------------

def _current_cfs(river: RiverConfig, t: datetime) -> float:
    return float(river.release_cfs) if _window_for(river, t) else 0.0


def _hourly_forecast(river: RiverConfig, t: datetime, days: int = 7) -> pd.DataFrame:
    """One row per hour for the next `days` days. cfs = release_cfs during a window, else 0."""
    start = t.replace(minute=0, second=0, microsecond=0)
    rows = []
    for i in range(days * 24):
        ts = start + timedelta(hours=i)
        cfs = float(river.release_cfs) if _window_for(river, ts) else 0.0
        rows.append({"predicted_cfs": cfs})
    idx = pd.date_range(start, periods=len(rows), freq="h")
    return pd.DataFrame(rows, index=idx)


def _gauge_history(river: RiverConfig, t: datetime, days: int = 7) -> pd.DataFrame:
    """Synthetic history mirrors the schedule for the past `days` so the chart isn't blank."""
    start = (t - timedelta(days=days)).replace(minute=0, second=0, microsecond=0)
    rows = []
    for i in range(days * 24):
        ts = start + timedelta(hours=i)
        cfs = float(river.release_cfs) if _window_for(river, ts) else 0.0
        rows.append({"cfs": cfs, "stage": cfs})
    idx = pd.date_range(start, periods=len(rows), freq="h")
    return pd.DataFrame(rows, index=idx)


def _daily_forecast(river: RiverConfig, t: datetime, days: int = 7) -> pd.DataFrame:
    """One row per upcoming day. peak_cfs = release flow on release days, 0 otherwise."""
    rows = []
    idx = []
    today = t.date()
    for i in range(days):
        d = today + timedelta(days=i)
        # All windows that fall on this date
        windows = [w for w in river.release_windows if w.day == d]
        is_release = bool(windows)
        peak = float(river.release_cfs) if is_release else 0.0
        # Mean over the day = release_cfs * (release_hours / 24)
        release_hours = sum(w.end_hour - w.start_hour for w in windows)
        mean = peak * release_hours / 24 if is_release else 0.0

        if is_release:
            status = "SWEET SPOT" if river.sweet_spot_min <= peak <= river.sweet_spot_max else "RUNNABLE"
            paddable = river.runnable_min <= peak <= river.runnable_max
            sweet = river.sweet_spot_min <= peak <= river.sweet_spot_max
        else:
            status = "TOO LOW"
            paddable = False
            sweet = False

        rows.append({
            "predicted_cfs_max":  peak,
            "predicted_cfs_mean": mean,
            "total_precip_mm":    0.0,
            "status":             status,
            "paddable":           paddable,
            "sweet_spot":         sweet,
        })
        idx.append(pd.Timestamp(d))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def synthesize_results(river: RiverConfig) -> dict:
    """
    Build the same results dict as `ML.predictor.run_prediction` so the rest
    of the API code path doesn't need to know this is a scheduled river.
    """
    t = _now()
    return {
        "current_cfs":         _current_cfs(river, t),
        "hourly":              _hourly_forecast(river, t),
        "gauge_hist":          _gauge_history(river, t),
        "daily":               _daily_forecast(river, t),
        # `holdout_comparison` and `metrics` are predictor-only — formatters
        # for /performance must check kind and skip these.
        "holdout_comparison":  None,
        "metrics":             None,
    }
