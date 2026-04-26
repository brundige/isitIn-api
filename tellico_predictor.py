"""
Tellico River Paddability Predictor
====================================
Uses USGS gauge data and Open-Meteo precipitation (historical + forecast)
to build a lag regression model predicting CFS given rainfall.

Gauge: USGS 03507000 - Tellico River near Tellico Plains, TN
"""

import os
import joblib
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from sklearn.metrics import mean_absolute_error, r2_score
import lightgbm as lgb
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

USGS_GAUGE_ID = "03518500"  # Tellico River at Tellico Plains, TN
WATERSHED_LAT = 35.37  # Approximate watershed centroid
WATERSHED_LON = -84.28

# Paddable ranges in CFS
PADDABLE_MIN_CFS = 300
PADDABLE_MAX_CFS = 1000  # Above this is flood/dangerous
SWEET_SPOT_MIN = 500
SWEET_SPOT_MAX = 600

HISTORY_DAYS = 365 * 2  # 2 years of training data

PREDICT_AHEAD_H = 2  # predict CFS this many hours ahead

# Leaky-bucket soil moisture: SM[t] = α×SM[t-1] + precip[t], α = exp(-1/τ)
SOIL_MOISTURE_TAU = 168  # hours (1 week memory)

# Rolling precip windows (hours) used as features
PRECIP_LAG_WINDOWS = [6, 12, 24, 48, 72]
ANTECEDENT_WINDOWS = [7 * 24, 14 * 24]  # 7-day, 14-day soil saturation

# Data cache — avoids hammering USGS / Open-Meteo on every run
CACHE_DIR = "cache"
GAUGE_CACHE = os.path.join(CACHE_DIR, "gauge.parquet")
PRECIP_CACHE = os.path.join(CACHE_DIR, "precip.parquet")
CACHE_MAX_AGE_HOURS = 1   # refetch if cache is older than this

