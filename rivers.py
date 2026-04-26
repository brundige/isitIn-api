"""
River configuration registry.
Add new rivers here — the API and predictor pick them up automatically.
"""

from dataclasses import dataclass


@dataclass
class RiverConfig:
    id: str
    name: str
    gauge_id: str
    watershed_lat: float
    watershed_lon: float
    runnable_min: float      # in display units (CFS or visual gauge ft)
    runnable_max: float
    sweet_spot_min: float
    sweet_spot_max: float
    baseflow_min: float = 30.0   # floor for forecast (in target/prediction units)
    # "cfs"   -> predict discharge (CFS)
    # "stage" -> predict gage height (ft), then convert to visual gauge
    target_param: str = "cfs"
    # Visual gauge linear formula: visual = slope * stage + intercept
    visual_gauge_slope: float = 1.0
    visual_gauge_intercept: float = 0.0
    display_unit: str = "CFS"


def stage_to_visual(stage: float, river: RiverConfig) -> float:
    """Convert USGS gage height (ft) to visual gauge reading (ft)."""
    return river.visual_gauge_slope * stage + river.visual_gauge_intercept


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
        # Ranges in visual gauge feet -- verify with local paddlers
        runnable_min=1.5,
        runnable_max=5.0,
        sweet_spot_min=2.0,
        sweet_spot_max=3.5,
        baseflow_min=2.5,        # minimum stage floor (ft)
        target_param="stage",
        visual_gauge_slope=0.6899,
        visual_gauge_intercept=-1.8740,
        display_unit="ft",
    ),
}
