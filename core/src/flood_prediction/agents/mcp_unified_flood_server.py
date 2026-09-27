#!/usr/bin/env python3
"""
Unified FastMCP Server for Flood Prediction - All Agents Combined
Integrates Data Collector, Risk Analyzer, Emergency Responder, and Predictor agents
"""

from fastmcp import FastMCP
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone, timedelta
import asyncio
import aiohttp
import json
import logging
import sys
import os

# Import the agent classes
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from .data_collector import DataCollectorAgent
from .risk_analyzer import RiskAnalyzerAgent
from .emergency_responder import EmergencyResponderAgent
from .predictor import PredictorAgent
from .h2ogpte_agent import H2OGPTEAgent
from .cameroon_context import build_cameroon_context
import urllib.request
import urllib.parse

# The operational source of truth is the FastAPI layer, which invokes
# farnorth_risk_engine.py in the backend process. Calling that API here avoids
# importing the large data-science environment into the lightweight MCP venv.
_FAR_NORTH_API = os.environ.get("FAR_NORTH_API_URL", "http://127.0.0.1:8000/api")
MAX_AGENT_TOOL_OUTPUT_CHARS = 12000


def _bound_agent_tool_output(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Keep backend data from exhausting an agent context window.

    Tool results are data, not a place for logs or an unbounded report.  The
    normal Far North responses are well below this limit; if a future backend
    response grows unexpectedly, expose an explicit truncation marker instead
    of silently handing an agent a partial JSON object that could invite
    guessing.
    """
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(encoded) <= MAX_AGENT_TOOL_OUTPUT_CHARS:
        return payload
    return {
        "status": "truncated_for_agent_context",
        "message": (
            "The backend response exceeded the agent context budget and was "
            "not passed through in full. Do not infer omitted values; ask for "
            "a narrower locality, date, or ranking request."
        ),
        "data_excerpt": encoded[:MAX_AGENT_TOOL_OUTPUT_CHARS],
    }

def _far_north_request(path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    method = "GET" if data is None else "POST"
    req = urllib.request.Request(
        f"{_FAR_NORTH_API}{path}", data=data, method=method,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local-token"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        # FastAPI/JSON is UTF-8; specify it explicitly so names such as
        # Bélé and Tézoko cannot be double-decoded as Latin-1.
        return _bound_agent_tool_output(json.loads(response.read().decode("utf-8")))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create the MCP server instance
mcp = FastMCP("unified-flood-prediction")

# Initialize all agents
data_collector = DataCollectorAgent()
risk_analyzer = RiskAnalyzerAgent()
emergency_responder = EmergencyResponderAgent()
predictor = PredictorAgent()
h2ogpte_agent = H2OGPTEAgent()


# =============================================================================
# Far North-only MCP tools exposed to NAT agents
# =============================================================================

# Exposed safe MCP tool.
@mcp.tool()
def get_far_north_locality_risk(locality: str) -> Dict[str, Any]:
    """Return the real rules-based risk for a gazetteer locality."""
    return _far_north_request("/farnorth/risk", {"locality": locality})


# Exposed safe MCP tool.
@mcp.tool()
def get_far_north_locality_forecast(locality: str, target_date: Optional[str] = None,
                                    days: int = 5) -> Dict[str, Any]:
    """Return real Open-Meteo/GloFAS forecast features for a Far North locality."""
    result = _far_north_request("/farnorth/forecast", {"locality": locality, "target_date": target_date, "days": max(1, min(int(days), 5))})
    # Static susceptibility can include all gazetteer places, while the
    # forecast model only covers tracked localities with environmental inputs.
    # Never let an uncovered static place look like a forecast-supported one.
    if not result.get("upstream_basin_count"):
        return {
            "status": "not_available",
            "locality": locality,
            "message": "No complete upstream-basin forecast coverage is available for this locality; choose a covered Far North locality such as Kousséri or Yagoua.",
            "source": result.get("source"),
        }
    return result


# Exposed safe MCP tool.
@mcp.tool()
def get_far_north_division_risk(division: str) -> Dict[str, Any]:
    """Return maximum real locality risk and breakdown for a Far North division."""
    return _far_north_request("/farnorth/division-risk", {"division": division})


# Exposed safe MCP tool.
@mcp.tool()
def get_far_north_top_risk_localities(n: int = 5, division: Optional[str] = None) -> Dict[str, Any]:
    """Return the real static-susceptibility ranking for covered localities."""
    query = urllib.parse.urlencode({"n": max(1, min(int(n), 20)), **({"division": division} if division else {})})
    return _far_north_request(f"/farnorth/top-risk?{query}")


def _current_risk_assessment(context: Dict[str, Any]) -> Dict[str, Any]:
    """Present persisted Cameroon risk without turning partial data into Unknown."""
    basins = context.get("basins", [])
    if not basins:
        return {"level": "Unknown", "score": None, "score_display": "Unknown",
                "partial": False, "reason": "No basin, rainfall, or community-report data exists for this location."}
    weight = sum((b.get("basin_size_sqkm") or 1) for b in basins)
    score = round(sum((b.get("risk_score") or 0) * (b.get("basin_size_sqkm") or 1)
                      for b in basins) / weight, 1) if weight else 0.0
    level = ("High" if score >= 7 else "Moderate" if score >= 4 else "Low")
    partial = any(b.get("discharge_status") == "unavailable" or
                  b.get("data_completeness") == "partial" for b in basins)
    return {"level": level, "score": score,
            "score_display": f"{score:.1f}/10" + (" (partial)" if partial else ""),
            "partial": partial,
            "discharge_note": "Discharge data is unavailable; this risk score uses the available rainfall and community-report inputs."
                              if partial else None}

# =============================================================================
# DATA COLLECTOR AGENT TOOLS
# =============================================================================

# Legacy helper intentionally not exposed through MCP.
async def get_cameroon_flood_context(
    location: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, Any]:
    """Resolve a Cameroon place and return current basin risk, rainfall and reports."""
    context = await build_cameroon_context(location, lat, lon)
    return {"status": "success" if context["has_data"] else "not_found",
            "agent": "Data Collector", "data": context}

# Legacy helper intentionally not exposed through MCP.
async def generate_data_insights() -> Dict[str, Any]:
    """Generate Cameroon data-collection insights without external US tools."""
    try:
        logger.info("Data Collector: Generating insights")

        actual_data = await build_cameroon_context()

        insights = await data_collector.analyze(actual_data)
        alerts = await data_collector.check_alerts(actual_data)

        return {
            "status": "success",
            "agent": "Data Collector",
            "data_collected": {
                "cameroon_basins": len(actual_data["basins"]),
                "rainfall_status": actual_data["recent_rainfall"]["status"],
                "community_reports": len(actual_data["recent_community_reports"])
            },
            "insights": [
                {
                    "title": insight.title,
                    "value": insight.value,
                    "change": insight.change,
                    "trend": insight.trend,
                    "urgency": insight.urgency
                } for insight in insights
            ],
            "alerts": [
                {
                    "id": alert.id,
                    "title": alert.title,
                    "message": alert.message,
                    "severity": alert.severity,
                    "recommendations": alert.recommendations
                } for alert in alerts
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error in generate_data_insights: {e}")
        return {
            "status": "error",
            "agent": "Data Collector",
            "message": str(e)
        }

# =============================================================================
# RISK ANALYZER AGENT TOOLS
# =============================================================================

# Legacy helper intentionally not exposed through MCP.
async def analyze_flood_risk(
    location: Optional[str] = None,
    watershed_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Analyze flood risk conditions using AI-powered analysis.

    Args:
        watershed_data: Optional watershed data, if not provided will collect actual data
    """
    try:
        logger.info("Risk Analyzer: Analyzing flood risk")

        # Resolve named Cameroon locations to Stage 1/2 records before any
        # coordinate path.  Never request non-Cameroon monitoring data.
        if not watershed_data:
            watershed_data = await build_cameroon_context(location)

        insights = await risk_analyzer.analyze(watershed_data)
        alerts = await risk_analyzer.check_alerts(watershed_data)

        return {
            "status": "success",
            "agent": "Risk Analyzer",
            "location_context": watershed_data,
            "current_risk": _current_risk_assessment(watershed_data),
            "insights": [
                {
                    "title": insight.title,
                    "value": insight.value,
                    "change": insight.change,
                    "trend": insight.trend,
                    "urgency": insight.urgency
                } for insight in insights
            ],
            "alerts": [
                {
                    "id": alert.id,
                    "title": alert.title,
                    "message": alert.message,
                    "severity": alert.severity,
                    "affected_areas": alert.affected_areas,
                    "recommendations": alert.recommendations
                } for alert in alerts
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error in analyze_flood_risk: {e}")
        return {
            "status": "error",
            "agent": "Risk Analyzer",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
def calculate_risk_score(
    location: str,
    current_rainfall_mm: float = 0,
    forecast_rainfall_mm: float = 0,
    elevation_m: float = 100,
    distance_to_water_km: float = 5,
    population_density: int = 1000,
    historical_events: int = 0,
    usgs_flow_cfs: float = 0,
    river_stage_ft: float = 0,
    flood_stage_ft: float = 20,
    weather_alerts: int = 0
) -> Dict[str, Any]:
    """Calculate comprehensive flood risk score using FEMA-aligned methodology.

    Based on Risk = Likelihood × Severity approach with normalized scoring (0-100 scale).

    Args:
        location: Location name
        current_rainfall_mm: Current rainfall in mm (>50mm = flash flood risk)
        forecast_rainfall_mm: Forecast rainfall in mm (>75mm/day = high risk)
        elevation_m: Elevation above sea level in meters
        distance_to_water_km: Distance to nearest water body in km
        population_density: Population density per km²
        historical_events: Number of historical flood events
        usgs_flow_cfs: USGS flow rate in cubic feet per second
        river_stage_ft: Current river stage in feet
        flood_stage_ft: Flood stage threshold in feet (NWS standard)
        weather_alerts: Number of active weather alerts
    """
    try:
        logger.info(f"Risk Analyzer: Calculating risk score for {location}")

        # LIKELIHOOD FACTORS (0-50 scale)
        # ==============================

        # 1. Rainfall intensity score (0-20): Based on flash flood guidance
        # >50mm in short period = very high risk, >75mm/day = extreme
        total_rainfall = current_rainfall_mm + (forecast_rainfall_mm * 0.8)
        if total_rainfall >= 100:
            rainfall_score = 20
        elif total_rainfall >= 75:
            rainfall_score = 16
        elif total_rainfall >= 50:
            rainfall_score = 12
        elif total_rainfall >= 25:
            rainfall_score = 8
        else:
            rainfall_score = min(8, total_rainfall / 3.125)  # Linear up to 25mm

        # 2. River stage ratio score (0-15): Most critical real-time indicator
        stage_score = 0
        if river_stage_ft > 0 and flood_stage_ft > 0:
            stage_ratio = river_stage_ft / flood_stage_ft
            if stage_ratio >= 1.0:  # At or above flood stage
                stage_score = 15
            elif stage_ratio >= 0.9:  # Within 90% - critical
                stage_score = 12
            elif stage_ratio >= 0.8:  # Within 80% - major concern
                stage_score = 10
            elif stage_ratio >= 0.7:  # Within 70% - action stage
                stage_score = 7
            else:
                stage_score = min(7, stage_ratio * 10)

        # 3. Flow rate score (0-10): Normalized to typical flood flows
        # Average flood flow ~20,000 cfs for major rivers
        flow_score = 0
        if usgs_flow_cfs > 0:
            if usgs_flow_cfs >= 50000:
                flow_score = 10
            elif usgs_flow_cfs >= 20000:
                flow_score = 8
            elif usgs_flow_cfs >= 10000:
                flow_score = 6
            else:
                flow_score = min(6, (usgs_flow_cfs / 10000) * 6)

        # 4. Weather alerts score (0-5): Active warnings
        alert_score = min(5, weather_alerts * 2.5)

        likelihood_score = rainfall_score + stage_score + flow_score + alert_score

        # SEVERITY FACTORS (0-50 scale)
        # ==============================

        # 5. Elevation/topography score (0-15): Lower = higher risk
        # <50m very high risk, >200m lower risk
        if elevation_m < 50:
            elevation_score = 15
        elif elevation_m < 100:
            elevation_score = 12
        elif elevation_m < 150:
            elevation_score = 8
        elif elevation_m < 200:
            elevation_score = 5
        else:
            elevation_score = max(0, 15 - (elevation_m / 40))

        # 6. Proximity to water (0-15): Distance matters
        if distance_to_water_km < 0.5:
            proximity_score = 15
        elif distance_to_water_km < 1:
            proximity_score = 12
        elif distance_to_water_km < 2:
            proximity_score = 9
        elif distance_to_water_km < 5:
            proximity_score = 5
        else:
            proximity_score = max(0, 15 - distance_to_water_km * 1.5)

        # 7. Historical flood events (0-10): Past is predictor
        historical_score = min(10, historical_events * 2)

        # 8. Population exposure (0-10): Impact severity
        # >2000/km² = high density urban
        if population_density >= 3000:
            population_score = 10
        elif population_density >= 2000:
            population_score = 8
        elif population_density >= 1000:
            population_score = 5
        else:
            population_score = min(5, population_density / 200)

        severity_score = elevation_score + proximity_score + historical_score + population_score

        # TOTAL RISK SCORE (0-100 scale)
        total_score = likelihood_score + severity_score

        # Risk level classification (FEMA-aligned)
        if total_score >= 80:
            risk_level, color = "Extreme", "#8B0000"
        elif total_score >= 65:
            risk_level, color = "Critical", "#FF0000"
        elif total_score >= 50:
            risk_level, color = "High", "#FF8C00"
        elif total_score >= 35:
            risk_level, color = "Moderate", "#FFD700"
        elif total_score >= 20:
            risk_level, color = "Low", "#90EE90"
        else:
            risk_level, color = "Very Low", "#00FF00"

        # Immediate risk assessment
        immediate_risk = "High" if (
            current_rainfall_mm > 50 or  # Flash flood threshold
            weather_alerts > 0 or
            (river_stage_ft > 0 and flood_stage_ft > 0 and river_stage_ft / flood_stage_ft >= 0.9)
        ) else "Low"

        return {
            "status": "success",
            "agent": "Risk Analyzer",
            "location": location,
            "overall_risk_score": round(total_score, 1),
            "risk_level": risk_level,
            "risk_color": color,
            "immediate_risk": immediate_risk,
            "component_scores": {
                "likelihood": {
                    "total": round(likelihood_score, 1),
                    "rainfall": round(rainfall_score, 1),
                    "river_stage": round(stage_score, 1),
                    "flow_rate": round(flow_score, 1),
                    "alerts": round(alert_score, 1)
                },
                "severity": {
                    "total": round(severity_score, 1),
                    "elevation": round(elevation_score, 1),
                    "proximity": round(proximity_score, 1),
                    "historical": round(historical_score, 1),
                    "population": round(population_score, 1)
                }
            },
            "stage_info": {
                "current_stage_ft": river_stage_ft,
                "flood_stage_ft": flood_stage_ft,
                "percent_of_flood_stage": round((river_stage_ft / flood_stage_ft * 100), 1) if flood_stage_ft > 0 else 0
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Risk calculation error: {e}")
        return {
            "status": "error",
            "agent": "Risk Analyzer",
            "message": str(e),
            "location": location
        }

# =============================================================================
# EMERGENCY RESPONDER AGENT TOOLS
# =============================================================================

# Legacy helper intentionally not exposed through MCP.
async def assess_emergency_response() -> Dict[str, Any]:
    """Assess emergency response status and readiness."""
    try:
        logger.info("Emergency Responder: Assessing response status")

        actual_data = await build_cameroon_context()

        insights = await emergency_responder.analyze(actual_data)
        alerts = await emergency_responder.check_alerts(actual_data)

        return {
            "status": "success",
            "agent": "Emergency Responder",
            "insights": [
                {
                    "title": insight.title,
                    "value": insight.value,
                    "change": insight.change,
                    "trend": insight.trend,
                    "urgency": insight.urgency
                } for insight in insights
            ],
            "alerts": [
                {
                    "id": alert.id,
                    "title": alert.title,
                    "message": alert.message,
                    "severity": alert.severity,
                    "affected_areas": alert.affected_areas,
                    "recommendations": alert.recommendations
                } for alert in alerts
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error in assess_emergency_response: {e}")
        return {
            "status": "error",
            "agent": "Emergency Responder",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
async def activate_emergency_alert(
    alert_type: str,
    location: str,
    severity: str = "warning",
    message: str = "Emergency flood conditions detected"
) -> Dict[str, Any]:
    """Activate emergency alert for specified conditions.
    
    Args:
        alert_type: Type of alert (flash_flood, evacuation, infrastructure)
        location: Location/area for alert
        severity: Alert severity (warning, critical)
        message: Alert message
    """
    try:
        logger.info(f"Emergency Responder: Activating {alert_type} alert for {location}")
        
        # Simulate alert activation
        alert_id = f"{alert_type}_{location}_{datetime.now().strftime('%Y%m%d%H%M')}"
        
        return {
            "status": "success",
            "agent": "Emergency Responder",
            "alert_id": alert_id,
            "alert_type": alert_type,
            "location": location,
            "severity": severity,
            "message": message,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "estimated_reach": "10,000+ people",
            "channels": ["Emergency Alert System", "Cell Broadcast", "Social Media"]
        }
    except Exception as e:
        logger.error(f"Error in activate_emergency_alert: {e}")
        return {
            "status": "error",
            "agent": "Emergency Responder",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
async def coordinate_evacuation(
    zone_name: str,
    evacuation_type: str = "voluntary",
    estimated_population: int = 1000
) -> Dict[str, Any]:
    """Coordinate evacuation for specified zone.
    
    Args:
        zone_name: Name of evacuation zone
        evacuation_type: Type of evacuation (voluntary, mandatory)
        estimated_population: Estimated population in zone
    """
    try:
        logger.info(f"Emergency Responder: Coordinating {evacuation_type} evacuation for {zone_name}")
        
        success = await emergency_responder.declare_evacuation_zone(zone_name, evacuation_type)
        
        return {
            "status": "success" if success else "error",
            "agent": "Emergency Responder",
            "zone_name": zone_name,
            "evacuation_type": evacuation_type,
            "estimated_population": estimated_population,
            "declared_at": datetime.now(timezone.utc).isoformat(),
            "estimated_duration": "6-12 hours",
            "shelter_capacity": "Available",
            "transportation": "Coordinated"
        }
    except Exception as e:
        logger.error(f"Error in coordinate_evacuation: {e}")
        return {
            "status": "error",
            "agent": "Emergency Responder",
            "message": str(e)
        }

# =============================================================================
# PREDICTOR AGENT TOOLS
# =============================================================================

# Legacy helper intentionally not exposed through MCP.
async def generate_flood_forecast(
    hours_ahead: int = 24,
    location: Optional[str] = None,
    watershed_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generate AI-powered flood forecast.

    Args:
        hours_ahead: Forecast horizon in hours
        watershed_data: Optional watershed data, if not provided will collect actual data
    """
    try:
        logger.info(f"Predictor: Generating {hours_ahead}h flood forecast")

        # Use the persisted Cameroon basin state; forecasting must not trigger
        # a legacy water-station lookup.
        if not watershed_data:
            watershed_data = await build_cameroon_context(location)

        forecast = await predictor.generate_forecast(watershed_data, hours_ahead)

        return {
            "status": "success",
            "agent": "AI Predictor",
            "forecast": forecast,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error in generate_flood_forecast: {e}")
        return {
            "status": "error",
            "agent": "AI Predictor",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
async def analyze_prediction_accuracy() -> Dict[str, Any]:
    """Analyze AI prediction model accuracy and performance."""
    try:
        logger.info("Predictor: Analyzing prediction accuracy")

        actual_data = await build_cameroon_context()

        insights = await predictor.analyze(actual_data)
        alerts = await predictor.check_alerts(actual_data)

        return {
            "status": "success",
            "agent": "AI Predictor",
            "insights": [
                {
                    "title": insight.title,
                    "value": insight.value,
                    "change": insight.change,
                    "trend": insight.trend,
                    "urgency": insight.urgency
                } for insight in insights
            ],
            "alerts": [
                {
                    "id": alert.id,
                    "title": alert.title,
                    "message": alert.message,
                    "severity": alert.severity,
                    "recommendations": alert.recommendations
                } for alert in alerts
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error in analyze_prediction_accuracy: {e}")
        return {
            "status": "error",
            "agent": "AI Predictor",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
async def predict_critical_conditions(
    location: str = "Cameroon"
) -> Dict[str, Any]:
    """Predict next critical flood conditions for a location.

    Args:
        location: Location to analyze
    """
    try:
        logger.info(f"Predictor: Predicting critical conditions for {location}")

        actual_data = await build_cameroon_context(location)

        # Use the predictor's internal method
        critical_period = await predictor._predict_next_critical_period(actual_data)

        if not critical_period:
            return {
                "status": "success",
                "agent": "AI Predictor",
                "location": location,
                "prediction": "No critical conditions predicted in next 72 hours",
                "confidence": "N/A",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        return {
            "status": "success",
            "agent": "AI Predictor",
            "location": location,
            "critical_period": critical_period,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error in predict_critical_conditions: {e}")
        return {
            "status": "error",
            "agent": "AI Predictor",
            "message": str(e)
        }

# =============================================================================
# H2OGPTE ML AGENT TOOLS
# =============================================================================

# Legacy helper intentionally not exposed through MCP.
async def h2ogpte_train_model(
    dataset_description: str,
    target_variable: str = "flood_risk",
    model_type: str = "classification",
    user_query: str = ""
) -> Dict[str, Any]:
    """Train ML model using H2OGPTE agent with Driverless AI AutoML capabilities.
    
    Args:
        dataset_description: Description of the dataset to be used for training
        target_variable: Target variable for prediction (default: flood_risk)
        model_type: Type of ML model (classification, regression, time_series)
        user_query: Specific user query or requirements for the model
    """
    try:
        logger.info(f"H2OGPTE Agent: Training model for {target_variable}")
        result = await h2ogpte_agent.train_model(
            dataset_description=dataset_description,
            target_variable=target_variable,
            model_type=model_type,
            user_query=user_query
        )
        return result
    except Exception as e:
        logger.error(f"Error in h2ogpte_train_model: {e}")
        return {
            "status": "error",
            "agent": "H2OGPTE ML Agent",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
async def h2ogpte_analyze_performance(
    model_results: Optional[Dict[str, Any]] = None,
    user_query: str = ""
) -> Dict[str, Any]:
    """Analyze ML model performance using H2OGPTE agent capabilities.
    
    Args:
        model_results: Optional model results to analyze
        user_query: Specific analysis requirements or questions
    """
    try:
        logger.info("H2OGPTE Agent: Analyzing model performance")
        result = await h2ogpte_agent.analyze_model_performance(
            model_results=model_results,
            user_query=user_query
        )
        return result
    except Exception as e:
        logger.error(f"Error in h2ogpte_analyze_performance: {e}")
        return {
            "status": "error",
            "agent": "H2OGPTE ML Agent",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
async def h2ogpte_optimize_features(
    feature_data: Dict[str, Any],
    user_query: str = ""
) -> Dict[str, Any]:
    """Optimize features for flood prediction using H2OGPTE agent.
    
    Args:
        feature_data: Feature data to optimize
        user_query: Specific optimization requirements
    """
    try:
        logger.info("H2OGPTE Agent: Optimizing features")
        result = await h2ogpte_agent.optimize_features(
            feature_data=feature_data,
            user_query=user_query
        )
        return result
    except Exception as e:
        logger.error(f"Error in h2ogpte_optimize_features: {e}")
        return {
            "status": "error",
            "agent": "H2OGPTE ML Agent",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
def h2ogpte_get_status() -> Dict[str, Any]:
    """Get H2OGPTE agent status, training history, and capabilities."""
    try:
        logger.info("H2OGPTE Agent: Getting status")
        status = h2ogpte_agent.get_agent_status()
        training_history = h2ogpte_agent.get_training_history()
        
        return {
            "status": "success",
            "agent": "H2OGPTE ML Agent",
            "agent_status": status,
            "training_history": training_history[-5:],  # Last 5 sessions
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error in h2ogpte_get_status: {e}")
        return {
            "status": "error",
            "agent": "H2OGPTE ML Agent",
            "message": str(e)
        }

# =============================================================================
# UNIFIED COORDINATION TOOLS
# =============================================================================

# Legacy helper intentionally not exposed through MCP.
async def comprehensive_flood_analysis(
    location: str = "Cameroon"
) -> Dict[str, Any]:
    """Run comprehensive flood analysis using all agents with actual data.

    Args:
        location: Location to analyze
    """
    try:
        logger.info(f"Running comprehensive flood analysis for {location}")

        actual_data = await build_cameroon_context(location)

        # Analyze with all agents using the actual data
        data_insights = await data_collector.analyze(actual_data)
        data_alerts = await data_collector.check_alerts(actual_data)

        risk_insights = await risk_analyzer.analyze(actual_data)
        risk_alerts = await risk_analyzer.check_alerts(actual_data)

        emergency_insights = await emergency_responder.analyze(actual_data)
        emergency_alerts = await emergency_responder.check_alerts(actual_data)

        prediction_insights = await predictor.analyze(actual_data)
        prediction_alerts = await predictor.check_alerts(actual_data)

        forecast = await predictor.generate_forecast(actual_data, 24)

        # Determine overall risk level from alerts
        all_alerts = data_alerts + risk_alerts + emergency_alerts + prediction_alerts
        critical_alerts = sum(1 for alert in all_alerts if alert.severity == "critical")
        warning_alerts = sum(1 for alert in all_alerts if alert.severity == "warning")

        if critical_alerts > 0:
            overall_risk_level = "CRITICAL"
        elif warning_alerts > 2:
            overall_risk_level = "HIGH"
        elif warning_alerts > 0:
            overall_risk_level = "MODERATE"
        else:
            overall_risk_level = "LOW"

        return {
            "status": "success",
            "location": location,
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
            "current_risk": _current_risk_assessment(actual_data),
            "data_collection": {
                "agent": "Data Collector",
                "data_sources": {
                    "cameroon_basins": len(actual_data["basins"]),
                    "rainfall_status": actual_data["recent_rainfall"]["status"],
                    "community_reports": len(actual_data["recent_community_reports"])
                },
                "location_context": actual_data,
                "insights": [{"title": i.title, "value": i.value, "trend": i.trend, "urgency": i.urgency} for i in data_insights],
                "alerts": [{"id": a.id, "title": a.title, "severity": a.severity} for a in data_alerts]
            },
            "risk_analysis": {
                "agent": "Risk Analyzer",
                "insights": [{"title": i.title, "value": i.value, "trend": i.trend, "urgency": i.urgency} for i in risk_insights],
                "alerts": [{"id": a.id, "title": a.title, "severity": a.severity} for a in risk_alerts]
            },
            "emergency_readiness": {
                "agent": "Emergency Responder",
                "insights": [{"title": i.title, "value": i.value, "trend": i.trend, "urgency": i.urgency} for i in emergency_insights],
                "alerts": [{"id": a.id, "title": a.title, "severity": a.severity} for a in emergency_alerts]
            },
            "ai_predictions": {
                "agent": "AI Predictor",
                "insights": [{"title": i.title, "value": i.value, "trend": i.trend, "urgency": i.urgency} for i in prediction_insights],
                "alerts": [{"id": a.id, "title": a.title, "severity": a.severity} for a in prediction_alerts]
            },
            "24h_forecast": forecast,
            "coordination_summary": {
                "overall_risk_level": overall_risk_level,
                "total_alerts": len(all_alerts),
                "critical_alerts": critical_alerts,
                "warning_alerts": warning_alerts,
                "immediate_actions_needed": critical_alerts + warning_alerts,
                "monitoring_status": "ACTIVE",
                "data_freshness": "CURRENT"
            }
        }
    except Exception as e:
        logger.error(f"Error in comprehensive_flood_analysis: {e}")
        return {
            "status": "error",
            "message": str(e)
        }

# Legacy helper intentionally not exposed through MCP.
def get_agent_capabilities() -> Dict[str, Any]:
    """Get information about all available agent capabilities."""
    return {
        "status": "success",
        "unified_server": "Flood Prediction Multi-Agent System",
        "agents": {
            "data_collector": {
                "name": "Data Collector",
                "description": "Reads current Cameroon basin risk, rainfall, and community reports",
                "capabilities": [
                    "Cameroon name and coordinate resolution",
                    "Open-Meteo rainfall snapshot for Cameroon basins",
                    "GloFAS discharge availability reporting",
                    "Community-report context"
                ],
                "tools": ["get_cameroon_flood_context", "generate_data_insights"]
            },
            "risk_analyzer": {
                "name": "Risk Analyzer", 
                "description": "AI-powered analysis of flood risk conditions",
                "capabilities": [
                    "Multi-factor risk assessment",
                    "Trend analysis",
                    "Critical threshold monitoring",
                    "Pattern anomaly detection"
                ],
                "tools": ["analyze_flood_risk", "calculate_risk_score"]
            },
            "emergency_responder": {
                "name": "Emergency Responder",
                "description": "Coordinates emergency response and alert management",
                "capabilities": [
                    "Emergency alert activation",
                    "Evacuation coordination", 
                    "Response team management",
                    "Communication system monitoring"
                ],
                "tools": ["assess_emergency_response", "activate_emergency_alert", "coordinate_evacuation"]
            },
            "predictor": {
                "name": "AI Predictor",
                "description": "Advanced AI forecasting and predictive analysis",
                "capabilities": [
                    "24-72 hour flood forecasting",
                    "Critical period prediction",
                    "Model accuracy assessment",
                    "Trend prediction"
                ],
                "tools": ["generate_flood_forecast", "analyze_prediction_accuracy", "predict_critical_conditions"]
            },
            "h2ogpte_agent": {
                "name": "H2OGPTE ML Agent",
                "description": "AutoML agent for training flood prediction models using H2OGPTE and Driverless AI platform",
                "capabilities": [
                    "AutoML model training with Driverless AI",
                    "Feature engineering optimization",
                    "Model performance analysis",
                    "ML pipeline recommendations",
                    "Flood prediction specific guidance",
                    "Time-series modeling expertise",
                    "Model interpretability analysis"
                ],
                "tools": ["h2ogpte_train_model", "h2ogpte_analyze_performance", "h2ogpte_optimize_features", "h2ogpte_get_status"]
            }
        },
        "unified_tools": ["comprehensive_flood_analysis", "get_agent_capabilities"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

if __name__ == "__main__":
    mcp.run(transport="sse", host="127.0.0.1", port=8001)