# Minimum predicted CFS — prevents autoregressive collapse during dry forecasts
BASEFLOW_MIN_CFS = 30.0  # Tellico typical low-flow floor


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_usgs_gauge(gauge_id: str, start: datetime, end: datetime,
                     param: str = "00060") -> pd.DataFrame:
    """
    Fetch instantaneous values from USGS NWIS IV service.
    param="00060" → discharge (CFS), column named "cfs"
    param="00065" → gage height (ft), column named "stage"
    """
    col_name = "cfs" if param == "00060" else "stage"
    url = "https://waterservices.usgs.gov/nwis/iv/"
    params = {
        "sites": gauge_id,
        "parameterCd": param,
        "startDT": start.strftime("%Y-%m-%d"),
        "endDT": end.strftime("%Y-%m-%d"),
        "format": "json",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    series = data["value"]["timeSeries"]
    if not series:
        raise ValueError(f"No data found for gauge {gauge_id} param {param}")

    values = series[0]["values"][0]["value"]
    records = []
    for v in values:
        try:
            val = float(v["value"])
            if val >= 0:
                records.append({"time": pd.to_datetime(v["dateTime"], utc=True), col_name: val})
        except (ValueError, KeyError):
            continue

    df = pd.DataFrame(records).set_index("time").sort_index()
    df.index = df.index.tz_convert("America/New_York")
    df = df.resample("1h").mean().interpolate(limit=3)
    return df


def fetch_precip_history(lat: float, lon: float, start: datetime, end: datetime) -> pd.DataFrame:
    """
    Fetch hourly precipitation from Open-Meteo ERA5 archive.
    Returns a DataFrame with DatetimeIndex and 'precip_mm' column.
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "hourly": "precipitation",
        "timezone": "America/New_York",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    times = pd.to_datetime(data["hourly"]["time"])
    precip = data["hourly"]["precipitation"]
    df = pd.DataFrame({"precip_mm": precip}, index=times)
    df.index = df.index.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    df = df[df.index.notna()].sort_index()
    return df


def fetch_precip_forecast(lat: float, lon: float, days: int = 7) -> pd.DataFrame:
    """
    Fetch hourly precipitation forecast from Open-Meteo (free, 7-day).
    Returns a DataFrame with DatetimeIndex and 'precip_mm' column.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "precipitation",
        "forecast_days": days,
        "timezone": "America/New_York",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    times = pd.to_datetime(data["hourly"]["time"])
    precip = data["hourly"]["precipitation"]
    df = pd.DataFrame({"precip_mm": precip}, index=times)
    df.index = df.index.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    df = df[df.index.notna()].sort_index()
    return df


# ---------------------------------------------------------------------------
# Data cache
# ---------------------------------------------------------------------------

def _cache_is_fresh(path: str) -> bool:
    if not os.path.exists(path):
        return False
    age_h = (datetime.now().timestamp() - os.path.getmtime(path)) / 3600
    return age_h < CACHE_MAX_AGE_HOURS


def load_or_fetch_gauge(gauge_id: str, start: datetime, end: datetime,
                        verbose: bool = True,
                        cache_path: str = GAUGE_CACHE,
                        param: str = "00060") -> pd.DataFrame:
    if _cache_is_fresh(cache_path):
        if verbose:
            age_h = (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 3600
            print(f"  Gauge: loaded from cache (age {age_h:.1f}h)")
        return pd.read_parquet(cache_path)
    if verbose:
        print(f"  Gauge: fetching from USGS API (param {param})...")
    df = fetch_usgs_gauge(gauge_id, start, end, param=param)
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_parquet(cache_path)
    return df


def load_or_fetch_precip(lat: float, lon: float, start: datetime, end: datetime,
                         verbose: bool = True,
                         cache_path: str = PRECIP_CACHE) -> pd.DataFrame:
    if _cache_is_fresh(cache_path):
        if verbose:
            age_h = (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 3600
            print(f"  Precip: loaded from cache (age {age_h:.1f}h)")
        return pd.read_parquet(cache_path)
    if verbose:
        print(f"  Precip: fetching from Open-Meteo API...")
    df = fetch_precip_history(lat, lon, start, end)
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_parquet(cache_path)
    return df


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

HOLDOUT_DAYS = 5  # Last N days reserved for backtesting, excluded from training


def _compute_features(combined: pd.DataFrame, value_col: str = "cfs") -> pd.DataFrame:
    """
    Build the flat feature matrix from an aligned gauge+precip DataFrame.
    value_col: "cfs" for discharge rivers, "stage" for gage-height rivers.
    """
    combined = combined.copy()
    combined["precip_mm"] = combined["precip_mm"].fillna(0)

    # Short-term rolling precip
    for h in PRECIP_LAG_WINDOWS:
        combined[f"precip_{h}h"] = (
            combined["precip_mm"].rolling(h, min_periods=max(1, h // 4)).sum()
        )

    # Antecedent moisture (longer windows)
    for h in ANTECEDENT_WINDOWS:
        combined[f"antecedent_{h}h"] = (
            combined["precip_mm"].rolling(h, min_periods=h // 4).sum()
        )

    # Rain on saturated ground amplifier
    combined["wet_amplifier"] = combined["precip_24h"] * combined["antecedent_168h"]

    # Exponentially weighted recent rain
    combined["precip_ewm"] = combined["precip_mm"].ewm(halflife=6, min_periods=1).mean() * 24

    # Leaky-bucket soil moisture — runs over FULL history for long memory
    α = np.exp(-1.0 / SOIL_MOISTURE_TAU)
    sm = np.zeros(len(combined))
    p = combined["precip_mm"].values
    for i in range(1, len(sm)):
        sm[i] = α * sm[i - 1] + p[i]
    combined["soil_moisture"] = sm

    # Current and lagged log(value) — persistence features
    log_col = f"log_{value_col}"
    combined[log_col] = np.log1p(combined[value_col])
    for lag in [1, 2, 6, 12, 24]:
        combined[f"{log_col}_lag{lag}h"] = combined[log_col].shift(lag)

    # Time-of-day (cyclical)
    hour = combined.index.hour
    combined["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    combined["hour_cos"] = np.cos(2 * np.pi * hour / 24)

    return combined


def feature_columns(value_col: str = "cfs") -> list[str]:
    log_col = f"log_{value_col}"
    cols = [f"precip_{h}h" for h in PRECIP_LAG_WINDOWS]
    cols += [f"antecedent_{h}h" for h in ANTECEDENT_WINDOWS]
    cols += ["wet_amplifier", "precip_ewm", "soil_moisture"]
    cols += [log_col] + [f"{log_col}_lag{l}h" for l in [1, 2, 6, 12, 24]]
    cols += ["hour_sin", "hour_cos"]
    return cols


def build_features(gauge_df: pd.DataFrame, precip_df: pd.DataFrame,
                   value_col: str = "cfs") -> pd.DataFrame:
    """
    Returns a DataFrame with all feature columns + target column.
    Target is log1p(value_col shifted by PREDICT_AHEAD_H).
    """
    combined = gauge_df.join(precip_df, how="inner").sort_index()
    combined = _compute_features(combined, value_col=value_col)
    target_col = f"target_log_{value_col}"
    combined[target_col] = combined[f"log_{value_col}"].shift(-PREDICT_AHEAD_H)
    return combined.dropna()


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def _infer_value_col(features_df: pd.DataFrame) -> str:
    """Detect whether this features_df was built from CFS or stage data."""
    return "stage" if "log_stage" in features_df.columns else "cfs"


def train_model(features_df: pd.DataFrame, verbose: bool = True):
    """
    Train a LightGBM regressor on log1p(CFS).
    Uses Huber objective for robustness to peak outliers.
    Early stopping on the last 10% of training data.
    Returns (model, metrics_dict).
    """
    cutoff = features_df.index.max() - timedelta(days=HOLDOUT_DAYS)
    train_df = features_df[features_df.index <= cutoff]

    val_split = int(len(train_df) * 0.9)
    train_part = train_df.iloc[:val_split]
    val_part = train_df.iloc[val_split:]

    value_col  = _infer_value_col(features_df)
    feat_cols  = feature_columns(value_col)
    target_col = f"target_log_{value_col}"
    X_tr, y_tr = train_part[feat_cols], train_part[target_col]
    X_val, y_val = val_part[feat_cols], val_part[target_col]

    model = lgb.LGBMRegressor(
        objective="huber",
        alpha=0.5,
        n_estimators=3000,
        learning_rate=0.03,
        num_leaves=63,
        min_child_samples=30,
        subsample=0.8,
        colsample_bytree=0.8,
        n_jobs=-1,
        random_state=42,
        verbose=-1,
    )
    model.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=100 if verbose else 0),
        ],
    )

    if verbose:
        print(f"  Best iteration: {model.best_iteration_}  "
              f"| val loss: {model.best_score_['valid_0']['huber']:.4f}")

    return model, {"n_train": len(X_tr)}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_holdout(model: lgb.LGBMRegressor,
                     features_df: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """
    Predict over the held-out last HOLDOUT_DAYS using real observed features.
    Returns metrics and an hourly comparison DataFrame.
    """
    value_col  = _infer_value_col(features_df)
    feat_cols  = feature_columns(value_col)
    target_col = f"target_log_{value_col}"

    cutoff  = features_df.index.max() - timedelta(days=HOLDOUT_DAYS)
    test_df = features_df[features_df.index > cutoff]

    log_pred  = model.predict(test_df[feat_cols])
    y_pred    = np.expm1(log_pred)
    y_test    = np.expm1(test_df[target_col].values)

    comparison = pd.DataFrame({
        "actual_cfs":    y_test,
        "predicted_cfs": y_pred,
        "error_cfs":     y_pred - y_test,
    }, index=test_df.index)

    metrics = {
        "mae_cfs": mean_absolute_error(y_test, y_pred),
        "r2":      r2_score(y_test, y_pred),
        "n_test":  len(test_df),
        "holdout_days": HOLDOUT_DAYS,
    }
    return metrics, comparison


# ---------------------------------------------------------------------------
# Forecasting  (autoregressive hourly rollout)
# ---------------------------------------------------------------------------

def predict_forecast(
        model: lgb.LGBMRegressor,
        forecast_precip: pd.DataFrame,
        recent_gauge: pd.DataFrame,
        recent_precip: pd.DataFrame,
        baseflow_min: float = BASEFLOW_MIN_CFS,
) -> pd.DataFrame:
    """
    Roll predictions forward hour by hour.

    Precip features come from the precomputed rolling windows over the
    stitched history+forecast series.  CFS lag features use the most
    recent predicted (or observed) values.
    """
    # Need enough lookback for the longest window + SM warmup
    lookback_h = max(max(ANTECEDENT_WINDOWS), SOIL_MOISTURE_TAU * 5) + 24
    buf_start = forecast_precip.index[0] - timedelta(hours=int(lookback_h))

    hist_precip = recent_precip[recent_precip.index >= buf_start].copy()
    hist_gauge = recent_gauge[recent_gauge.index >= buf_start].copy()

    # Stitch historical + forecast precip and compute all rolling features
    full_precip = pd.concat([hist_precip, forecast_precip])
    full_precip = full_precip[~full_precip.index.duplicated(keep="last")].sort_index()

    # Detect whether this is a CFS or stage river from the gauge column names
    value_col = "stage" if "stage" in hist_gauge.columns else "cfs"
    log_col   = f"log_{value_col}"
    feat_cols = feature_columns(value_col)

    # Placeholder value column — filled in during rollout
    full_precip[value_col] = np.nan

    # Seed with historical observations
    for ts in hist_gauge.index:
        if ts in full_precip.index:
            full_precip.loc[ts, value_col] = hist_gauge.loc[ts, value_col]

    feat_frame = _compute_features(full_precip, value_col=value_col)

    # History dict for autoregressive lag lookups
    val_history: dict = {}
    for ts, row in hist_gauge.iterrows():
        val_history[ts] = float(row[value_col])

    def get_lag(ts, lag_h):
        target = ts - timedelta(hours=lag_h)
        candidates = {t: v for t, v in val_history.items() if t <= target}
        if candidates:
            return float(np.log1p(candidates[max(candidates)]))
        return float(np.log1p(baseflow_min))

    results = []
    for ts, row in feat_frame.loc[forecast_precip.index].iterrows():
        feats = row[feat_cols].copy()
        feats[log_col]              = get_lag(ts, 0)
        feats[f"{log_col}_lag1h"]  = get_lag(ts, 1)
        feats[f"{log_col}_lag2h"]  = get_lag(ts, 2)
        feats[f"{log_col}_lag6h"]  = get_lag(ts, 6)
        feats[f"{log_col}_lag12h"] = get_lag(ts, 12)
        feats[f"{log_col}_lag24h"] = get_lag(ts, 24)

        log_pred = float(model.predict(pd.DataFrame([feats])[feat_cols])[0])
        val_pred = float(max(np.expm1(log_pred), baseflow_min))

        val_history[ts] = val_pred
        results.append({"time": ts, "predicted_cfs": val_pred,
                        "precip_mm": float(row["precip_mm"])})

    return pd.DataFrame(results).set_index("time")


def daily_summary(
        hourly_forecast: pd.DataFrame,
        runnable_min: int = PADDABLE_MIN_CFS,
        runnable_max: int = PADDABLE_MAX_CFS,
        sweet_spot_min: int = SWEET_SPOT_MIN,
        sweet_spot_max: int = SWEET_SPOT_MAX,
) -> pd.DataFrame:
    """Aggregate hourly predictions into daily summary."""
    df = hourly_forecast.copy()
    daily = df.resample("1D").agg(
        predicted_cfs_max=("predicted_cfs", "max"),
        predicted_cfs_mean=("predicted_cfs", "mean"),
        total_precip_mm=("precip_mm", "sum"),
    ).round(1)

    daily["paddable"] = (
            (daily["predicted_cfs_max"] >= runnable_min) &
            (daily["predicted_cfs_max"] <= runnable_max)
    )
    daily["sweet_spot"] = (
            (daily["predicted_cfs_max"] >= sweet_spot_min) &
            (daily["predicted_cfs_max"] <= sweet_spot_max)
    )
    daily["status"] = daily.apply(
        lambda row: _row_status(row, runnable_min, runnable_max), axis=1
    )
    return daily


def _row_status(row, runnable_min: int, runnable_max: int) -> str:
    cfs = row["predicted_cfs_max"]
    if cfs < runnable_min:
        return "TOO LOW"
    elif cfs > runnable_max:
        return "TOO HIGH"
    elif row["sweet_spot"]:
        return "SWEET SPOT"
    else:
        return "RUNNABLE"


# ---------------------------------------------------------------------------
# Model persistence
# ---------------------------------------------------------------------------

MODEL_PATH = "tellico_model.joblib"


def save_model(model: lgb.LGBMRegressor, path: str = MODEL_PATH):
    joblib.dump(model, path)
    print(f"  Model saved → {path}")


def load_model(path: str = MODEL_PATH):
    if not os.path.exists(path):
        return None
    return joblib.load(path)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_prediction(retrain: bool = False, verbose: bool = True, plot: bool = False,
                   river=None) -> dict:
    """
    Full pipeline: fetch data, train (or load) model, predict forecast.

    Parameters
    ----------
    river : RiverConfig, optional
        River configuration. Defaults to Tellico River for backward compatibility.
    retrain : bool
        Force retraining even if a saved model exists.
    """
    # Default to Tellico for backward compat
    if river is None:
        from rivers import RIVERS
        river = RIVERS["tellico"]

    from rivers import stage_to_visual

    gauge_id       = river.gauge_id
    watershed_lat  = river.watershed_lat
    watershed_lon  = river.watershed_lon
    runnable_min   = river.runnable_min
    runnable_max   = river.runnable_max
    sweet_min      = river.sweet_spot_min
    sweet_max      = river.sweet_spot_max
    baseflow_min   = river.baseflow_min
    value_col      = river.target_param   # "cfs" or "stage"
    model_path     = f"{river.id}_model.joblib"
    gauge_cache    = os.path.join(CACHE_DIR, f"{river.id}_gauge.parquet")
    precip_cache   = os.path.join(CACHE_DIR, f"{river.id}_precip.parquet")
    usgs_param     = "00065" if value_col == "stage" else "00060"

    now = datetime.now()
    history_start = now - timedelta(days=HISTORY_DAYS)

    if verbose:
        print(f"{river.name} Predictor")
        print(f"Gauge: USGS {gauge_id}")
        print(f"{'=' * 60}")

    saved = None if retrain else load_model(model_path)

    if verbose:
        print(f"Loading {HISTORY_DAYS}-day gauge history...")
    gauge_hist = load_or_fetch_gauge(
        gauge_id, history_start, now, verbose=verbose,
        cache_path=gauge_cache, param=usgs_param,
    )
    if verbose:
        print(f"    {len(gauge_hist):,} hourly readings "
              f"({gauge_hist.index[0].date()} to {gauge_hist.index[-1].date()})  "
              f"| current: {gauge_hist['cfs'].iloc[-1]:.0f} CFS")

    if verbose:
        print(f"Loading precipitation history...")
    precip_hist = load_or_fetch_precip(
        watershed_lat, watershed_lon, history_start, now,
        verbose=verbose, cache_path=precip_cache
    )
    if verbose:
        total_precip = precip_hist["precip_mm"].sum() / 25.4
        print(f"    {len(precip_hist):,} hourly readings  |  total: {total_precip:.1f} in")

    if verbose:
        print(f"Building features ({len(feature_columns())} features per timestep)...")
    features_df = build_features(gauge_hist, precip_hist, value_col=value_col)
    if verbose:
        print(f"  {len(features_df):,} training rows")

    if saved:
        model = saved
        if verbose:
            print(f"  Loaded saved model from {model_path}")
        train_metrics = {"n_train": 0}
    else:
        if verbose:
            print(f"Training LightGBM...")
        model, train_metrics = train_model(features_df, verbose=verbose)
        save_model(model, model_path)

    holdout_metrics, holdout_comparison = evaluate_holdout(model, features_df)
    metrics = {**train_metrics, **holdout_metrics}
    if verbose:
        print(f"  Backtest R²: {metrics['r2']:.3f} | "
              f"MAE: {metrics['mae_cfs']:.0f} CFS | "
              f"Holdout samples: {metrics['n_test']:,}")

    if verbose:
        print(f"Fetching 7-day precipitation forecast...")
    forecast_precip = fetch_precip_forecast(watershed_lat, watershed_lon, days=7)
    total_forecast_in = forecast_precip["precip_mm"].sum() / 25.4
    if verbose:
        print(f"  Forecast total: {total_forecast_in:.2f} inches over 7 days")

    if verbose:
        print(f"Generating river level predictions...\n")
    hourly_pred = predict_forecast(
        model, forecast_precip, gauge_hist, precip_hist, baseflow_min=baseflow_min
    )

    # For stage rivers, convert predicted stage → visual gauge for display
    if value_col == "stage":
        hourly_pred["predicted_cfs"] = hourly_pred["predicted_cfs"].apply(
            lambda s: stage_to_visual(s, river)
        )
        current_display = stage_to_visual(float(gauge_hist[value_col].iloc[-1]), river)
    else:
        current_display = float(gauge_hist[value_col].iloc[-1])

    daily_pred = daily_summary(
        hourly_pred,
        runnable_min=runnable_min, runnable_max=runnable_max,
        sweet_spot_min=sweet_min, sweet_spot_max=sweet_max,
    )

    if verbose:
        _print_report(daily_pred, metrics, gauge_hist, holdout_comparison)

    if plot:
        plot_results(gauge_hist, holdout_comparison, hourly_pred, precip_hist, metrics)

    return {
        "daily": daily_pred,
        "hourly": hourly_pred,
        "model": model,
        "metrics": metrics,
        "holdout_comparison": holdout_comparison,
        "gauge_hist": gauge_hist,
        "precip_hist": precip_hist,
        "current_cfs": current_display,
    }


def plot_results(
        gauge_hist: pd.DataFrame,
        holdout: pd.DataFrame,
        forecast: pd.DataFrame,
        precip_hist: pd.DataFrame,
        metrics: dict,
):
    """
    Two-panel chart:
      Top:    Actual CFS (blue) | Holdout predictions (orange) | Forecast (orange dashed)
      Bottom: Hourly precipitation bars
    """
    # Show HOLDOUT_DAYS of history before the holdout window for context
    context_start = holdout.index[-1] - timedelta(days=3)
    now_ts = holdout.index[-1]

    actual = gauge_hist[gauge_hist.index >= context_start]
    precip_window = precip_hist[precip_hist.index >= context_start]
    forecast_precip = forecast[["precip_mm"]]

    # Combine precip for bar chart
    all_precip = pd.concat([precip_window, forecast_precip])
    all_precip = all_precip[~all_precip.index.duplicated(keep="last")].sort_index()

    fig, (ax_cfs, ax_rain) = plt.subplots(
        2, 1,
        figsize=(14, 7),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )
    fig.patch.set_facecolor("#1a1a2e")
    for ax in (ax_cfs, ax_rain):
        ax.set_facecolor("#16213e")
        ax.tick_params(colors="0.75")
        ax.spines[:].set_color("0.3")
        ax.yaxis.label.set_color("0.85")
        ax.xaxis.label.set_color("0.85")

    # --- Paddable / sweet-spot bands ---
    ax_cfs.axhspan(PADDABLE_MIN_CFS, PADDABLE_MAX_CFS,
                   color="#2e7d32", alpha=0.12, label="Paddable range")
    ax_cfs.axhspan(SWEET_SPOT_MIN, SWEET_SPOT_MAX,
                   color="#66bb6a", alpha=0.20, label="Sweet spot")

    # --- Actual gauge (blue) ---
    ax_cfs.plot(
        actual.index, actual["cfs"],
        color="#42a5f5", linewidth=1.5, label="Actual CFS",
    )

    # --- Holdout predictions (orange solid, same hourly cadence) ---
    ax_cfs.plot(
        holdout.index, holdout["predicted_cfs"],
        color="#ff7043", linewidth=1.5, label="Predicted CFS (backtest)",
    )

    # --- Forward forecast (orange dashed) ---
    ax_cfs.plot(
        forecast.index, forecast["predicted_cfs"],
        color="#ff7043", linewidth=1.5, linestyle="--", label="Predicted CFS (forecast)",
    )

    # --- Dividers ---
    holdout_start = holdout.index[0]
    ax_cfs.axvline(holdout_start, color="0.55", linewidth=1, linestyle=":")
    ax_cfs.axvline(now_ts, color="white", linewidth=1.2, linestyle="--")
    ax_cfs.text(holdout_start, ax_cfs.get_ylim()[1] if ax_cfs.get_ylim()[1] > 0 else 1,
                " ← train | backtest →", color="0.65", fontsize=8, va="top")
    ax_cfs.text(now_ts, 0, "  now", color="white", fontsize=8, va="bottom")

    # Reference lines
    ax_cfs.axhline(PADDABLE_MIN_CFS, color="#66bb6a", linewidth=0.7, linestyle=":")
    ax_cfs.axhline(PADDABLE_MAX_CFS, color="#ef9a9a", linewidth=0.7, linestyle=":")

    ax_cfs.set_ylabel("Discharge (CFS)", color="0.85")
    ax_cfs.set_title(
        f"Tellico River — USGS {USGS_GAUGE_ID}  |  "
        f"Backtest R²={metrics['r2']:.3f}  MAE={metrics['mae_cfs']:.0f} CFS",
        color="0.9", fontsize=11,
    )
    ax_cfs.legend(loc="upper left", framealpha=0.3, labelcolor="0.9",
                  facecolor="#1a1a2e", edgecolor="0.3", fontsize=8)
    ax_cfs.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:,.0f}"))

    # --- Precipitation bars ---
    bar_width = 1 / 24  # 1 hour in days
    ax_rain.bar(
        all_precip.index, all_precip["precip_mm"] / 25.4,
        width=bar_width, color="#7986cb", alpha=0.8, align="edge",
    )
    ax_rain.axvline(holdout_start, color="0.55", linewidth=1, linestyle=":")
    ax_rain.axvline(now_ts, color="white", linewidth=1.2, linestyle="--")
    ax_rain.set_ylabel('Precip (in)', color="0.85")
    ax_rain.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.2f}"))

    # X-axis formatting
    ax_rain.xaxis.set_major_locator(mdates.DayLocator())
    ax_rain.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax_rain.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 12, 18]))
    plt.setp(ax_rain.xaxis.get_majorticklabels(), rotation=45, ha="right", color="0.75")

    fig.tight_layout()
    out_path = "tellico_forecast.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"\nChart saved → {out_path}")
    try:
        plt.show()
    except AttributeError:
        # PyCharm's bundled matplotlib backend is incompatible with newer matplotlib.
        # Chart has already been saved to disk above; open it from there.
        import subprocess
        subprocess.Popen(["open", out_path])


