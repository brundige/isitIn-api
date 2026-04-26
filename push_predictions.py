#!/usr/bin/env python3
"""
Run predictions locally and push results to the Render API.

Cron (every 4 hours):
    0 */4 * * * cd /Users/chrisbrundige/PycharmProjects/isItIn && python push_predictions.py >> /tmp/isitIn_push.log 2>&1
"""
import os
import json
from datetime import datetime, timedelta

import numpy as np
import requests

from rivers import RIVERS
from tellico_predictor import run_prediction

API_BASE = os.environ.get("RENDER_API", "https://isitin-api.onrender.com")
PUSH_KEY = os.environ.get("PUSH_KEY", "")


def to_json(df):
    """Serialize a DataFrame with DatetimeIndex to a JSON string."""
    d = df.copy()
    d.index = d.index.astype(str)
    return d.to_json(orient="split")


def sanitize(obj):
    """Recursively convert numpy scalars to plain Python types."""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj


def push_river(river_id: str):
    river = RIVERS[river_id]
    print(f"[{datetime.now():%H:%M:%S}] Running prediction for {river.name}...")

    results = run_prediction(river=river, verbose=False)

    # Trim gauge history to the last 7 days — that's all the API needs to serve the chart
    gauge = results["gauge_hist"]
    gauge_trimmed = gauge[gauge.index >= gauge.index.max() - timedelta(days=7)]

    payload = {
        "current_cfs":        float(results["current_cfs"]),
        "metrics":            sanitize(results["metrics"]),
        "daily":              to_json(results["daily"]),
        "hourly":             to_json(results["hourly"]),
        "gauge_hist":         to_json(gauge_trimmed),
        "holdout_comparison": to_json(results["holdout_comparison"]),
    }

    resp = requests.post(
        f"{API_BASE}/rivers/{river_id}/push",
        json=payload,
        headers={"X-Push-Key": PUSH_KEY},
        timeout=60,
    )
    resp.raise_for_status()
    print(f"[{datetime.now():%H:%M:%S}] ✓ Pushed {river.name}")


if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"Push run started at {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"Target: {API_BASE}")
    print(f"{'='*50}")
    for river_id in RIVERS:
        try:
            push_river(river_id)
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] ✗ Failed {river_id}: {e}")
    print(f"Done at {datetime.now():%H:%M:%S}\n")
