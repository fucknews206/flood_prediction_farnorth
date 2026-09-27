"""
Data source integrations for Cameroon Flood Intelligence.
All hydrological measurements are in metric units:
- Streamflow / discharge: cubic metres per second (m³/s, cms)
- Basin / drainage area: square kilometres (km²)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import json

log = logging.getLogger(__name__)

@dataclass
class StreamflowData:
    """Streamflow data in metric units"""
    site_code: str
    site_name: str
    streamflow_cms: float
    gage_height_m: Optional[float]
    timestamp: datetime
    quality_code: str = "A"

@dataclass
class BasinSite:
    """River basin information"""
    site_code: str
    site_name: str
    latitude: float
    longitude: float
    drainage_area_sqkm: Optional[float] = None


@dataclass(frozen=True)
class BasinRiskResult:
    """Risk result with auditable Phase 3 trigger provenance."""
    risk_score: float
    risk_level: str
    data_completeness: str
    missing_inputs: List[str]
    risk_source: str
    trigger_reasons: List[str]

# Cameroon Region Configuration (10 Regions)
REGION_CONFIG = {
    "AD": {
        "name": "Adamawa",
        "code": "AD",
        "description": "Adamawa Region, Cameroon",
        "center_lat": 6.8,
        "center_lng": 13.5,
        "zoom": 7,
        "sites": []
    },
    "CE": {
        "name": "Centre",
        "code": "CE",
        "description": "Centre Region, Cameroon",
        "center_lat": 4.5,
        "center_lng": 11.5,
        "zoom": 8,
        "sites": []
    },
    "ES": {
        "name": "East",
        "code": "ES",
        "description": "East Region, Cameroon",
        "center_lat": 4.0,
        "center_lng": 14.0,
        "zoom": 7,
        "sites": []
    },
    "EN": {
        "name": "Far North",
        "code": "EN",
        "description": "Far North Region, Cameroon",
        "center_lat": 10.8,
        "center_lng": 14.5,
        "zoom": 8,
        "sites": []
    },
    "LT": {
        "name": "Littoral",
        "code": "LT",
        "description": "Littoral Region, Cameroon",
        "center_lat": 4.2,
        "center_lng": 10.0,
        "zoom": 8,
        "sites": []
    },
    "NO": {
        "name": "North",
        "code": "NO",
        "description": "North Region, Cameroon",
        "center_lat": 8.5,
        "center_lng": 13.5,
        "zoom": 7,
        "sites": []
    },
    "NW": {
        "name": "North West",
        "code": "NW",
        "description": "North West Region, Cameroon",
        "center_lat": 6.3,
        "center_lng": 10.3,
        "zoom": 8,
        "sites": []
    },
    "SU": {
        "name": "South",
        "code": "SU",
        "description": "South Region, Cameroon",
        "center_lat": 2.8,
        "center_lng": 12.0,
        "zoom": 8,
        "sites": []
    },
    "SW": {
        "name": "South West",
        "code": "SW",
        "description": "South West Region, Cameroon",
        "center_lat": 5.2,
        "center_lng": 9.3,
        "zoom": 8,
        "sites": []
    },
    "OU": {
        "name": "West",
        "code": "OU",
        "description": "West Region, Cameroon",
        "center_lat": 5.5,
        "center_lng": 10.5,
        "zoom": 8,
        "sites": []
    }
}

def get_available_regions() -> List[Dict[str, Any]]:
    """Get list of all available regions with metadata"""
    return [
        {
            "code": config["code"],
            "name": config["name"],
            "description": config["description"],
            "center_lat": config["center_lat"],
            "center_lng": config["center_lng"],
            "zoom": config["zoom"],
            "watershed_count": 0
        }
        for code, config in REGION_CONFIG.items()
    ]

def get_region_config(region_code: str) -> Optional[Dict[str, Any]]:
    """Get configuration for a specific region"""
    return REGION_CONFIG.get(region_code.upper())

def calculate_risk_level(streamflow_cms: float, flood_stage_cms: Optional[float] = None) -> Tuple[str, float]:
    """
    Calculate flood risk level and score based on streamflow data in cubic metres per second (m³/s)
    
    Returns:
        Tuple of (risk_level, risk_score)
    """
    if flood_stage_cms and streamflow_cms >= flood_stage_cms:
        risk_level = "High"
        risk_score = min(10.0, 7.0 + (streamflow_cms / flood_stage_cms - 1.0) * 3.0)
    elif flood_stage_cms and streamflow_cms >= flood_stage_cms * 0.8:
        risk_level = "Moderate" 
        ratio = streamflow_cms / flood_stage_cms
        risk_score = 4.0 + (ratio - 0.8) * 15.0
    elif streamflow_cms > 28.3:  # ~1000 CFS equivalent
        risk_level = "Moderate"
        risk_score = min(7.0, 3.0 + (streamflow_cms / 56.6) * 2.0)
    elif streamflow_cms > 14.16:  # ~500 CFS equivalent
        risk_level = "Low"
        risk_score = 2.0 + (streamflow_cms / 14.16)
    else:
        risk_level = "Low"
        risk_score = min(3.0, max(0.5, streamflow_cms / 5.66))
    
    return risk_level, round(risk_score, 1)

def calculate_trend(current_flow: float, previous_flow: float, time_diff_hours: float) -> Tuple[str, float]:
    """
    Calculate flow trend based on current vs previous measurements in m³/s
    
    Returns:
        Tuple of (trend, trend_rate_cms_per_hour)
    """
    if time_diff_hours <= 0:
        return "stable", 0.0
    
    rate_per_hour = (current_flow - previous_flow) / time_diff_hours
    
    # 0.0283 m3/s per hour is approx 1 CFS per hour
    if abs(rate_per_hour) < 0.0283:
        trend = "stable"
    elif rate_per_hour > 0:
        trend = "rising"
    else:
        trend = "falling"
    
    return trend, round(rate_per_hour, 3)

def calculate_risk_with_partial_data(
    rainfall_mm: float,
    community_count: int,
    discharge_cms: Optional[float],
    discharge_status: str,
    flood_stage_cms: Optional[float] = None
) -> Tuple[float, str, str, List[str]]:
    """
    Calculate overall risk using a renormalized weights scheme if GloFAS is unavailable.
    
    Inputs:
    - rainfall_mm: 24h precipitation in mm
    - community_count: recent community reports in the basin
    - discharge_cms: GloFAS discharge forecast in m³/s
    - discharge_status: "available" | "unavailable" | "stale"
    - flood_stage_cms: optional flood stage in m³/s
    
    Returns:
    - risk_score (0.0 to 10.0)
    - risk_level ("Low" | "Moderate" | "High")
    - data_completeness ("full" | "partial")
    - missing_inputs list
    """
    # 1. Rainfall score (0 to 10)
    # 2mm or less is no risk, 50mm or more is max risk
    if rainfall_mm <= 2.0:
        rain_score = 0.0
    elif rainfall_mm >= 50.0:
        rain_score = 10.0
    else:
        rain_score = ((rainfall_mm - 2.0) / 48.0) * 10.0
        
    # 2. Community reports score (0 to 10)
    if community_count == 0:
        comm_score = 0.0
    elif community_count == 1:
        comm_score = 4.0
    elif community_count == 2:
        comm_score = 7.0
    else:
        comm_score = 10.0
        
    # Weights configuration
    w_rain = 0.6
    w_comm = 0.4
    w_disch = 0.5
    
    missing_inputs = []
    
    if discharge_status == "available" and discharge_cms is not None:
        # Determine discharge score
        f_stage = flood_stage_cms or 50.0 # fallback default threshold
        if discharge_cms >= f_stage:
            disch_score = 10.0
        else:
            disch_score = (discharge_cms / f_stage) * 10.0
            
        sum_weights = w_rain + w_comm + w_disch
        risk_score = (rain_score * w_rain + comm_score * w_comm + disch_score * w_disch) / sum_weights
        data_completeness = "full"
    else:
        # Renormalise weights over available inputs
        sum_weights = w_rain + w_comm
        risk_score = (rain_score * w_rain + comm_score * w_comm) / sum_weights
        
        # Cap at 7.0 when discharge is unavailable
        risk_score = min(7.0, risk_score)
        data_completeness = "partial"
        missing_inputs.append("discharge")
        
    risk_score = round(risk_score, 1)
    
    if risk_score >= 7.0:
        risk_level = "High"
    elif risk_score >= 4.0:
        risk_level = "Moderate"
    else:
        risk_level = "Low"
        
    return risk_score, risk_level, data_completeness, missing_inputs


def calculate_calibrated_basin_risk(
    rainfall_mm: float,
    rainfall_two_day_mm: Optional[float],
    community_count: int,
    discharge_cms: Optional[float],
    discharge_status: str,
    flood_stage_cms: Optional[float] = None,
    local_daily_threshold_mm: float = 20.0,
    local_two_day_threshold_mm: float = 30.0,
    upstream_propagation_active: bool = False,
    upstream_sources: Optional[List[str]] = None,
) -> BasinRiskResult:
    """Combine calibrated local rainfall and delayed upstream flow with Phase 2 inputs.

    The local thresholds are supplied by the basin record, never hard-coded by
    the caller.  An upstream signal is an additional weighted input: it can
    elevate a clear-sky downstream basin, while local rain, discharge and
    community reports continue to compound the score.
    """
    two_day = rainfall_two_day_mm if rainfall_two_day_mm is not None else rainfall_mm
    reasons: List[str] = []
    local_trigger = (
        rainfall_mm >= local_daily_threshold_mm
        or two_day >= local_two_day_threshold_mm
    )
    if rainfall_mm >= local_daily_threshold_mm:
        reasons.append("local_rainfall_daily_threshold")
    if two_day >= local_two_day_threshold_mm:
        reasons.append("local_rainfall_two_day_threshold")
    if upstream_propagation_active:
        reasons.append("upstream_propagation")
        reasons.extend(upstream_sources or [])

    # Preserve the established generic rainfall curve, but make a calibrated
    # local trigger a strong (7/10) signal at its basin-specific threshold.
    if rainfall_mm <= 2.0:
        rain_score = 0.0
    elif rainfall_mm >= 50.0:
        rain_score = 10.0
    else:
        rain_score = ((rainfall_mm - 2.0) / 48.0) * 10.0
    if local_trigger:
        rain_score = max(rain_score, 7.0)

    comm_score = 0.0 if community_count == 0 else 4.0 if community_count == 1 else 7.0 if community_count == 2 else 10.0
    propagation_score = 8.0 if upstream_propagation_active else 0.0
    w_rain, w_comm, w_disch, w_propagation = 0.6, 0.4, 0.5, 0.6
    weights = w_rain + w_comm + (w_propagation if upstream_propagation_active else 0.0)
    numerator = rain_score * w_rain + comm_score * w_comm + propagation_score * w_propagation
    missing_inputs: List[str] = []

    if discharge_status == "available" and discharge_cms is not None:
        flood_stage = flood_stage_cms or 50.0
        discharge_score = min(10.0, (discharge_cms / flood_stage) * 10.0)
        numerator += discharge_score * w_disch
        weights += w_disch
        completeness = "full"
    else:
        missing_inputs.append("discharge")
        completeness = "partial"

    score = numerator / weights if weights else 0.0
    # A calibrated trigger is operationally meaningful even without GloFAS;
    # do not suppress it with the legacy partial-data cap.
    if local_trigger or upstream_propagation_active:
        score = max(score, 4.0)
    elif discharge_status != "available":
        score = min(7.0, score)
    score = round(min(10.0, score), 1)
    level = "High" if score >= 7.0 else "Moderate" if score >= 4.0 else "Low"
    source = "compound" if local_trigger and upstream_propagation_active else "local_rainfall" if local_trigger else "upstream_propagation" if upstream_propagation_active else "discharge_forecast" if discharge_status == "available" and discharge_cms else "none"
    return BasinRiskResult(score, level, completeness, missing_inputs, source, reasons)

# Legacy US-centric stubs for backward compatibility
def fetch_and_update_usgs_data(db_path: str, site_codes: Optional[List[str]] = None, region_code: Optional[str] = None) -> Dict[str, Any]:
    log.info("fetch_and_update_usgs_data is not applicable for Cameroon.")
    return {"success": False, "message": "USGS data is not applicable for Cameroon"}

def fetch_and_store_noaa_alerts(db_path: str) -> Dict[str, Any]:
    log.info("fetch_and_store_noaa_alerts is not applicable for Cameroon.")
    return {"success": False, "message": "NOAA alerts are not applicable for Cameroon"}

def create_watersheds_from_usgs_sites(db_path: str, limit: int = 20, region_code: str = "TX") -> Dict[str, Any]:
    log.info("create_watersheds_from_usgs_sites is not applicable for Cameroon.")
    return {"success": False, "message": "USGS sites are not applicable for Cameroon"}