def _print_report(
        daily: pd.DataFrame,
        metrics: dict,
        gauge_hist: pd.DataFrame,
        holdout: pd.DataFrame,
):
    current_cfs = gauge_hist["cfs"].iloc[-1]
    current_status = _row_status(pd.Series({
        "predicted_cfs_max": current_cfs,
        "sweet_spot": SWEET_SPOT_MIN <= current_cfs <= SWEET_SPOT_MAX,
    }))

    print(f"CURRENT CONDITIONS")
    print(f"  Flow: {current_cfs:.0f} CFS  →  {current_status}")
    print(f"  Paddable range: {PADDABLE_MIN_CFS}–{PADDABLE_MAX_CFS} CFS")
    print(f"  Sweet spot:     {SWEET_SPOT_MIN}–{SWEET_SPOT_MAX} CFS")
    print()

    # --- 5-day backtest (printed at 2h cadence) ---
    holdout_2h = holdout.resample("2h").mean().dropna()
    print(f"BACKTEST: last {HOLDOUT_DAYS} days (2-hour windows, actual vs predicted)")
    print(f"{'Time':<18} {'Actual CFS':>12} {'Predicted CFS':>14} {'Error':>8}")
    print(f"{'-' * 56}")
    for ts, row in holdout_2h.iterrows():
        err = row["error_cfs"]
        sign = "+" if err >= 0 else ""
        print(f"{ts.strftime('%m/%d %H:%M'):<18} {row['actual_cfs']:>10.0f}   "
              f"{row['predicted_cfs']:>12.0f}   {sign}{err:.0f}")
    print(f"\n  Backtest R²={metrics['r2']:.3f}  |  MAE={metrics['mae_cfs']:.0f} CFS  "
          f"|  n={metrics['n_test']} hourly samples")
    print()

    # --- 7-day forward forecast ---
    print(f"7-DAY FORECAST  (2-hour prediction horizon)")
    print(f"{'Date':<12} {'Precip':>8} {'Peak CFS':>10} {'Mean CFS':>10} {'Status':<12}")
    print(f"{'-' * 55}")
    for date, row in daily.iterrows():
        precip_in = row["total_precip_mm"] / 25.4
        date_str = date.strftime("%a %m/%d")
        flag = " <--" if row["paddable"] else ""
        print(f"{date_str:<12} {precip_in:>6.2f}\"  {row['predicted_cfs_max']:>8.0f}  "
              f"{row['predicted_cfs_mean']:>8.0f}  {row['status']:<12}{flag}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Tellico River paddability predictor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python tellico_predictor.py predict       # forecast using saved model (default)
  python tellico_predictor.py retrain       # retrain from scratch then forecast
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["predict", "retrain"],
        default="predict",
        help="predict: use saved model; retrain: retrain from scratch (default: predict)",
    )
    args = parser.parse_args()
    run_prediction(retrain=(args.command == "retrain"), plot=True)
