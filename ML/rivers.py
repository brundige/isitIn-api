"""
River configuration registry.
Add new rivers here — the API and predictor pick them up automatically.

Rivers come in two flavors, distinguished by `kind`:
  - "gauge"     — has a USGS gauge; ML predictor handles status/forecast
  - "scheduled" — dam-controlled; status derives from the release calendar
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal


# ---------------------------------------------------------------------------
# Schedule primitives
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReleaseWindow:
    """A single dam release: gates open from start_hour to end_hour on `day` (local time)."""
    day: date
    start_hour: int
    end_hour: int


def _windows(durations: dict[tuple[int, int], list[str]]) -> list[ReleaseWindow]:
    """
    Compact schedule-builder. Maps (start_hour, end_hour) → list of ISO dates.
    Returned list is sorted ascending by date.
    """
    out: list[ReleaseWindow] = []
    for (start, end), dates in durations.items():
        for d in dates:
            out.append(ReleaseWindow(date.fromisoformat(d), start, end))
    return sorted(out, key=lambda w: w.day)


# ---------------------------------------------------------------------------
# RiverConfig
# ---------------------------------------------------------------------------

@dataclass
class RiverConfig:
    id: str
    name: str
    kind: Literal["gauge", "scheduled"] = "gauge"

    # --- gauge-river fields (required when kind="gauge") ----------------------
    gauge_id: str | None = None
    watershed_lat: float | None = None
    watershed_lon: float | None = None
    runnable_min: float = 0
    runnable_max: float = 0
    sweet_spot_min: float = 0
    sweet_spot_max: float = 0
    baseflow_min: float = 30.0
    target_param: str = "cfs"           # "cfs" | "stage"
    visual_gauge_slope: float = 1.0
    visual_gauge_intercept: float = 0.0
    display_unit: str = "CFS"

    # --- scheduled-river fields (required when kind="scheduled") --------------
    release_cfs: float = 1500.0         # nominal flow when gates are open
    release_windows: list[ReleaseWindow] = field(default_factory=list)


def stage_to_visual(stage: float, river: RiverConfig) -> float:
    """Convert USGS gage height (ft) to visual gauge reading (ft)."""
    return river.visual_gauge_slope * stage + river.visual_gauge_intercept


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

RIVERS: dict[str, RiverConfig] = {
    "tellico": RiverConfig(
        id="tellico",
        name="Tellico River",
        gauge_id="03518500",
        watershed_lat=35.37,
        watershed_lon=-84.28,
        runnable_min=300,
        runnable_max=1000,
        sweet_spot_min=500,
        sweet_spot_max=600,
        baseflow_min=30.0,
        target_param="cfs",
        display_unit="CFS",
    ),
    "north_chick": RiverConfig(
        id="north_chick",
        name="North Chickamauga Creek",
        gauge_id="03566535",
        watershed_lat=35.2112,
        watershed_lon=-85.2152,
        runnable_min=1.5,
        runnable_max=5.0,
        sweet_spot_min=2.0,
        sweet_spot_max=3.5,
        baseflow_min=2.5,
        target_param="stage",
        visual_gauge_slope=0.6899,
        visual_gauge_intercept=-1.8740,
        display_unit="ft",
    ),

    # -----------------------------------------------------------------------
    # Middle Ocoee (Ocoee #2) — 2026 recreational release calendar.
    # Runnable range is permissive on purpose: when gates are open (~1500 cfs)
    # the river is always runnable; when they're closed, current_cfs=0 → TOO LOW.
    # -----------------------------------------------------------------------
    "ocoee_middle": RiverConfig(
        id="ocoee_middle",
        name="Middle Ocoee",
        kind="scheduled",
        display_unit="CFS",
        release_cfs=1500,
        runnable_min=1000,
        runnable_max=2200,
        sweet_spot_min=1300,
        sweet_spot_max=1700,
        release_windows=_windows({
            (10, 16): [  # 6-hour days
                "2026-03-21", "2026-03-22", "2026-03-28", "2026-03-29",
                "2026-05-28", "2026-05-29",
                # June Mon/Thu/Fri
                "2026-06-01", "2026-06-04", "2026-06-05",
                "2026-06-08", "2026-06-11", "2026-06-12",
                "2026-06-15", "2026-06-18", "2026-06-19",
                "2026-06-22", "2026-06-25", "2026-06-26", "2026-06-29",
                # August
                "2026-08-03",
                # September late + October + November 1
                "2026-09-26", "2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30",
                "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04",
                "2026-10-10", "2026-10-11",
                "2026-10-17", "2026-10-18",
                "2026-10-24", "2026-10-25",
                "2026-10-31",
                "2026-11-01",
            ],
            (9, 17): [  # 8-hour days
                # April every weekend
                "2026-04-04", "2026-04-05", "2026-04-11", "2026-04-12",
                "2026-04-18", "2026-04-19", "2026-04-25", "2026-04-26",
                # May weekends + Memorial Day (5/25) + final two days
                "2026-05-02", "2026-05-03", "2026-05-09", "2026-05-10",
                "2026-05-16", "2026-05-17", "2026-05-23", "2026-05-24",
                "2026-05-25", "2026-05-30", "2026-05-31",
                # July Thu/Fri
                "2026-07-02", "2026-07-03", "2026-07-09", "2026-07-10",
                "2026-07-16", "2026-07-17", "2026-07-23", "2026-07-24",
                "2026-07-30", "2026-07-31",
                # August anomaly day + Labor Day weekend
                "2026-08-07",
                "2026-09-07", "2026-09-13", "2026-09-20",
            ],
            (9, 16): [  # 7-hour days
                # July Mondays
                "2026-07-06", "2026-07-13", "2026-07-20", "2026-07-27",
                "2026-08-06",
            ],
            (9, 19): [  # 10-hour days
                # June Sat/Sun
                "2026-06-06", "2026-06-07", "2026-06-13", "2026-06-14",
                "2026-06-20", "2026-06-21", "2026-06-27", "2026-06-28",
                # July Sat/Sun (incl. 4th of July)
                "2026-07-04", "2026-07-05", "2026-07-11", "2026-07-12",
                "2026-07-18", "2026-07-19", "2026-07-25", "2026-07-26",
                # August Sat/Sun
                "2026-08-01", "2026-08-02", "2026-08-08", "2026-08-09",
                "2026-08-15", "2026-08-16", "2026-08-22", "2026-08-23",
                "2026-08-29", "2026-08-30",
                # September early
                "2026-09-05", "2026-09-06", "2026-09-12", "2026-09-19",
            ],
            (10, 15): [  # 5-hour days
                # August Mon/Thu/Fri
                "2026-08-10", "2026-08-13", "2026-08-14",
                "2026-08-17", "2026-08-20", "2026-08-21",
                "2026-08-24", "2026-08-27", "2026-08-28", "2026-08-31",
                # September Thu/Fri
                "2026-09-03", "2026-09-04",
            ],
        }),
    ),

    # -----------------------------------------------------------------------
    # Upper Ocoee (Ocoee #3) — 2026 recreational release calendar.
    # Different durations than Middle (note start times — 8:30a/9a, not 9a/10a).
    # -----------------------------------------------------------------------
    "ocoee_upper": RiverConfig(
        id="ocoee_upper",
        name="Upper Ocoee",
        kind="scheduled",
        display_unit="CFS",
        release_cfs=1200,
        runnable_min=800,
        runnable_max=1800,
        sweet_spot_min=1000,
        sweet_spot_max=1500,
        release_windows=_windows({
            # 8-hour days at 8:30a–4:30p — we round the half-hour to whole hours
            # since hourly synthesis works in integer hour buckets. Status during
            # 8a or 5p edge-hours is a non-issue in practice.
            (9, 17): [
                "2026-05-24",
                "2026-07-04", "2026-07-11", "2026-07-18", "2026-07-25",
                "2026-08-01", "2026-08-08", "2026-08-15", "2026-08-22", "2026-08-29",
                "2026-09-05", "2026-09-06",
            ],
            (9, 15): [  # 6-hour days
                "2026-05-16", "2026-05-23", "2026-05-30", "2026-05-31",
                "2026-06-06", "2026-06-13", "2026-06-20", "2026-06-27",
                "2026-09-12",
            ],
            (9, 14): [  # 5-hour days
                "2026-06-07", "2026-06-14", "2026-06-21", "2026-06-28",
                "2026-07-05", "2026-07-12", "2026-07-19", "2026-07-26",
                "2026-08-02", "2026-08-09", "2026-08-16", "2026-08-23", "2026-08-30",
            ],
        }),
    ),
}
