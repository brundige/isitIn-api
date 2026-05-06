"""
DataFrame → API-response shape mapping.

Each `to_*` function takes the raw `run_prediction` result dict and emits a
plain-dict shape that matches the matching Pydantic model in schemas.py.
"""

from datetime import datetime, timedelta

from ML.rivers import RiverConfig, stage_to_visual


def cfs_status(cfs: float, river: RiverConfig) -> str:
    if cfs < river.runnable_min:
        return "TOO LOW"
    if cfs > river.runnable_max:
        return "TOO HIGH"
    if river.sweet_spot_min <= cfs <= river.sweet_spot_max:
        return "SWEET SPOT"
    return "RUNNABLE"


def _range_dict(river: RiverConfig) -> dict:
    return {
        "runnable_min": river.runnable_min,
        "runnable_max": river.runnable_max,
        "sweet_min":    river.sweet_spot_min,
        "sweet_max":    river.sweet_spot_max,
    }


def to_river_summary(river_id: str, river: RiverConfig, results: dict, updated_at: datetime) -> dict:
    cfs = float(results["current_cfs"])
    return {
        "id":          river_id,
        "name":        river.name,
        "current_cfs": round(cfs),
        "status":      cfs_status(cfs, river),
        "runnable":    river.runnable_min <= cfs <= river.runnable_max,
        "sweet_spot":  river.sweet_spot_min <= cfs <= river.sweet_spot_max,
        "updated_at":  updated_at.isoformat(),
        "range":       _range_dict(river),
    }


def river_summary_error(river_id: str, river: RiverConfig) -> dict:
    return {
        "id": river_id,
        "name": river.name,
        "current_cfs": 0,
        "status": "UNKNOWN",
        "runnable": False,
        "sweet_spot": False,
        "updated_at": datetime.now().isoformat(),
        "range": _range_dict(river),
    }


def to_status(river: RiverConfig, results: dict, updated_at: datetime) -> dict:
    cfs = float(results["current_cfs"])
    return {
        "river":        river.name,
        "current_cfs":  round(cfs, 2),
        "display_unit": river.display_unit,
        "status":       cfs_status(cfs, river),
        "runnable":     river.runnable_min <= cfs <= river.runnable_max,
        "sweet_spot":   river.sweet_spot_min <= cfs <= river.sweet_spot_max,
        "updated_at":   updated_at.isoformat(),
        "range":        _range_dict(river),
    }


def to_daily_forecast(results: dict) -> list[dict]:
    rows = []
    for date, row in results["daily"].iterrows():
        rows.append({
            "date":       date.strftime("%Y-%m-%d"),
            "day":        date.strftime("%a %m/%d"),
            "peak_cfs":   int(row["predicted_cfs_max"]),
            "mean_cfs":   int(row["predicted_cfs_mean"]),
            "precip_in":  round(float(row["total_precip_mm"]) / 25.4, 2),
            "status":     row["status"],
            "runnable":   bool(row["paddable"]),
            "sweet_spot": bool(row["sweet_spot"]),
        })
    return rows


def to_hourly_forecast(river: RiverConfig, results: dict) -> dict:
    gauge = results["gauge_hist"]
    cutoff = gauge.index.max() - timedelta(days=7)
    col = river.target_param  # "cfs" or "stage"
    if col == "stage":
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


def to_performance(river_id: str, river: RiverConfig, results: dict) -> dict:
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
