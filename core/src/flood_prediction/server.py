import json
import os
import uuid
import jwt
import requests
import time
import asyncio
import aiohttp
import sys
import csv
import difflib
import math
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Annotated, Dict, Any, List

import rq
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Request,
    Response,
    UploadFile,
    File,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from rq.exceptions import InvalidJobOperationError
from pydantic import BaseModel
from .settings import settings, server_dir, log
from .settings import configure_logging, initialize_app
from . import db
from .api import llm_call, llm_call_stream, get_available_llm_models, get_provider_info, get_all_providers_info
from .evaluator import evaluator, EvaluationResult
from .data_sources import fetch_and_update_usgs_data, fetch_and_store_noaa_alerts
from .agents import AgentManager
from .agents.nat_base import FloodPredictionRunner

FAR_NORTH_DIVISIONS = ["Logone-et-Chari", "Mayo-Danay", "Diamaré", "Mayo-Sava", "Mayo-Tsanaga", "Mayo-Kani"]
# Only these localities have the complete environmental/risk pipeline.  This
# explicit set prevents arbitrary labels from the broad susceptibility cache
# (for example “Paris”) being accepted as a valid entity.
FAR_NORTH_COVERED_LOCALITIES = {
    "Blangoua", "Darak", "Datchéka", "Djarèngol", "Dougui", "Doukoula",
    "Gaklé", "Gobo", "Guémé", "Guéré", "Harde", "Hilé - Alifa", "Hina",
    "Kai-Kai", "Kar-Hay", "Kaélé", "Kolofata", "Kousséri", "Maga",
    "Makabaye", "Makary", "Maroua I", "Maroua II", "Mokolo", "Mora",
    "Moulvoudaye", "Mozogo", "Pouss", "Salak", "Tchatibali", "Vélé",
    "Wina", "Yagoua", "Zina",
}
CAMEROON_OUTSIDE_FAR_NORTH = {
    "garoua": "North Region",
    "lagdo": "North Region (Bénoué/Lagdo dam area)",
    "yaounde": "Centre Region",
    "douala": "Littoral Region",
}

# Optional Far North interim engine. It lives at repository root so it can also
# be used from scripts; expose it through the API without duplicating logic.
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
try:
    from farnorth_risk_engine import get_locality_risk as _get_farnorth_risk
    from farnorth_risk_engine import get_locality_risk_classifier as _get_farnorth_classifier
    from farnorth_risk_engine import get_forecasted_features as _get_farnorth_forecast
    from farnorth_risk_engine import _risk_cache as _get_farnorth_cache
    from farnorth_risk_engine import _catalogue as _get_farnorth_catalogue
    from farnorth_risk_engine import _read_parquet as _read_farnorth_parquet
    from farnorth_risk_engine import get_top_risk_localities as _get_farnorth_top_risk
    from farnorth_risk_engine import get_division_risk as _get_farnorth_division_risk
except Exception as _farnorth_import_error:
    _get_farnorth_risk = None
    _get_farnorth_classifier = None
    _get_farnorth_forecast = None
    _get_farnorth_cache = None
    _get_farnorth_catalogue = None
    _read_farnorth_parquet = None
    _get_farnorth_top_risk = None
    _get_farnorth_division_risk = None
    print(f"Far North risk engine unavailable: {_farnorth_import_error}")

configure_logging()
initialize_app()
# Set environment variable to fix fork() issues on macOS
os.environ.setdefault('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', 'YES')
# NAT workflow YAML files use NVIDIA_API_KEY, while this application keeps
# configuration under the APP_ prefix.  Make the configured key available to
# NAT before it loads a workflow (without replacing an explicitly supplied
# NVIDIA_API_KEY).
if settings.nvidia_api_key:
    os.environ.setdefault('NVIDIA_API_KEY', settings.nvidia_api_key)

# Redis and job queue setup
_redis = Redis.from_url(settings.redis_url)
_job_queue = rq.Queue(connection=_redis, default_timeout=settings.job_timeout)

# Database setup
_db_path = Path(settings.app_data_dir) / "flood_prediction.db"
# The risk engine is usable without the application database.  This opt-out is
# useful for the local demo when PostgreSQL/PostGIS is unavailable.
if os.environ.get("APP_SKIP_DB_INIT", "0") != "1":
    db.init_app_db(str(_db_path))

# Initialize Agent Manager
_agent_manager = None
if settings.agents_enabled and os.environ.get("APP_SKIP_DB_INIT", "0") != "1":
    _agent_manager = AgentManager(str(_db_path))
    log.info("AgentManager initialized")

# Initialize NAT Agent Runner
_nat_runner = None
try:
    _nat_runner = FloodPredictionRunner()
    log.info("NAT FloodPredictionRunner initialized")
except Exception as e:
    log.warning(f"NAT FloodPredictionRunner not available: {e}")

# Lightweight per-user assistant context.  The frontend may send context on
# each request, but keeping the last verified prediction server-side also
# makes a page reload/follow-up (for example, “Why?”) deterministic.  Only
# structured, backend-derived fields are retained; raw prompts and secrets are
# never stored here.  This is intentionally bounded for the local deployment.
_assistant_session_context: Dict[str, Dict[str, Any]] = {}
_ASSISTANT_SESSION_LIMIT = 512


def _assistant_context_for(user_id: str, supplied: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    key = str(user_id or "anonymous")
    merged = dict(_assistant_session_context.get(key, {}))
    if isinstance(supplied, dict):
        merged.update(supplied)
    return merged


def _remember_assistant_context(user_id: str, routed: Optional[Dict[str, Any]]) -> None:
    if not isinstance(routed, dict):
        return
    update = routed.get("conversation_context")
    if not isinstance(update, dict):
        return
    key = str(user_id or "anonymous")
    _assistant_session_context[key] = update
    if len(_assistant_session_context) > _ASSISTANT_SESSION_LIMIT:
        oldest = next(iter(_assistant_session_context))
        _assistant_session_context.pop(oldest, None)

# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    log.info("Application starting up...")
    
    # Start AI agents if enabled and auto-start is configured
    if _agent_manager and settings.agents_auto_start:
        try:
            log.info("Auto-starting AI agents...")
            await _agent_manager.start_all_agents()
            log.info("All AI agents started successfully")
        except Exception as e:
            log.error(f"Failed to auto-start AI agents: {str(e)}")
    
    # Generate initial insights if agent manager is available
    if _agent_manager:
        try:
            log.info("Generating initial agent insights...")
            await _agent_manager._generate_initial_insights()
            log.info("Initial agent insights generated successfully")
        except Exception as e:
            log.error(f"Failed to generate initial agent insights: {str(e)}")
    
    yield
    
    # Shutdown
    log.info("Application shutting down...")
    
    # Stop AI agents if running
    if _agent_manager:
        try:
            log.info("Stopping AI agents...")
            await _agent_manager.stop_all_agents()
            log.info("All AI agents stopped successfully")
        except Exception as e:
            log.error(f"Failed to stop AI agents: {str(e)}")

app = FastAPI(title="Generic API Server", version="1.0.0", lifespan=lifespan)
security = HTTPBearer()

@app.middleware("http")
async def enforce_utf8_responses(request: Request, call_next):
    """Keep API/UI encoding explicit end-to-end for accented place names."""
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if (content_type.startswith("application/json") or content_type.startswith("text/")) and "charset=" not in content_type.lower():
        response.headers["content-type"] = f"{content_type}; charset=utf-8"
    return response

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing and logging middleware
# @app.middleware("http")
# async def logging_middleware(request: Request, call_next):
#     start_time = time.time()
    
#     # Log request start
#     log.info("Request started", extra={
#         "method": request.method,
#         "url": str(request.url),
#         "client_ip": request.client.host if request.client else "unknown",
#         "user_agent": request.headers.get("user-agent", ""),
#         "request_id": str(uuid.uuid4())[:8],
#     })
    
#     # Process request
#     try:
#         response = await call_next(request)
        
#         # Calculate duration
#         process_time = time.time() - start_time
#         duration_ms = round(process_time * 1000, 2)
        
#         # Log request completion
#         log.info("Request completed", extra={
#             "method": request.method,
#             "url": str(request.url),
#             "status_code": response.status_code,
#             "duration_ms": duration_ms,
#             "client_ip": request.client.host if request.client else "unknown",
#         })
        
#         # Add timing header
#         response.headers["X-Process-Time"] = str(process_time)
        
#         return response
        
#     except Exception as e:
#         # Calculate duration for failed requests
#         process_time = time.time() - start_time
#         duration_ms = round(process_time * 1000, 2)
        
#         # Log request error
#         log.error("Request failed", extra={
#             "method": request.method,
#             "url": str(request.url),
#             "duration_ms": duration_ms,
#             "error": str(e),
#             "client_ip": request.client.host if request.client else "unknown",
#         })
        
#         raise e

# Cache for JWKS (JSON Web Key Set)
_jwks_cache: Dict = {}


# =============================================================================
# Authentication
# =============================================================================

async def get_jwks():
    """Fetch JSON Web Key Set from the OIDC provider"""
    if not _jwks_cache.get("keys"):
        jwks_uri = f"{settings.oidc_authority}/.well-known/openid-configuration"
        try:
            openid_config = requests.get(jwks_uri).json()
            jwks_url = openid_config.get("jwks_uri")
            if jwks_url:
                jwks = requests.get(jwks_url).json()
                _jwks_cache["keys"] = jwks.get("keys", [])
        except Exception as e:
            print(f"Error fetching JWKS: {e}")
    return _jwks_cache.get("keys", [])


def get_token_endpoint(auth_url: str) -> str:
    """Get token endpoint from OIDC discovery"""
    try:
        discovery_url = f"{auth_url}/.well-known/openid-configuration"
        response = requests.get(discovery_url)
        return response.json().get("token_endpoint")
    except Exception:
        return f"{auth_url}/oauth/token"


async def refresh_access_token(user_id: str) -> Optional[str]:
    """Attempt to refresh the access token using the stored refresh token"""
    refresh_token = _redis.get(f"refresh_token:{user_id}")
    if not refresh_token:
        print(f"No refresh token found for user {user_id}")
        return None

    try:
        refresh_token = refresh_token.decode('utf-8')
        token_endpoint = get_token_endpoint(settings.oidc_authority)

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.oidc_client_id,
        }

        if settings.oidc_client_secret:
            data["client_secret"] = settings.oidc_client_secret

        response = requests.post(token_endpoint, headers=headers, data=data)
        if response.status_code == 200:
            token_data = response.json()
            if "access_token" in token_data:
                # Store the new access token
                expires_in = token_data.get("expires_in", 300)
                access_token = token_data["access_token"]
                _redis.setex(f"access_token:{user_id}", expires_in, access_token)

                # Update refresh token if provided
                if "refresh_token" in token_data:
                    _redis.setex(f"refresh_token:{user_id}", 86400, token_data["refresh_token"])

                print(f"Successfully refreshed access token for user {user_id}")
                return access_token

        print(f"Failed to refresh token: {response.status_code}, {response.text}")
        return None
    except Exception as e:
        print(f"Error refreshing token: {str(e)}")
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> str:
    """Validate JWT token or extract user identifier from request headers with auto-refresh"""
    token = credentials.credentials if credentials else None

    if settings.oidc_authority == "":  # local development mode
        # The local frontend uses a fixed development bearer token.  The
        # identity header is accepted only in this explicit local profile so
        # separate local citizens still get separate records; it is never a
        # substitute for a production JWT.
        if token == "local-token":
            header_user = request.headers.get("X-User-Id") or request.headers.get("X-User-Email")
            identity = header_user.strip() if header_user and header_user.strip() else "local-user"
            if identity != "local-user" and not db.is_user_active(identity):
                raise HTTPException(status_code=403, detail="This account has been deactivated")
            return identity
        raise HTTPException(status_code=401, detail="Missing or invalid local token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    try:
        # Simple decode without verification (for development)
        # In production, you should properly verify the token signature
        decoded = jwt.decode(token, options={"verify_signature": False})

        # Extract user identifier
        user_id = decoded.get(settings.oidc_user_id_claim)
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid token: missing {settings.oidc_user_id_claim} claim"
            )

        roles = decoded.get("roles") or decoded.get("role") or decoded.get("groups") or []
        if isinstance(roles, str):
            roles = [roles]
        request.state.auth_role = next((str(r).lower() for r in roles if str(r).lower() in {"admin", "administrator"}), None)

        # Store the token temporarily
        _redis.setex(f"access_token:{user_id}", 300, token)
        return user_id

    except jwt.ExpiredSignatureError:
        try:
            decoded = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
            user_id = decoded.get(settings.oidc_user_id_claim)

            if user_id:
                print(f"Token expired for user {user_id}, attempting refresh")
                new_token = await refresh_access_token(user_id)
                if new_token:
                    return user_id
        except Exception as e:
            print(f"Error handling expired token: {str(e)}")

        raise HTTPException(status_code=401, detail="Token has expired and refresh failed")

    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def _require_authenticated_identity(user_id: str) -> str:
    """Reject the anonymous local development principal on private APIs.

    Public Far North assessment endpoints intentionally work without login,
    while citizen records and the assistant require an identity.  The local
    frontend sends X-User-Id after sign-in; without it the fixed development
    token is only an anonymous public session.
    """
    clean = str(user_id or "").strip()
    if not clean or clean == "local-user":
        raise HTTPException(status_code=401, detail="Sign in is required for this citizen workspace")
    return clean


# Define the dependency for getting authenticated user ID
UserID = Annotated[str, Depends(get_current_user)]


# =============================================================================
# Utility Functions
# =============================================================================

def _api(url: str) -> str:
    """Helper to construct API URLs"""
    return f"{settings.base_url}api/{url}"


def _format_utc(dt: datetime) -> str:
    """Format datetime as UTC string"""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def uid() -> str:
    """Generate a unique ID"""
    return str(uuid.uuid4())


def get_user_access_token(user_id: str) -> Optional[bytes]:
    """Get stored access token for user"""
    return _redis.get(f"access_token:{user_id}")


def get_user_refresh_token(user_id: str) -> Optional[bytes]:
    """Get stored refresh token for user"""
    return _redis.get(f"refresh_token:{user_id}")


# =============================================================================
# Background Job Processing
# =============================================================================

class JobContext:
    """Context manager for background jobs"""
    def __init__(self, job: Optional[rq.job.Job] = None):
        self.job = job or rq.get_current_job()
        self._last_checkpoint_time = datetime.now()

    @property
    def status(self) -> Optional[str]:
        return self.job.get_meta(refresh=True).get("status")

    @status.setter
    def status(self, message: str):
        print(f"Job status: {message}")
        self.job.meta["status"] = message
        self.job.save_meta()

    @property
    def aborted(self) -> bool:
        return self.job.get_meta(refresh=True).get("abort") == 1

    def abort(self):
        self.job.meta["abort"] = 1
        self.job.save_meta()

    def checkpoint(self):
        """Check if job should be aborted"""
        now = datetime.now()
        if (now - self._last_checkpoint_time).total_seconds() > 5:
            self._last_checkpoint_time = now
            if self.aborted:
                raise Exception("Job was aborted")

    def delete(self):
        self.job.delete()


def sample_background_task(user_id: str, task_data: Dict[str, Any]):
    """Sample background task - customize this for your needs"""
    ctx = JobContext()
    try:
        ctx.status = "Starting task..."
        
        # Simulate some work
        import time
        for i in range(10):
            ctx.checkpoint()  # Check for abort
            time.sleep(1)
            ctx.status = f"Processing step {i+1}/10"
        
        ctx.status = "Task completed successfully"
        return {"result": "success", "processed_data": task_data}
        
    except Exception as e:
        ctx.status = f"Task failed: {str(e)}"
        raise e


def update_flood_data_task(user_id: str = "system", site_codes: Optional[List[str]] = None):
    """Background task to update flood prediction data for Cameroon basins"""
    ctx = JobContext()
    try:
        ctx.status = "Starting Cameroon data ingestion..."
        
        from .db import (get_basins_with_centroids, get_recent_community_reports,
                         get_session, get_rainfall_two_day_total,
                         get_upstream_propagation_signals, record_basin_rainfall)
        from .models import CommunityReport, RiverBasin, RiskTrend
        from .agents.data_collector import DataCollectorAgent
        from .data_sources import calculate_calibrated_basin_risk, calculate_trend
        from sqlalchemy import select, func
        
        basins = get_basins_with_centroids()
        if not basins:
            ctx.status = "No basins found to update."
            return {"success": False, "message": "No basins found"}
            
        collector = DataCollectorAgent()
        
        # Collect rainfall
        ctx.status = "Fetching rainfall from Open-Meteo..."
        rainfall_map = {}
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            rainfall_map = loop.run_until_complete(collector.collect_openmeteo_rainfall(basins))
            loop.close()
            log.info(f"Successfully collected rainfall for {len(rainfall_map)} basins")
        except Exception as rain_err:
            log.error(f"Failed to fetch rainfall: {rain_err}")
            
        # Collect GloFAS discharge
        ctx.status = "Checking GloFAS discharge status..."
        discharge_map = {}
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            discharge_map = loop.run_until_complete(collector.collect_glofas_discharge(basins))
            loop.close()
            log.info(f"Successfully checked discharge for {len(discharge_map)} basins")
        except Exception as disch_err:
            log.error(f"Failed to fetch GloFAS discharge: {disch_err}")
            
        # Count community reports
        ctx.status = "Counting community reports..."
        comm_counts = {}
        try:
            with get_session() as session:
                stmt = select(CommunityReport.basin_id, func.count(CommunityReport.id)).group_by(CommunityReport.basin_id)
                for basin_id, count in session.execute(stmt).all():
                    if basin_id:
                        comm_counts[basin_id] = count
        except Exception as comm_err:
            log.error(f"Failed to count community reports: {comm_err}")
            
        # Update each basin
        ctx.status = "Updating basins in database..."
        updated_count = 0
        with get_session() as session:
            risk_date = datetime.now(timezone.utc).date()
            # Persist every basin's daily rainfall before scoring: a basin can
            # be upstream of one evaluated later in this same ingestion run.
            for b in basins:
                record_basin_rainfall(session, b["id"], risk_date,
                                      rainfall_map.get(b["id"], 0.0))
            session.flush()
            for b in basins:
                basin_id = b["id"]
                
                # If site_codes is provided, filter only to those basin IDs (or hybas_id strings)
                if site_codes and str(basin_id) not in site_codes and b["hybas_id"] not in site_codes:
                    continue
                    
                rain_val = rainfall_map.get(basin_id, 0.0)
                disch_info = discharge_map.get(basin_id, {
                    "discharge_cms": None,
                    "discharge_status": "unavailable",
                    "discharge_source": "none"
                })
                comm_count = comm_counts.get(basin_id, 0)
                
                basin_obj = session.get(RiverBasin, basin_id)
                if not basin_obj:
                    continue
                two_day_rainfall = get_rainfall_two_day_total(session, basin_id, risk_date)
                upstream_signals = get_upstream_propagation_signals(session, basin_id, risk_date)
                # Calculate risk from local rainfall, configured upstream flow,
                # discharge and reports; no single signal replaces the others.
                risk = calculate_calibrated_basin_risk(
                    rainfall_mm=rain_val,
                    rainfall_two_day_mm=two_day_rainfall,
                    community_count=comm_count,
                    discharge_cms=disch_info["discharge_cms"],
                    discharge_status=disch_info["discharge_status"],
                    flood_stage_cms=b["flood_stage_cms"],
                    local_daily_threshold_mm=basin_obj.local_rainfall_threshold_mm,
                    local_two_day_threshold_mm=basin_obj.two_day_rainfall_threshold_mm,
                    upstream_propagation_active=bool(upstream_signals),
                    upstream_sources=upstream_signals,
                )
                if basin_obj:
                    prev_flow = basin_obj.current_streamflow_cms or 0.0
                    current_flow = disch_info["discharge_cms"] if disch_info["discharge_cms"] is not None else 0.0
                    trend, rate = calculate_trend(current_flow, prev_flow, 1.0)
                    
                    basin_obj.current_streamflow_cms = current_flow
                    basin_obj.current_risk_level = risk.risk_level
                    basin_obj.risk_score = risk.risk_score
                    basin_obj.risk_source = risk.risk_source
                    basin_obj.trigger_reasons = json.dumps(risk.trigger_reasons)
                    basin_obj.trend = trend
                    basin_obj.trend_rate_cms_per_hour = rate
                    basin_obj.discharge_cms = disch_info["discharge_cms"]
                    basin_obj.discharge_status = disch_info["discharge_status"]
                    basin_obj.discharge_source = disch_info["discharge_source"]
                    basin_obj.data_completeness = risk.data_completeness
                    basin_obj.missing_inputs = json.dumps(risk.missing_inputs)
                    basin_obj.last_api_update = datetime.now(timezone.utc)
                    basin_obj.last_updated = datetime.now(timezone.utc)
                    
                    # Also insert into RiskTrend table
                    session.add(RiskTrend(
                        basin_id=basin_id,
                        risk_score=risk.risk_score,
                        streamflow_cms=current_flow,
                        timestamp=datetime.now(timezone.utc)
                    ))
                    
                    updated_count += 1
                    
        ctx.checkpoint()
        
        results = {"success": True, "updated_count": updated_count, "message": f"Successfully updated {updated_count} Cameroon basins"}
        ctx.status = results["message"]
        log.info("Cameroon flood data update job completed", **results)
        return results
        
    except Exception as e:
        error_msg = f"Cameroon data update task failed: {str(e)}"
        ctx.status = error_msg
        log.error("Cameroon data update task error", error=str(e))
        raise Exception(error_msg)



# =============================================================================
# API Models
# =============================================================================

class JobRequest(BaseModel):
    """Request model for creating a job"""
    name: str
    data: Dict[str, Any] = {}


class JobResponse(BaseModel):
    """Response model for job creation"""
    job_id: str


class Job(BaseModel):
    """Job status model"""
    id: str
    state: str
    aborted: bool
    name: str
    status: Optional[str] = None
    enqueued_at: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


class JobListResponse(BaseModel):
    """Response model for job list"""
    jobs: list[Job]


class JobUpdateRequest(BaseModel):
    """Request model for updating a job"""
    name: Optional[str] = None
    priority: Optional[int] = None


class RefreshTokenRequest(BaseModel):
    """Request model for refresh token"""
    refresh_token: str


class LocalLoginRequest(BaseModel):
    identifier: str
    password: str


class LogEntry(BaseModel):
    """Frontend log entry"""
    timestamp: str
    level: str
    message: str
    data: Optional[Dict[str, Any]] = None
    component: Optional[str] = None
    userId: Optional[str] = None
    sessionId: Optional[str] = None
    duration: Optional[float] = None
    url: Optional[str] = None
    userAgent: Optional[str] = None


class AnalyticsEvent(BaseModel):
    """Analytics event from frontend"""
    event_type: str
    event_data: Dict[str, Any]
    timestamp: str
    userId: Optional[str] = None
    sessionId: Optional[str] = None


# =============================================================================
# Dashboard Models  
# =============================================================================

class DashboardSummary(BaseModel):
    """Dashboard summary statistics"""
    total_watersheds: int
    active_alerts: int
    high_risk_watersheds: int
    moderate_risk_watersheds: int
    low_risk_watersheds: int
    discharge_unavailable: bool = False
    last_updated: str


class Watershed(BaseModel):
    """Watershed information"""
    id: int
    name: str
    region: Optional[str] = "Cameroon"
    region_code: Optional[str] = "CM"
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    basin_size_sqkm: Optional[float] = None
    current_streamflow_cms: float
    current_risk_level: str
    risk_score: float
    local_rainfall_threshold_mm: Optional[float] = None
    two_day_rainfall_threshold_mm: Optional[float] = None
    risk_source: Optional[str] = "none"
    trigger_reasons: Optional[List[str]] = []
    flood_stage_cms: Optional[float] = None
    trend: Optional[str] = None
    trend_rate_cms_per_hour: Optional[float] = None
    discharge_cms: Optional[float] = None
    discharge_status: Optional[str] = "unavailable"
    discharge_source: Optional[str] = "none"
    data_completeness: Optional[str] = "partial"
    missing_inputs: Optional[List[str]] = []
    last_updated: str


class Alert(BaseModel):
    """Alert information"""
    alert_id: int
    alert_type: str
    watershed: str
    message: str
    severity: str
    issued_time: str
    expires_time: Optional[str] = None
    affected_counties: Optional[List[str]] = None
    data_source: Optional[str] = "sample"


class RiskTrendPoint(BaseModel):
    """Risk trend data point"""
    time: str
    risk: float
    watersheds: int


class DashboardData(BaseModel):
    """Complete dashboard data"""
    summary: DashboardSummary
    watersheds: List[Watershed]
    alerts: List[Alert]
    risk_trends: List[RiskTrendPoint]


# =============================================================================
# Helper Functions
# =============================================================================

def _make_job_id(user_id: str, job_id: str) -> str:
    """Create a composite job ID that includes the user ID"""
    return f"{user_id}/{job_id}"


def _parse_job_id(composite_id: str) -> tuple[str, str]:
    """Parse composite job ID to extract user ID and job ID"""
    user_id, job_id = composite_id.split("/", maxsplit=1)
    return user_id, job_id


def _is_job_owned_by(composite_id: str, expected_user_id: str) -> bool:
    """Check if a job is owned by the expected user"""
    user_id, _ = _parse_job_id(composite_id)
    return user_id == expected_user_id


def _to_job_status(job: rq.job.Job) -> Job:
    """Convert RQ job to our Job model"""
    meta = job.get_meta()
    _, job_id = _parse_job_id(job.id)
    return Job(
        id=job_id,
        state=job.get_status(),
        aborted=meta.get("abort") == 1,
        name=meta.get("name", "Unknown"),
        status=meta.get("status"),
        enqueued_at=_format_utc(job.enqueued_at) if job.enqueued_at else None,
        started_at=_format_utc(job.started_at) if job.started_at else None,
        ended_at=_format_utc(job.ended_at) if job.ended_at else None,
    )


# =============================================================================
# API Endpoints
# =============================================================================

@app.get(_api("config"))
async def get_config():
    config = dict(
        oidc_authority=settings.oidc_authority,
        oidc_client_id=settings.oidc_client_id,
        oidc_client_secret=settings.oidc_client_secret,
        oidc_scope=settings.oidc_scope,
        base_url=settings.base_url,
    )

    headers = {
        "Cache-Control": "no-store, max-age=0",
        "Content-Type": "application/json",
    }

    return Response(
        content=json.dumps(config), media_type="application/json", headers=headers
    )


@app.post(_api("logs"))
async def receive_frontend_logs(request: LogEntry):
    """Receive logs from frontend"""
    try:
        # Log frontend entry with backend logger
        log_level = getattr(log, request.level.lower(), log.info)
        log_level(f"Frontend: {request.message}", extra={
            "component": request.component,
            "user_id": request.userId,
            "session_id": request.sessionId,
            "frontend_url": request.url,
            "duration_ms": request.duration,
            "frontend_data": request.data,
            "source": "frontend"
        })
        
        # Store in Redis for real-time monitoring (optional)
        if settings.enable_metrics:
            log_key = f"frontend_logs:{request.sessionId}"
            _redis.lpush(log_key, json.dumps(request.dict()))
            _redis.expire(log_key, 3600)  # Keep for 1 hour
            
        return {"status": "logged"}
        
    except Exception as e:
        log.error(f"Failed to process frontend log: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process log")


@app.post(_api("analytics"))
async def receive_analytics(request: AnalyticsEvent):
    """Receive analytics events from frontend"""
    try:
        # Log analytics event
        log.info(f"Analytics: {request.event_type}", extra={
            "user_id": request.userId,
            "session_id": request.sessionId,
            "event_data": request.event_data,
            "source": "frontend_analytics"
        })
        
        # Store analytics data (you might want to use a dedicated analytics service)
        if settings.enable_metrics:
            analytics_key = f"analytics:{request.event_type}"
            _redis.lpush(analytics_key, json.dumps(request.dict()))
            _redis.expire(analytics_key, 86400)  # Keep for 24 hours
            
        return {"status": "tracked"}
        
    except Exception as e:
        log.error(f"Failed to process analytics event: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process analytics")


@app.post(_api("auth/local-login"))
async def local_login(payload: LocalLoginRequest):
    """Authenticate locally managed accounts updated from the admin panel."""
    if not payload.identifier.strip() or not payload.password:
        return JSONResponse({"detail": "identifier and password are required"}, status_code=422)
    account = await asyncio.to_thread(db.authenticate_local_user, payload.identifier, payload.password)
    if account is None:
        known = await asyncio.to_thread(db.local_account_exists, payload.identifier)
        return JSONResponse({"detail": "Invalid username/email or password"}, status_code=401 if known else 404)
    return {"user": account}


@app.post(_api("auth/refresh"))
async def refresh_token(
    user_id: UserID,
    request: RefreshTokenRequest,
):
    """Store and use refresh token to get new access token"""
    refresh_token = request.refresh_token
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Missing refresh token")

    # Store refresh token
    _redis.setex(f"refresh_token:{user_id}", 86400, refresh_token)
    print(f"Stored refresh token for user {user_id}")

    try:
        token_endpoint = get_token_endpoint(settings.oidc_authority)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.oidc_client_id,
        }

        if settings.oidc_client_secret:
            data["client_secret"] = settings.oidc_client_secret

        response = requests.post(token_endpoint, headers=headers, data=data)
        if response.status_code == 200:
            token_data = response.json()
            if "access_token" in token_data:
                expires_in = token_data.get("expires_in", 300)
                _redis.setex(
                    f"access_token:{user_id}", 
                    expires_in,
                    token_data["access_token"]
                )

                if "refresh_token" in token_data:
                    _redis.setex(
                        f"refresh_token:{user_id}", 
                        86400,
                        token_data["refresh_token"]
                    )

                return {"status": "success", "message": "Tokens refreshed successfully"}

        print(f"Failed to refresh token: {response.status_code}")
    except Exception as e:
        print(f"Error refreshing token: {str(e)}")

    return {"status": "stored", "message": "Refresh token stored"}


@app.post(_api("jobs"), response_model=JobResponse)
async def create_job(user_id: UserID, request: JobRequest):
    """Create a new background job"""
    job_id = _make_job_id(user_id, uid())
    
    meta = {"name": request.name}
    
    _job_queue.enqueue(
        sample_background_task,
        job_id=job_id,
        timeout=-1,  # No timeout
        ttl=604800,  # 1 week TTL
        failure_ttl=604800,  # 1 week failure TTL
        meta=meta,
        kwargs={
            "user_id": user_id,
            "task_data": request.data,
        },
    )
    
    _, simple_job_id = _parse_job_id(job_id)
    return JobResponse(job_id=simple_job_id)


@app.get(_api("jobs"), response_model=JobListResponse)
async def list_jobs(user_id: UserID):
    """Get all jobs for the current user"""
    # Get jobs from different registries
    started_job_ids = _job_queue.started_job_registry.get_job_ids()
    failed_job_ids = _job_queue.failed_job_registry.get_job_ids()
    queued_job_ids = _job_queue.job_ids
    finished_job_ids = _job_queue.finished_job_registry.get_job_ids()
    
    all_ids = started_job_ids + failed_job_ids + queued_job_ids + finished_job_ids
    
    # Filter jobs owned by current user
    job_ids = [job_id for job_id in all_ids if _is_job_owned_by(job_id, user_id)]
    jobs = [_job_queue.fetch_job(job_id) for job_id in job_ids if _job_queue.fetch_job(job_id)]
    
    return JobListResponse(jobs=[_to_job_status(job) for job in jobs])


@app.get(_api("jobs/{job_id}"), response_model=Job)
async def get_job(user_id: UserID, job_id: str):
    """Get a specific job by ID"""
    full_job_id = _make_job_id(user_id, job_id)
    job = _job_queue.fetch_job(full_job_id)
    
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return _to_job_status(job)


@app.patch(_api("jobs/{job_id}"))
async def update_job(user_id: UserID, job_id: str, request: JobUpdateRequest):
    """Update job metadata"""
    full_job_id = _make_job_id(user_id, job_id)
    job = _job_queue.fetch_job(full_job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Update job metadata
    if request.name is not None:
        job.meta["name"] = request.name
        job.save_meta()
    
    return {"status": "success", "message": "Job updated"}


@app.delete(_api("jobs/{job_id}"))
async def delete_job(user_id: UserID, job_id: str):
    """Delete a job"""
    full_job_id = _make_job_id(user_id, job_id)
    job = _job_queue.fetch_job(full_job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    status = job.get_status()
    if status == "started":
        # Abort running job
        JobContext(job).abort()
        return {"status": "success", "message": "Job aborted"}
    
    try:
        job.delete()
        return {"status": "success", "message": "Job deleted"}
    except InvalidJobOperationError as e:
        message = f"Failed deleting job: {e}"
        print(message)
        raise HTTPException(status_code=500, detail=message)


# =============================================================================
# AI Chat API Models
# =============================================================================

class ChatMessage(BaseModel):
    """Chat message model"""
    message: str
    watershed_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None
    use_agent: bool = False
    model: Optional[str] = None

class ChatResponse(BaseModel):
    """AI chat response model"""
    response: str
    confidence: float
    recommendations: List[str] = []
    timestamp: str

# =============================================================================
# NAT Agent Chat API Models
# =============================================================================

class NATChatMessage(BaseModel):
    """NAT agent chat message model"""
    message: str
    agent_type: str = "risk_analyzer"  # data_collector, risk_analyzer, emergency_responder, predictor, all
    location: Optional[str] = "Cameroon"
    forecast_hours: Optional[int] = 24
    scenario: Optional[str] = "routine_check"
    custom_prompt: Optional[str] = None
    # Conversation state is intentionally carried into the shared router so
    # questions such as “should I evacuate?” can use the risk value just shown.
    context: Optional[Dict[str, Any]] = None

class NATChatResponse(BaseModel):
    """NAT agent chat response model"""
    output: str
    agent_type: str
    status: str
    logs: List[Dict[str, Any]] = []
    timestamp: str

class FarNorthRiskRequest(BaseModel):
    locality: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    division: Optional[str] = None
    date: Optional[str] = None

# =============================================================================
# Analytics API Models
# =============================================================================

class AnalyticsTimeRange(BaseModel):
    """Analytics time range request"""
    range: str = "7d"  # 7d, 30d, 90d
    metric: str = "risk_score"  # risk_score, flow, alerts

class HistoricalDataPoint(BaseModel):
    """Historical data point"""
    date: str
    time: str
    avg_risk_score: float
    avg_flow: float
    high_risk_count: int
    alerts_count: int

class RiskDistribution(BaseModel):
    """Risk distribution data"""
    name: str
    value: int
    color: str
    percentage: int

class WatershedComparison(BaseModel):
    """Watershed comparison data"""
    name: str
    risk_score: float
    flow_ratio: float
    current_flow: float

class FlowComparison(BaseModel):
    """Flow vs flood stage comparison"""
    name: str
    current_flow: float
    flood_stage: float
    capacity_used: float

class AnalyticsData(BaseModel):
    """Complete analytics data"""
    summary: Dict[str, Any]
    historical_data: List[HistoricalDataPoint]
    risk_distribution: List[RiskDistribution]
    watershed_comparison: List[WatershedComparison]
    flow_comparison: List[FlowComparison]

# =============================================================================
# Region API Models
# =============================================================================

class Region(BaseModel):
    """Region information"""
    code: str
    name: str
    description: str
    center_lat: float
    center_lng: float
    zoom: int
    watershed_count: int

# =============================================================================
# Dashboard API Endpoints
# =============================================================================

@app.get(_api("farnorth/localities"))
async def get_farnorth_localities():
    """Return the compact Far North locality index for autocomplete."""
    if _get_farnorth_cache is None:
        raise HTTPException(status_code=503, detail="Far North risk engine unavailable")
    try:
        cache = _get_farnorth_cache()
        return {"region": "Far North", "localities": sorted(cache.index.astype(str).tolist()), "count": int(len(cache))}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Far North locality cache unavailable: {exc}")

@app.get(_api("farnorth/top-risk"))
async def get_farnorth_top_risk(n: int = 5, division: Optional[str] = None):
    """Return static susceptibility ranking, explicitly not live conditions."""
    if _get_farnorth_top_risk is None:
        raise HTTPException(status_code=503, detail="Far North risk engine unavailable")
    try:
        return await asyncio.to_thread(_get_farnorth_top_risk, max(1, min(int(n), 20)), division)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Far North ranking unavailable: {exc}")

@app.post(_api("farnorth/division-risk"))
async def get_farnorth_division_risk(request: FarNorthRiskRequest):
    """Assess a whole division using the maximum covered-locality risk."""
    if _get_farnorth_division_risk is None:
        raise HTTPException(status_code=503, detail="Far North division risk unavailable")
    if not request.division:
        raise HTTPException(status_code=422, detail="Provide a division")
    try:
        return await asyncio.to_thread(_get_farnorth_division_risk, request.division)
    except Exception as exc:
        log.exception("Far North division risk evaluation failed")
        raise HTTPException(status_code=503, detail=f"Division risk unavailable: {exc}")

@app.get(_api("farnorth/gazetteer/search"))
async def search_farnorth_gazetteer(q: str = "", limit: int = 12):
    """Search all Far North gazetteer names and expose coverage status.

    The risk cache contains the full gazetteer, while the environmental
    subsets identify the smaller set with complete model coverage.  Returning
    both lets the UI disclose a nearest-covered substitution explicitly.
    """
    gazetteer = _repo_root.parent / "boundaries-data" / "gazetteer_farnorth.csv"
    if not gazetteer.exists():
        raise HTTPException(status_code=503, detail="Far North gazetteer unavailable")
    query = q.strip().casefold()
    try:
        with gazetteer.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        covered = set()
        subset = _repo_root / "data_quality" / "farnorth_consolidation" / "locality_subsets" / "chirps_34.parquet"
        if _read_farnorth_parquet is not None and subset.exists():
            covered = set(_read_farnorth_parquet(subset, columns=["name"])["name"].dropna().astype(str))
        def score(row):
            name = str(row.get("name", ""))
            if not query: return 1.0
            n = name.casefold()
            if query in n: return 1.0 - (len(n) - len(query)) / max(1, len(n))
            return difflib.SequenceMatcher(None, query, n).ratio()
        matches = sorted(rows, key=score, reverse=True)[:max(1, min(limit, 50))]
        return {"query": q, "count": len(rows), "covered_count": len(covered), "suggestions": [
            {"name": r.get("name"), "division": r.get("division"), "lat": float(r["lat"]), "lon": float(r["lon"]), "covered": r.get("name") in covered, "score": round(score(r), 4)}
            for r in matches if r.get("name")
        ]}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Far North gazetteer search unavailable: {exc}")

@app.post(_api("farnorth/resolve"))
async def resolve_farnorth_location(request: FarNorthRiskRequest):
    """Resolve a gazetteer place to itself or the nearest covered locality."""
    if not request.locality:
        raise HTTPException(status_code=422, detail="Provide a locality")
    gazetteer = _repo_root.parent / "boundaries-data" / "gazetteer_farnorth.csv"
    subset = _repo_root / "data_quality" / "farnorth_consolidation" / "locality_subsets" / "chirps_34.parquet"
    if _read_farnorth_parquet is None or not gazetteer.exists() or not subset.exists():
        raise HTTPException(status_code=503, detail="Far North location resolver unavailable")
    def key(v):
        import unicodedata, re
        return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode().casefold())
    with gazetteer.open(newline="", encoding="utf-8") as fh: rows = list(csv.DictReader(fh))
    target = next((r for r in rows if key(r.get("name")) == key(request.locality)), None)
    if target is None:
        names = [str(r.get("name", "")) for r in rows]
        close = difflib.get_close_matches(request.locality, names, n=1, cutoff=.55)
        target = next((r for r in rows if r.get("name") == close[0]), None) if close else None
    if target is None: raise HTTPException(status_code=404, detail=f"Unknown Far North place: {request.locality}")
    covered_df = _read_farnorth_parquet(subset, columns=["name", "lat", "lon"]).drop_duplicates("name")
    if target["name"] in set(covered_df["name"]):
        return {"requested_name": target["name"], "resolved_name": target["name"], "covered": True, "distance_km": 0.0, "disclosure": None}
    lat, lon = float(target["lat"]), float(target["lon"])
    def distance(r):
        dy = math.radians(float(r.lat) - lat); dx = math.radians(float(r.lon) - lon)
        a = math.sin(dy/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(float(r.lat)))*math.sin(dx/2)**2
        return 6371.0 * 2 * math.asin(math.sqrt(a))
    nearest = covered_df.iloc[covered_df.apply(distance, axis=1).argmin()]
    km = round(float(distance(nearest)), 1)
    return {"requested_name": target["name"], "resolved_name": str(nearest["name"]), "covered": False, "distance_km": km,
            "disclosure": f"Full model coverage not yet available for {target['name']} - showing nearest covered locality: {nearest['name']}, approximately {km} km away."}

@app.post(_api("farnorth/risk"))
async def get_farnorth_locality_risk(request: FarNorthRiskRequest):
    """Evaluate one Far North locality using the interim rules-based engine."""
    if _get_farnorth_risk is None:
        raise HTTPException(status_code=503, detail="Far North risk engine unavailable")
    try:
        # Keep the event loop responsive while Open-Meteo is queried.
        if request.locality:
            query = request.locality
        elif request.latitude is not None and request.longitude is not None:
            query = f"{request.latitude},{request.longitude}"
        else:
            raise HTTPException(status_code=422, detail="Provide locality or latitude and longitude")
        return await asyncio.to_thread(_get_farnorth_risk, query)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.exception("Far North risk evaluation failed")
        raise HTTPException(status_code=503, detail=f"Limited data available for this locality: {exc}")

@app.post(_api("farnorth/classifier"))
async def get_farnorth_classifier(request: FarNorthRiskRequest):
    """Return the explicitly secondary exploratory classifier signal."""
    if _get_farnorth_classifier is None:
        raise HTTPException(status_code=503, detail="Far North classifier unavailable")
    if not request.locality:
        raise HTTPException(status_code=422, detail="Provide a locality")
    try:
        day = request.date or datetime.now(timezone.utc).date().isoformat()
        return await asyncio.to_thread(_get_farnorth_classifier, request.locality, day)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        log.exception("Far North classifier evaluation failed")
        raise HTTPException(status_code=503, detail=f"Classifier unavailable for this locality: {exc}")

@app.post(_api("farnorth/forecast"))
async def get_farnorth_forecast(request: FarNorthRiskRequest):
    """Return the forward environmental trajectory and independent Option-B signal."""
    if _get_farnorth_forecast is None:
        raise HTTPException(status_code=503, detail="Far North forecast engine unavailable")
    if not request.locality and not (request.latitude is not None and request.longitude is not None):
        raise HTTPException(status_code=422, detail="Provide a locality or latitude and longitude")
    query = request.locality or f"{request.latitude},{request.longitude}"
    try:
        return await asyncio.to_thread(_get_farnorth_forecast, query, request.date, 7)
    except ValueError as exc:
        return {"status": "not_available", "locality": query, "message": str(exc), "trajectory": []}
    except Exception as exc:
        log.exception("Far North forecast failed")
        raise HTTPException(status_code=503, detail=f"Forecast unavailable: {exc}")

@app.get(_api("regions"), response_model=List[Region])
async def get_available_regions():
    """Get list of all available regions"""
    try:
        from .data_sources import get_available_regions
        regions = get_available_regions()
        return [Region(**r) for r in regions]
    except Exception as e:
        log.error(f"Failed to get regions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load regions")


@app.get(_api("regions/{region_code}"), response_model=Region)
async def get_region_details(region_code: str):
    """Get details for a specific region"""
    try:
        from .data_sources import get_region_config
        config = get_region_config(region_code)
        if not config:
            raise HTTPException(status_code=404, detail=f"Region {region_code} not found")

        return Region(
            code=config["code"],
            name=config["name"],
            description=config["description"],
            center_lat=config["center_lat"],
            center_lng=config["center_lng"],
            zoom=config["zoom"],
            watershed_count=len(config["sites"])
        )
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to get region details: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load region details")


@app.get(_api("dashboard"), response_model=DashboardData)
async def get_dashboard_data(response: Response, region: Optional[str] = None):
    """Get complete dashboard data, optionally filtered by region"""
    try:
        # Set cache control headers to prevent caching
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        # Get dashboard data
        summary = db.get_dashboard_summary(str(_db_path))
        watersheds = db.get_watersheds(str(_db_path), region_code=region)

        alerts = db.get_active_alerts(str(_db_path), limit=100)
        risk_trends = db.get_risk_trend_data(str(_db_path))

        # Generate sample risk trend data if none exists
        if not risk_trends:
            import random
            import datetime
            now = datetime.datetime.now()
            risk_trends = []
            for i in range(24):
                hour = (now - datetime.timedelta(hours=23-i)).strftime('%H:00')
                risk_trends.append({
                    'time': hour,
                    'risk': round(random.uniform(3.0, 7.0), 1),
                    'watersheds': random.randint(8, 12)
                })

        summary_mapped = {
            "total_watersheds": summary.get("total_basins", 0),
            "active_alerts": summary.get("active_alerts", 0),
            "high_risk_watersheds": summary.get("high_risk_basins", 0),
            "moderate_risk_watersheds": summary.get("moderate_risk_basins", 0),
            "low_risk_watersheds": summary.get("low_risk_basins", 0),
            "discharge_unavailable": summary.get("discharge_unavailable", False),
            "last_updated": summary.get("last_updated", "")
        }

        return DashboardData(
            summary=DashboardSummary(**summary_mapped),
            watersheds=[Watershed(**w) for w in watersheds],
            alerts=[Alert(**a) for a in alerts],
            risk_trends=[RiskTrendPoint(**r) for r in risk_trends]
        )

    except Exception as e:
        log.error(f"Failed to get dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard data")


@app.get(_api("dashboard/summary"), response_model=DashboardSummary)
async def get_dashboard_summary():
    """Get dashboard summary statistics"""
    try:
        summary = db.get_dashboard_summary(str(_db_path))
        summary_mapped = {
            "total_watersheds": summary.get("total_basins", 0),
            "active_alerts": summary.get("active_alerts", 0),
            "high_risk_watersheds": summary.get("high_risk_basins", 0),
            "moderate_risk_watersheds": summary.get("moderate_risk_basins", 0),
            "low_risk_watersheds": summary.get("low_risk_basins", 0),
            "discharge_unavailable": summary.get("discharge_unavailable", False),
            "last_updated": summary.get("last_updated", "")
        }
        return DashboardSummary(**summary_mapped)
        
    except Exception as e:
        log.error(f"Failed to get dashboard summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard summary")


@app.get(_api("watersheds"), response_model=List[Watershed])
async def get_watersheds(region: Optional[str] = None):
    """Get all watersheds, optionally filtered by region"""
    try:
        watersheds = db.get_watersheds(str(_db_path), region_code=region)
        return [Watershed(**w) for w in watersheds]

    except Exception as e:
        log.error(f"Failed to get watersheds: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load watersheds")


@app.get(_api("alerts"), response_model=List[Alert])
async def get_alerts(limit: int = 100, response: Response = None):
    """Get active alerts"""
    try:
        # Set cache control headers to prevent caching
        if response:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        alerts = db.get_active_alerts(str(_db_path), limit)
        return [Alert(**a) for a in alerts]

    except Exception as e:
        log.error(f"Failed to get alerts: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load alerts")


@app.post(_api("alerts/refresh"))
async def refresh_alerts(user_id: UserID):
    """NOAA alerts refresh stub for Cameroon"""
    return {"status": "not_applicable", "region": "Cameroon"}


@app.get(_api("geo/regions"))
async def get_geo_regions():
    """Get all regions as a GeoJSON FeatureCollection"""
    try:
        return db.get_regions_geojson()
    except Exception as e:
        log.error(f"Failed to get geo regions: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load geo regions")


@app.get(_api("geo/basins"))
async def get_geo_basins():
    """Get all basins as a GeoJSON FeatureCollection"""
    try:
        return db.get_basins_geojson()
    except Exception as e:
        log.error(f"Failed to get geo basins: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load geo basins")


@app.get(_api("farnorth/geo/risk-zones"))
async def get_farnorth_risk_zones():
    """Get all Far North Arrondissements with operational risk levels as a GeoJSON FeatureCollection"""
    try:
        return db.get_farnorth_risk_zones_geojson()
    except Exception as e:
        log.error(f"Failed to get Far North risk zones: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load Far North risk zones")


class CommunityReportRequest(BaseModel):
    lat: float
    lon: float
    water_level_estimate: str  # low/medium/high
    reporter_contact: Optional[str] = None
    reporter_name: Optional[str] = None
    timestamp: Optional[str] = None
    details: Optional[str] = None
    locality: Optional[str] = None
    division: Optional[str] = None
    observation_at: Optional[str] = None
    evidence_name: Optional[str] = None
    # Optional externally hosted evidence URL (uploads use the endpoint below).
    evidence_url: Optional[str] = None
    evidence_media_type: Optional[str] = None


class PredictionFeedbackRequest(BaseModel):
    prediction_id: int
    accuracy: str
    comments: Optional[str] = None


@app.post(_api("community-reports"))
async def create_community_report(request: CommunityReportRequest, user_id: UserID):
    """Submit a community flood report owned by the authenticated citizen."""
    try:
        user_id = _require_authenticated_identity(user_id)
        # Standardise water level estimate to capitalization
        risk_map = {"low": "Low", "medium": "Moderate", "high": "High", "moderate": "Moderate"}
        risk_level = risk_map.get(request.water_level_estimate.lower(), "Low")

        details = request.details or f"Community report: water level estimate {request.water_level_estimate}"
        observation_at = None
        if request.observation_at:
            try:
                observation_at = datetime.fromisoformat(request.observation_at.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=422, detail="observation_at must be an ISO date/time")

        res = db.insert_community_report(
            details=details,
            lat=request.lat,
            lon=request.lon,
            reporter_name=request.reporter_name or "Anonymous",
            contact_info=request.reporter_contact,
            risk_level=risk_level,
            user_id=user_id,
            locality=request.locality,
            division=request.division,
            observation_at=observation_at,
            water_depth_category=request.water_level_estimate,
            evidence_name=request.evidence_name,
            evidence_url=request.evidence_url,
            evidence_media_type=request.evidence_media_type,
        )
        return {**res, "status": "Submitted", "locality": request.locality, "division": request.division}
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to submit community report: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to submit community report")


@app.post(_api("community-reports/{report_id}/evidence"))
async def upload_community_report_evidence(report_id: int, evidence: UploadFile = File(...), user_id: UserID = ""):
    """Persist a citizen photo/video and attach it to an existing report."""
    requester = _require_authenticated_identity(user_id)
    content_type = (evidence.content_type or "").lower()
    if not (content_type.startswith("image/") or content_type.startswith("video/")):
        raise HTTPException(status_code=415, detail="Only image and video evidence files are supported")
    # Protect the local deployment from accidentally filling the disk.
    payload = await evidence.read()
    if len(payload) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Evidence file must be 50 MB or smaller")
    suffix = Path(evidence.filename or "evidence").suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = ".bin"
    upload_dir = Path(settings.app_data_dir) / "community_report_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"report-{report_id}-{uuid.uuid4().hex}{suffix}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(payload)
    try:
        result = await asyncio.to_thread(
            db.attach_community_report_evidence,
            report_id,
            f"/api/community-reports/{report_id}/evidence",
            content_type,
            evidence.filename or stored_name,
            requester,
        )
    except PermissionError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=403, detail=str(exc))
    if result is None:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="Community report not found")
    return {"status": "success", "report": result}


@app.get(_api("community-reports/{report_id}/evidence"))
async def get_community_report_evidence(report_id: int, user_id: UserID):
    """Stream attached evidence only to the report owner or an administrator."""
    requester = _require_authenticated_identity(user_id)
    with db.get_session() as session:
        report = session.get(db.CommunityReport, int(report_id))
        if report is None or not report.evidence_url:
            raise HTTPException(status_code=404, detail="Evidence not found")
        if requester not in {"admin", "administrator", "admin@aquaguard.local"} and report.user_id != requester:
            raise HTTPException(status_code=403, detail="Evidence access denied")
        evidence_name = report.evidence_name or "evidence.bin"
        media_type = report.evidence_media_type or "application/octet-stream"
    upload_dir = Path(settings.app_data_dir) / "community_report_uploads"
    matches = sorted(upload_dir.glob(f"report-{report_id}-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise HTTPException(status_code=404, detail="Evidence file is no longer available")
    return FileResponse(matches[0], media_type=media_type, filename=evidence_name)


@app.get(_api("community-reports/recent"))
async def get_recent_reports():
    """Get the 50 most recent community reports."""
    try:
        return db.get_recent_community_reports(limit=50)
    except Exception as e:
        log.error(f"Failed to get recent community reports: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load community reports")


@app.get(_api("my-reports"))
async def get_my_reports(user_id: UserID, limit: int = 50):
    """Return community reports submitted by the authenticated citizen."""
    try:
        reports = db.get_user_community_reports(_require_authenticated_identity(user_id), limit=limit)
        return {"reports": reports, "count": len(reports)}
    except Exception as e:
        log.error(f"Failed to get user reports for {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load your reports")


@app.post(_api("prediction-feedback"))
async def create_prediction_feedback(request: PredictionFeedbackRequest, user_id: UserID):
    """Store feedback only against a prediction owned by the current citizen."""
    clean_id = _require_authenticated_identity(user_id)
    accuracy = request.accuracy.strip().lower()
    if accuracy not in {"accurate", "partially accurate", "inaccurate"}:
        raise HTTPException(status_code=422, detail="accuracy must be Accurate, Partially accurate, or Inaccurate")
    try:
        return await asyncio.to_thread(db.insert_prediction_feedback, clean_id, request.prediction_id, accuracy, request.comments)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get(_api("my-feedback"))
async def get_my_feedback(user_id: UserID, limit: int = 50):
    clean_id = _require_authenticated_identity(user_id)
    rows = await asyncio.to_thread(db.get_user_prediction_feedback, clean_id, limit)
    return {"feedback": rows, "count": len(rows)}


def _require_admin_identity(user_id: str, request: Optional[Request] = None) -> str:
    """Authorize admin views using the verified role in production or the
    explicit local admin identity in the local development profile."""
    clean_id = _require_authenticated_identity(user_id)
    role = getattr(getattr(request, "state", None), "auth_role", None) if request else None
    if settings.oidc_authority != "" and role in {"admin", "administrator"}:
        return clean_id
    if settings.oidc_authority == "" and clean_id.lower() in {"admin", "administrator", "admin@aquaguard.local"}:
        return clean_id
    raise HTTPException(status_code=403, detail="Administrator access required")


class ReportStatusUpdateRequest(BaseModel):
    status: str


class ReportVerificationRequest(BaseModel):
    verified: bool
    notes: Optional[str] = None


class CommunityAlertRequest(BaseModel):
    message: str
    severity: str = "Moderate"
    expires_time: Optional[str] = None


class AdminUserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


@app.get(_api("admin/overview"))
async def get_admin_overview_endpoint(user_id: UserID, request: Request):
    _require_admin_identity(user_id, request)
    return await asyncio.to_thread(db.get_admin_overview)


@app.get(_api("admin/users"))
async def get_admin_users_endpoint(user_id: UserID, request: Request, limit: int = 200):
    _require_admin_identity(user_id, request)
    rows = await asyncio.to_thread(db.get_admin_users, limit)
    return {"users": rows, "count": len(rows)}


@app.patch(_api("admin/users/{target_user_id}"))
async def update_admin_user_endpoint(target_user_id: str, payload: AdminUserUpdateRequest, user_id: UserID, request: Request):
    _require_admin_identity(user_id, request)
    if target_user_id.lower() in {"admin", "administrator", "admin@aquaguard.local"} and payload.is_active is False:
        raise HTTPException(status_code=400, detail="The active administrator cannot be deactivated")
    if payload.role and payload.role.lower() not in {"citizen user", "citizen", "admin", "administrator"}:
        raise HTTPException(status_code=422, detail="Unsupported role")
    if payload.email is not None and payload.email.strip() and ("@" not in payload.email or "." not in payload.email.rsplit("@", 1)[-1]):
        raise HTTPException(status_code=422, detail="email must be a valid email address")
    if payload.password is not None and payload.password and len(payload.password) < 4:
        raise HTTPException(status_code=422, detail="password must contain at least 4 characters")
    result = await asyncio.to_thread(db.update_user_account, target_user_id, payload.display_name, payload.role, payload.is_active, payload.username, payload.email, payload.password)
    return {"status": "success", "user": result}


@app.delete(_api("admin/users/{target_user_id}"))
async def deactivate_admin_user_endpoint(target_user_id: str, user_id: UserID, request: Request):
    _require_admin_identity(user_id, request)
    if target_user_id.lower() in {"admin", "administrator", "admin@aquaguard.local"}:
        raise HTTPException(status_code=400, detail="The active administrator cannot be deactivated")
    result = await asyncio.to_thread(db.deactivate_user_account, target_user_id)
    return {"status": "success", "user": result, "operation": "deactivated"}


@app.get(_api("admin/reports"))
async def get_admin_reports(user_id: UserID, request: Request, limit: int = 200):
    _require_admin_identity(user_id, request)
    rows = await asyncio.to_thread(db.get_admin_community_reports, limit)
    return {"reports": rows, "count": len(rows)}


@app.patch(_api("admin/reports/{report_id}/status"))
async def update_admin_report_status_endpoint(
    report_id: int,
    payload: ReportStatusUpdateRequest,
    user_id: UserID,
    request: Request,
):
    _require_admin_identity(user_id, request)
    try:
        updated = await asyncio.to_thread(db.update_community_report_status, report_id, payload.status)
        if not updated:
            raise HTTPException(status_code=404, detail="Community report not found")
        return {"status": "success", "report": updated}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.delete(_api("admin/reports/{report_id}"))
async def delete_admin_report_endpoint(report_id: int, user_id: UserID, request: Request):
    """Permanently remove a rejected community report and its stored evidence."""
    _require_admin_identity(user_id, request)
    try:
        deleted = await asyncio.to_thread(db.delete_community_report, report_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if deleted is None:
        raise HTTPException(status_code=404, detail="Community report not found")

    # Evidence is stored outside the database.  Remove only files belonging to
    # this exact report after the guarded database delete succeeds.
    upload_dir = Path(settings.app_data_dir) / "community_report_uploads"
    if upload_dir.exists():
        for media_path in upload_dir.glob(f"report-{int(report_id)}-*"):
            try:
                media_path.unlink()
            except OSError:
                log.warning("Could not remove evidence file %s", media_path)
    return {"status": "success", "report_id": int(report_id), "message": "Rejected report permanently deleted"}


@app.post(_api("admin/reports/{report_id}/verify"))
async def verify_admin_report_endpoint(report_id: int, payload: ReportVerificationRequest, user_id: UserID, request: Request):
    _require_admin_identity(user_id, request)
    result = await asyncio.to_thread(db.verify_community_report, report_id, payload.verified, payload.notes)
    if result is None:
        return JSONResponse(status_code=404, content={"detail": "Community report not found"})
    return {"status": "success", "report": result}


@app.post(_api("admin/reports/{report_id}/alert"))
async def create_admin_report_alert_endpoint(report_id: int, payload: CommunityAlertRequest, user_id: UserID, request: Request):
    _require_admin_identity(user_id, request)
    expires = None
    if payload.expires_time:
        try:
            expires = datetime.fromisoformat(payload.expires_time.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="expires_time must be an ISO date/time")
    try:
        result = await asyncio.to_thread(db.create_alert_from_report, report_id, payload.message, payload.severity, expires)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"status": "success", "alert": result}


@app.get(_api("admin/feedback"))
async def get_admin_feedback(user_id: UserID, request: Request, limit: int = 200):
    _require_admin_identity(user_id, request)
    rows = await asyncio.to_thread(db.get_admin_feedback, limit)
    return {"feedback": rows, "count": len(rows)}


@app.get(_api("admin/analytics"))
async def get_admin_analytics_endpoint(user_id: UserID, request: Request):
    _require_admin_identity(user_id, request)
    return await asyncio.to_thread(db.get_admin_analytics)


@app.get(_api("admin/predictions"))
async def get_admin_predictions_endpoint(user_id: UserID, request: Request, limit: int = 200):
    """Return persisted Far North prediction records for the admin review page."""
    _require_admin_identity(user_id, request)
    rows = await asyncio.to_thread(db.get_admin_predictions, max(1, min(limit, 1000)))
    return {"predictions": rows, "count": len(rows)}


@app.get(_api("admin/alerts"))
async def get_admin_alerts_endpoint(user_id: UserID, request: Request, limit: int = 200):
    """Return only active alerts persisted by the application."""
    _require_admin_identity(user_id, request)
    rows = await asyncio.to_thread(db.get_active_alerts, str(_db_path), max(1, min(limit, 1000)))
    return {"alerts": rows, "count": len(rows)}


@app.get(_api("admin/datasets"))
async def get_admin_datasets_endpoint(user_id: UserID, request: Request):
    _require_admin_identity(user_id, request)
    datasets = await asyncio.to_thread(db.get_admin_datasets)
    return {"datasets": datasets, "count": len(datasets)}


@app.get(_api("historical-flood-events"))
async def get_historical_flood_events_endpoint(limit: int = 100):
    """Return verified historical Far North flood events from the canonical catalogue."""
    try:
        events = db.get_historical_flood_events(limit=limit)
        return {"events": events, "count": len(events)}
    except Exception as e:
        log.error(f"Failed to load historical flood events: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load historical events")


@app.post(_api("alerts/clear-sample"))
async def clear_sample_alerts_endpoint():
    """Clear all sample alerts from the database"""
    try:
        deleted_count = db.clear_sample_alerts(str(_db_path))
        return {
            "status": "success",
            "message": f"Cleared {deleted_count} sample alerts",
            "deleted_count": deleted_count
        }
    except Exception as e:
        log.error(f"Failed to clear sample alerts: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear sample alerts: {str(e)}")


@app.post(_api("dashboard/populate-sample-data"))
async def populate_sample_data():
    """Populate database with sample flood prediction data"""
    try:
        db.populate_sample_data(str(_db_path))
        return {"status": "success", "message": "Sample data populated"}

    except Exception as e:
        log.error(f"Failed to populate sample data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to populate sample data")


@app.post(_api("dashboard/refresh-usgs-data"))
async def refresh_usgs_data(user_id: UserID):
    """Manually trigger USGS data refresh"""
    try:
        if not settings.enable_real_time_data:
            raise HTTPException(status_code=400, detail="Real-time data integration is disabled")
        
        # Create background job for USGS data update
        job_id = _make_job_id(user_id, uid())
        
        meta = {"name": "USGS Data Refresh"}
        
        job = _job_queue.enqueue(
            update_flood_data_task,
            job_id=job_id,
            timeout=600,  # 10 minutes timeout
            ttl=3600,  # 1 hour TTL
            failure_ttl=3600,  # 1 hour failure TTL
            meta=meta,
            kwargs={
                "user_id": user_id,
                "site_codes": None  # Use default major river sites
            },
        )
        
        _, simple_job_id = _parse_job_id(job_id)
        return {
            "status": "success", 
            "message": "USGS data refresh started",
            "job_id": simple_job_id
        }
        
    except Exception as e:
        log.error(f"Failed to start USGS data refresh: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start USGS data refresh")


@app.post(_api("dashboard/update-single-watershed/{watershed_id}"))
async def update_single_watershed_data(watershed_id: int, user_id: UserID):
    """Update a single watershed with latest USGS data"""
    try:
        if not settings.enable_real_time_data:
            raise HTTPException(status_code=400, detail="Real-time data integration is disabled")
        
        # Get watershed info
        watersheds = db.get_watersheds(str(_db_path))
        target_watershed = next((w for w in watersheds if w['id'] == watershed_id), None)
        
        if not target_watershed:
            raise HTTPException(status_code=404, detail="Watershed not found")
        
        # Extract USGS site code from watershed name if available
        import re
        site_code_match = re.search(r'USGS (\d{8})', target_watershed['name'])
        if not site_code_match:
            raise HTTPException(
                status_code=400, 
                detail="No USGS site code found for this watershed"
            )
        
        site_code = site_code_match.group(1)
        
        # Create background job for single watershed update
        job_id = _make_job_id(user_id, uid())
        
        meta = {"name": f"Update Watershed {target_watershed['name']}"}
        
        job = _job_queue.enqueue(
            update_flood_data_task,
            job_id=job_id,
            timeout=300,  # 5 minutes timeout
            ttl=1800,  # 30 minutes TTL
            failure_ttl=1800,  # 30 minutes failure TTL
            meta=meta,
            kwargs={
                "user_id": user_id,
                "site_codes": [site_code]
            },
        )
        
        _, simple_job_id = _parse_job_id(job_id)
        return {
            "status": "success",
            "message": f"Watershed {target_watershed['name']} update started",
            "job_id": simple_job_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to update single watershed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update watershed data")


# =============================================================================
# Analytics API Endpoints
# =============================================================================

@app.get(_api("analytics"), response_model=AnalyticsData)
async def get_analytics_data(
    time_range: str = "7d",
    metric: str = "risk_score"
):
    """Get complete analytics data"""
    try:
        # Initialize watersheds from USGS if database is empty (no sample data)
        summary = db.get_dashboard_summary(str(_db_path))
        if summary.get('total_basins', 0) == 0:
            log.info("No basins found in database.")

        # Get analytics data
        analytics_data = db.get_analytics_data(str(_db_path), time_range, metric)
        
        return AnalyticsData(**analytics_data)
        
    except Exception as e:
        log.error(f"Failed to get analytics data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load analytics data")

@app.get(_api("analytics/historical"), response_model=List[HistoricalDataPoint])
async def get_historical_data(
    time_range: str = "7d"
):
    """Get historical trend data"""
    try:
        historical_data = db.get_historical_analytics_data(str(_db_path), time_range)
        return [HistoricalDataPoint(**point) for point in historical_data]
        
    except Exception as e:
        log.error(f"Failed to get historical data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load historical data")

@app.get(_api("analytics/risk-distribution"), response_model=List[RiskDistribution])
async def get_risk_distribution():
    """Get current risk distribution"""
    try:
        distribution = db.get_risk_distribution_data(str(_db_path))
        return [RiskDistribution(**item) for item in distribution]
        
    except Exception as e:
        log.error(f"Failed to get risk distribution: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load risk distribution")

@app.get(_api("analytics/watershed-comparison"), response_model=List[WatershedComparison])
async def get_watershed_comparison():
    """Get watershed comparison data"""
    try:
        comparison = db.get_watershed_comparison_data(str(_db_path))
        return [WatershedComparison(**item) for item in comparison]
        
    except Exception as e:
        log.error(f"Failed to get watershed comparison: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load watershed comparison")

@app.get(_api("analytics/flow-comparison"), response_model=List[FlowComparison])
async def get_flow_comparison():
    """Get flow vs flood stage comparison"""
    try:
        comparison = db.get_flow_comparison_data(str(_db_path))
        return [FlowComparison(**item) for item in comparison]
        
    except Exception as e:
        log.error(f"Failed to get flow comparison: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load flow comparison")

@app.get(_api("dashboard/insights"))
async def get_dashboard_insights():
    """Get comprehensive dashboard insights and metrics"""
    try:
        # Get base data
        summary = db.get_dashboard_summary(str(_db_path))
        watersheds = db.get_watersheds(str(_db_path))
        analytics_data = db.get_analytics_data(str(_db_path), '24h', 'risk_score')
        
        # Calculate additional insights
        usgs_stations = len([w for w in watersheds if w.get('data_source') == 'usgs'])
        rising_trend_count = len([w for w in watersheds if w.get('trend') == 'rising'])
        average_flow = sum([w.get('current_streamflow_cms', 0) for w in watersheds]) / len(watersheds) if watersheds else 0
        
        # Calculate model accuracy based on data quality
        total_stations = len(watersheds)
        accuracy_base = 75.0  # Base accuracy
        if usgs_stations > 0:
            accuracy_boost = min((usgs_stations / total_stations) * 15, 15)  # Up to 15% boost for real-time data
            model_accuracy = accuracy_base + accuracy_boost
        else:
            model_accuracy = accuracy_base
        
        # Confidence level based on data availability and risk distribution
        high_risk_ratio = summary.get('high_risk_basins', 0) / summary.get('total_basins', 1)
        if total_stations > 0 and usgs_stations / total_stations > 0.7 and high_risk_ratio < 0.3:
            confidence = "HIGH"
        elif usgs_stations / total_stations > 0.4:
            confidence = "MODERATE" 
        else:
            confidence = "LOW"
            
        return {
            "model_accuracy": round(model_accuracy, 1),
            "usgs_stations": usgs_stations,
            "total_stations": total_stations,
            "rising_trend_count": rising_trend_count,
            "average_flow": round(average_flow, 2),
            "confidence_level": confidence,
            "data_quality_score": round((usgs_stations / total_stations) * 100, 1) if total_stations > 0 else 0,
            "next_update": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            "system_status": "operational",
            "alert_trend": "stable" if rising_trend_count < 3 else "increasing"
        }
        
    except Exception as e:
        log.error(f"Failed to get dashboard insights: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard insights")

# =============================================================================
# User Settings API Models
# =============================================================================

class UserSettings(BaseModel):
    """User settings model"""
    notifications: Dict[str, Any]
    display: Dict[str, Any]
    data: Dict[str, Any]

class SettingsUpdateRequest(BaseModel):
    """Settings update request model"""
    settings: UserSettings

# =============================================================================
# Authenticated User & Predictions API Endpoints
# =============================================================================

class SavePredictionRequest(BaseModel):
    locality: str
    risk_level: Optional[str] = None
    estimated_risk_percent: Optional[float] = None
    confidence_score: Optional[float] = None
    forecast_period: Optional[str] = "Next 24–72 hrs"
    details: Optional[Dict[str, Any]] = None


@app.get(_api("me"))
async def get_me(user_id: UserID, request: Request):
    """Return authenticated user profile details."""
    clean_id = _require_authenticated_identity(user_id)
    role = "admin" if clean_id.lower() in ("admin", "admin@aquaguard.local", "administrator") else "citizen"
    # In local development the login form supplies the display name while
    # the authenticated identity remains the username/email.  In production
    # the verified token identity remains authoritative; the display header is
    # only presentation metadata.
    name = request.headers.get("X-User-Name", "").strip() if settings.oidc_authority == "" else ""
    name = name or clean_id
    email = clean_id if "@" in clean_id else f"{clean_id}@aquaguard.local"
    return {
        "user_id": clean_id,
        "username": clean_id,
        "name": name,
        "email": email,
        "role": role,
    }


@app.get(_api("my-predictions/latest"))
async def get_my_latest_prediction(user_id: UserID):
    """Retrieve the most recent prediction owned by the authenticated user."""
    prediction = db.get_user_latest_prediction(_require_authenticated_identity(user_id))
    return {"prediction": prediction}


@app.get(_api("my-predictions"))
async def get_my_predictions(user_id: UserID, limit: int = 50):
    """Retrieve chronological prediction history strictly owned by the authenticated user."""
    predictions = db.list_user_predictions(_require_authenticated_identity(user_id), limit=limit)
    return {"predictions": predictions, "count": len(predictions)}


@app.post(_api("my-predictions"))
async def save_my_prediction(user_id: UserID, req: SavePredictionRequest):
    """Save a real prediction associated with the authenticated user."""
    user_id = _require_authenticated_identity(user_id)
    locality = req.locality.strip()
    risk_data: Dict[str, Any] = {}
    if not locality:
        raise HTTPException(status_code=422, detail="A locality is required to save a prediction")

    # Recalculate whenever the client did not provide the complete result.
    # Never manufacture a probability or confidence value merely to make a
    # record fit the UI; an unavailable engine result must remain unavailable.
    if req.risk_level is None or req.estimated_risk_percent is None or req.confidence_score is None:
        if _get_farnorth_risk is not None:
            try:
                calc = await asyncio.to_thread(_get_farnorth_risk, locality)
                if isinstance(calc, dict):
                    risk_data = calc
            except Exception as e:
                log.warning(f"Could not calculate risk for locality {locality}: {e}")

    risk_level = req.risk_level or risk_data.get("risk_level")
    estimated_risk_percent = req.estimated_risk_percent if req.estimated_risk_percent is not None else risk_data.get("estimated_risk_percent")
    confidence_score = req.confidence_score if req.confidence_score is not None else risk_data.get("confidence_score")
    if risk_level is None or estimated_risk_percent is None or confidence_score is None:
        raise HTTPException(status_code=503, detail="The authoritative Far North prediction is unavailable; nothing was saved")
    details = req.details or risk_data

    saved = db.save_user_prediction(
        user_id=user_id,
        data={
            "locality": locality,
            "risk_level": risk_level,
            "estimated_risk_percent": float(estimated_risk_percent),
            "confidence_score": float(confidence_score),
            "forecast_period": req.forecast_period or "Next 24–72 hrs",
            "details": details,
        }
    )
    return {"status": "saved", "prediction": saved}


# =============================================================================
# User Settings API Endpoints
# =============================================================================

@app.get(_api("settings"), response_model=UserSettings)
async def get_user_settings(user_id: UserID):
    """Get current user's settings"""
    try:
        settings = db.get_user_settings(str(_db_path), user_id)
        return UserSettings(**settings)
    except Exception as e:
        log.error(f"Failed to get user settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve settings")

@app.post(_api("settings"))
async def update_user_settings(user_id: UserID, settings: UserSettings):
    """Update current user's settings"""
    try:
        db.save_user_settings(str(_db_path), user_id, settings.dict())
        return {"status": "success", "message": "Settings updated successfully"}
    except Exception as e:
        log.error(f"Failed to save user settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save settings")

@app.delete(_api("settings"))
async def reset_user_settings(user_id: UserID):
    """Reset current user's settings to defaults"""
    try:
        db.delete_user_settings(str(_db_path), user_id)
        return {"status": "success", "message": "Settings reset to defaults"}
    except Exception as e:
        log.error(f"Failed to reset user settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to reset settings")

@app.get(_api("settings/export"))
async def export_user_settings(user_id: UserID):
    """Export current user's settings as JSON file"""
    try:
        settings = db.get_user_settings(str(_db_path), user_id)
        
        # Create JSON response
        import json
        from fastapi.responses import StreamingResponse
        import io
        
        json_str = json.dumps(settings, indent=2)
        json_bytes = io.BytesIO(json_str.encode('utf-8'))
        
        return StreamingResponse(
            json_bytes,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=flood-prediction-settings.json"}
        )
    except Exception as e:
        log.error(f"Failed to export user settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to export settings")

@app.post(_api("settings/import"))
async def import_user_settings(user_id: UserID, request: Request):
    """Import user settings from JSON"""
    try:
        import json
        
        # Read body as bytes
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="No file content provided")
            
        # Parse JSON settings
        settings_data = json.loads(body.decode('utf-8'))
        
        # Validate structure (basic validation)
        required_keys = ['notifications', 'display', 'data']
        if not all(key in settings_data for key in required_keys):
            raise HTTPException(status_code=400, detail="Invalid settings file format")
            
        # Save settings
        db.save_user_settings(str(_db_path), user_id, settings_data)
        
        return {"status": "success", "message": "Settings imported successfully", "settings": settings_data}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        log.error(f"Failed to import user settings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to import settings")

# =============================================================================
# AI Chat API Endpoints
# =============================================================================

@app.get(_api("ai/models"))
async def get_llm_models(provider: Optional[str] = None):
    """Get available LLM models from the specified provider"""
    try:
        models = get_available_llm_models(provider)
        provider_info = get_provider_info(provider)
        return {
            "models": models, 
            "default_model": provider_info.get("default_model"),
            "provider": provider_info.get("name")
        }
    except Exception as e:
        log.error(f"Failed to get LLM models: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get LLM models")

@app.post(_api("ai/chat"), response_model=ChatResponse)
async def chat_with_ai(user_id: UserID, request: ChatMessage):
    """Chat with AI assistant about flood conditions"""
    user_id = _require_authenticated_identity(user_id)
    try:
        # Normal Chat and NAT mode share the same bounded Far North router.
        # This prevents the legacy generic assistant path from attaching an
        # arbitrary locality or returning template (non-Cameroon) numbers.
        session_context = _assistant_context_for(user_id, request.context)
        routed_request = NATChatMessage(
            message=request.message,
            agent_type="all" if request.use_agent else "risk_analyzer",
            location=session_context.get("location") or session_context.get("name") or "Cameroon Region",
            context=session_context,
        )
        routed = await _route_nat_intent(routed_request)
        if routed is not None:
            _remember_assistant_context(user_id, routed)
            return ChatResponse(
                response=_sanitize_agent_text(routed.get("output")),
                confidence=1.0,
                recommendations=[],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        # Generate AI response based on the message and context
        response = db.generate_ai_response(
            str(_db_path), 
            request.message, 
            request.watershed_id,
            request.context or {}
        )
        
        return ChatResponse(
            response=response["content"],
            confidence=response["confidence"],
            recommendations=response.get("recommendations", []),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
    except Exception as e:
        log.error(f"Failed to process AI chat: {str(e)}")
        return ChatResponse(
            response=LLM_UNAVAILABLE_MESSAGE,
            confidence=0.0,
            recommendations=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


@app.post(_api("ai/chat/stream"))
async def stream_chat_with_ai(user_id: UserID, request: ChatMessage):
    """Stream chat with AI assistant about flood conditions"""
    user_id = _require_authenticated_identity(user_id)
    try:
        import asyncio
        import json

        session_context = _assistant_context_for(user_id, request.context)
        routed_request = NATChatMessage(
            message=request.message,
            agent_type="all" if request.use_agent else "risk_analyzer",
            location=session_context.get("location") or session_context.get("name") or "Cameroon Region",
            context=session_context,
        )
        routed = await _route_nat_intent(routed_request)
        if routed is not None:
            _remember_assistant_context(user_id, routed)
            async def routed_stream():
                yield f"data: {json.dumps({'type': 'start', 'agent_type': routed_request.agent_type, 'location': routed_request.location}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'result', 'output': _sanitize_agent_text(routed.get('output')), 'status': routed.get('status', 'routed')}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(routed_stream(), media_type="text/event-stream; charset=utf-8", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
        
        async def generate_stream():
            try:
                import threading
                import concurrent.futures
                from collections import deque
                
                # Use thread-safe deque and event for communication
                chunks_queue = deque()
                done_event = threading.Event()
                error_container = {'error': None}
                
                # Get provider info for evaluation
                provider_info = get_provider_info(None)  # Use default provider
                
                def sync_callback(chunk: str):
                    chunks_queue.append(chunk)
                
                def run_llm_sync():
                    try:
                        # Create a new event loop for this thread
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        final_response = loop.run_until_complete(llm_call_stream(
                            request.message, 
                            sync_callback, 
                            request.model, 
                            request.use_agent
                        ))
                        chunks_queue.append("__DONE__")
                        done_event.set()
                        return final_response
                    except Exception as e:
                        # Keep flood Q&A usable when an external model is
                        # retired, rate-limited, or temporarily unreachable.
                        # This response is deliberately labelled as a local
                        # fallback and never pretends to be a model forecast.
                        fallback = _local_flood_answer(request.message)
                        for part in (fallback,):
                            chunks_queue.append(part)
                        chunks_queue.append("__DONE__")
                        done_event.set()
                        return fallback
                
                # Start the LLM in a background thread
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    llm_future = executor.submit(run_llm_sync)
                    
                    # Stream chunks as they arrive
                    while not done_event.is_set() or chunks_queue:
                        if chunks_queue:
                            chunk = chunks_queue.popleft()
                            if chunk == "__DONE__":
                                break
                            # Do not forward provider chunks incrementally:
                            # they can contain ReAct scaffolding or raw JSON
                            # before the final answer is known.  The complete
                            # answer is sanitized and emitted below.
                        else:
                            # Small delay to avoid busy waiting and send keepalive
                            await asyncio.sleep(0.1)
                            if not done_event.is_set():
                                yield f"data: {json.dumps({'keepalive': True})}\n\n"
                    
                    # Wait for LLM completion
                    final_response = llm_future.result()
                    safe_final_response = _sanitize_agent_text(final_response)
                    yield f"data: {json.dumps({'chunk': safe_final_response, 'done': False}, ensure_ascii=False)}\n\n"
                    
                    # Run evaluation for all responses (agent and non-agent) if we have a complete response
                    # Quality judging is optional background work.  It used to
                    # block the user's stream on a second remote model call,
                    # adding tens of seconds and exposing evaluator failures.
                    if os.environ.get("APP_ENABLE_CHAT_EVALUATION", "0") == "1" and final_response and not error_container['error']:
                        try:
                            evaluation_result = await evaluator.evaluate_chat_response(
                                question=request.message,
                                response=final_response,
                                model_used=request.model or "default",
                                agent_used=request.use_agent,
                                watershed_context=request.context,
                                response_provider=provider_info.get("name", "unknown")  # Use actual provider used
                            )
                            
                            # Send evaluation results
                            evaluation_data = {
                                'evaluation': {
                                    'id': evaluation_result.id,
                                    'overall_score': evaluation_result.metrics.overall,
                                    'confidence': evaluation_result.metrics.confidence,
                                    'safety_score': evaluation_result.metrics.safety,
                                    'helpfulness': evaluation_result.metrics.helpfulness,
                                    'accuracy': evaluation_result.metrics.accuracy,
                                    'reasoning': evaluation_result.judge_reasoning
                                }
                            }
                            yield f"data: {json.dumps(evaluation_data)}\n\n"
                            
                        except Exception as eval_error:
                            log.warning(f"Evaluation failed: {str(eval_error)}")
                            # Don't fail the entire response if evaluation fails
                    
                    yield f"data: {json.dumps({'done': True})}\n\n"
                
            except Exception as e:
                log.error(f"Stream generation error: {str(e)}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            }
        )
        
    except Exception as e:
        log.error(f"Failed to process streaming AI chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process streaming chat message")


# =============================================================================
# NAT Agent Chat API Endpoints
# =============================================================================

@app.get(_api("nat/agents"))
async def get_available_nat_agents():
    """Get available NAT agents"""
    if not _nat_runner:
        raise HTTPException(status_code=503, detail="NAT agents are not available")
    
    try:
        agents_info = _nat_runner.list_available_agents()
        return agents_info
    except Exception as e:
        log.error(f"Failed to get NAT agents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get NAT agents")


# ---------------------------------------------------------------------------
# Shared NAT intent router and output safety layer
# ---------------------------------------------------------------------------

def _fold_far_north_text(value: Any) -> str:
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(ch)).casefold()


def _farnorth_names() -> List[str]:
    """Return only verified model-covered locality names.

    The 3,860-row susceptibility cache also contains unverified gazetteer
    labels (including generic/place-name fragments).  It is not an authority
    for accepting a user entity into a risk calculation.  Keep the router's
    accepted set aligned with the explicit 34-locality environmental scope;
    other gazetteer names can be reported as out of coverage, never queried.
    """
    return sorted(FAR_NORTH_COVERED_LOCALITIES,
                  key=lambda value: (-len(value), value.casefold()))


def _historical_localities_starting_with(initial: str) -> List[str]:
    """Return locality names that occur in the verified event catalogue.

    This deliberately reads the canonical catalogue rather than the risk
    cache: a susceptibility cache can contain localities with no documented
    event history, while this query is specifically about history.
    """
    if not initial or _get_farnorth_catalogue is None:
        return []
    try:
        catalogue = _get_farnorth_catalogue()
        column = "locality_name"
        if not hasattr(catalogue, "columns") or column not in catalogue.columns:
            return []
        # Catalogue rows may contain several source-named localities in one
        # semicolon-delimited footprint.  Return the actual locality tokens,
        # not the whole composite string.
        values = catalogue[column].dropna().astype(str).str.split(";").explode().str.strip()
        folded_initial = _fold_far_north_text(initial)[:1]
        seen: Dict[str, str] = {}
        for value in values:
            if _fold_far_north_text(value).startswith(folded_initial):
                seen.setdefault(_fold_far_north_text(value), value)
        return sorted(seen.values(), key=lambda value: _fold_far_north_text(value))
    except Exception as exc:
        log.warning("Unable to filter Far North event catalogue: %s", exc)
        return []


def _context_risk_value(context: Optional[Dict[str, Any]]) -> Optional[float]:
    """Find a previously displayed numeric risk signal in session context."""
    if not isinstance(context, dict):
        return None
    candidates = [context.get("estimated_risk_percent"), context.get("risk_percent"), context.get("risk_score")]
    nested = context.get("risk") or context.get("current_risk") or {}
    if isinstance(nested, dict):
        candidates.extend([nested.get("estimated_risk_percent"), nested.get("risk_percent")])
    for value in candidates:
        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _context_locality(context: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return a previously selected *covered* locality, never an arbitrary fallback."""
    if not isinstance(context, dict):
        return None
    candidates = [context.get("locality"), context.get("location"), context.get("name")]
    nested = context.get("prediction") or context.get("risk") or context.get("current_risk") or {}
    if isinstance(nested, dict):
        candidates.extend([nested.get("locality"), nested.get("location")])
    covered = {_fold_far_north_text(name): name for name in _farnorth_names()}
    for candidate in candidates:
        if candidate is None:
            continue
        match = covered.get(_fold_far_north_text(candidate))
        if match:
            return match
    return None


FAR_NORTH_GEOGRAPHIC_AREAS = {
    "yaere": "Yaérés",
    "yaeres": "Yaérés",
    "les yaeres": "Yaérés",
    "plaine du yaere": "Yaérés",
    "plaines des yaeres": "Yaérés",
    "lac tchad": "Lac Tchad (Lake Chad)",
    "lake chad": "Lake Chad",
    "barrage de maga": "Barrage de Maga (Maga Dam)",
    "maga dam": "Maga Dam",
    "fleuve logone": "Fleuve Logone",
    "logone river": "Logone River",
    "fleuve chari": "Fleuve Chari",
    "chari river": "Chari River",
}


@dataclass
class LocationResolution:
    user_location: Optional[str] = None
    resolved_location: Optional[str] = None
    location_type: Optional[str] = None       # "locality", "division", "geographic_area", "out_of_scope", None
    prediction_location: Optional[str] = None # Valid covered locality for engine lookup, or None
    confidence: str = "unresolved"            # "exact", "high", "unresolved"
    notes: Optional[str] = None


def _resolve_location_hierarchy(message: str, context: Optional[Dict[str, Any]] = None,
                                supplied_location: Optional[str] = None) -> LocationResolution:
    """Explicitly separate user location, resolved location, and prediction location.

    Never silently substitute an unresolvable or geographic area with Yagoua or another city.
    """
    folded = _fold_far_north_text(message)

    # 1. Check covered Far North localities
    localities = _farnorth_names()
    names = _whole_name_matches(message, localities)
    if names:
        canonical = names[0]
        return LocationResolution(
            user_location=canonical,
            resolved_location=canonical,
            location_type="locality",
            prediction_location=canonical,
            confidence="exact",
        )

    # 2. Check Far North divisions
    divisions = FAR_NORTH_DIVISIONS
    division = next((d for d in divisions if re.search(r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, _fold_far_north_text(d).split("-"))) + r"(?![a-z0-9])", folded)), None)
    if division:
        return LocationResolution(
            user_location=division,
            resolved_location=division,
            location_type="division",
            prediction_location=None,
            confidence="exact",
        )

    # 3. Check recognized Far North environmental / geographic areas (e.g. Yaérés)
    for key, canonical in FAR_NORTH_GEOGRAPHIC_AREAS.items():
        pattern = r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])"
        if re.search(pattern, folded):
            return LocationResolution(
                user_location=canonical,
                resolved_location=canonical,
                location_type="geographic_area",
                prediction_location=None,  # NEVER substitute Yagoua or any other town
                confidence="exact",
                notes="Far North geographical/wetland area. Not a covered town in the 34-locality prediction database.",
            )

    # 4. Check Cameroon locations outside the Far North
    cameroonian_outside = next((place for place in CAMEROON_OUTSIDE_FAR_NORTH if re.search(rf"(?<![a-z0-9]){place}(?![a-z0-9])", folded)), None)
    if cameroonian_outside:
        region = CAMEROON_OUTSIDE_FAR_NORTH[cameroonian_outside]
        return LocationResolution(
            user_location=cameroonian_outside.title(),
            resolved_location=cameroonian_outside.title(),
            location_type="out_of_scope",
            prediction_location=None,
            confidence="exact",
            notes=f"Located in Cameroon's {region}, outside Far North coverage.",
        )

    # 5. Check foreign / unrelated regions
    unrelated_terms = ("houston", "buffalo bayou", "austin", "united states", "usgs", "texas", "paris")
    for term in unrelated_terms:
        if re.search(rf"(?<![a-z0-9]){term}(?![a-z0-9])", folded):
            return LocationResolution(
                user_location=term.title(),
                resolved_location=term.title(),
                location_type="out_of_scope",
                prediction_location=None,
                confidence="exact",
                notes="External location outside Cameroon.",
            )

    # 6. Check if follow-up can use verified locality from previous session context
    prior_locality = _context_locality(context)
    if prior_locality and _is_followup_question(message):
        return LocationResolution(
            user_location=prior_locality,
            resolved_location=prior_locality,
            location_type="locality",
            prediction_location=prior_locality,
            confidence="exact",
            notes="Inherited from verified previous session context for follow-up query",
        )

    # 7. Check if supplied_location is specific and covered
    if supplied_location:
        sup_folded = _fold_far_north_text(supplied_location)
        if sup_folded not in {"", "cameroon", "cameroon region", "cameroon far north", "far north"}:
            matched_sup = _whole_name_matches(supplied_location, localities)
            if matched_sup:
                return LocationResolution(
                    user_location=matched_sup[0],
                    resolved_location=matched_sup[0],
                    location_type="locality",
                    prediction_location=matched_sup[0],
                    confidence="exact",
                )

    return LocationResolution(
        user_location=None,
        resolved_location=None,
        location_type=None,
        prediction_location=None,
        confidence="unresolved",
    )


def _is_conceptual_question(message: str) -> bool:
    """Detect conceptual explanations that must not require or invoke locality risk data."""
    folded = _fold_far_north_text(message)
    definition_lead = bool(re.search(
        r"\b(?:what\s+does|what\s+is|what\s+are|what\s+do\s+you\s+mean|explain|meaning\s+of|define|definition\s+of|how\s+does|"
        r"que\s+signifie|qu['’]est-ce\s+que\b|qu['’]est-ce\s+qu['’]une?|qu['’]est-ce\s+qu['’]un?|c['’]est\s+quoi|"
        r"explique(?:z)?|definis|definir|comment\s+fonctionne)\b",
        folded,
        re.I,
    ))
    domain_term = bool(re.search(
        r"\b(?:soil\s+moisture|humidite(?:\s+du\s+sol)?|swvl1|rainfall|pluie|precipitation|"
        r"discharge|debit|streamflow|confidence|confiance|baseline|anomal(?:y|ie)|"
        r"forecast\s+horizon|horizon\s+de\s+prevision|flood\s+probability|"
        r"probabilite(?:\s+d['’]inondation)?|digue|dike|dyke|floodplain|plaine\s+inondable|"
        r"yaere|yaeres|drainage|drainage\s+density|densite\s+de\s+drainage|"
        r"threshold|seuil|saturation|flood\s+stages?|stades?\s+d['’]inondation|"
        r"risk\s+level|niveau\s+de\s+risque|risk\s+score|score\s+de\s+risque|"
        r"hydrolog\w*|meteorolog\w*)\b",
        folded,
        re.I,
    ))
    numeric_measurement = domain_term and bool(re.search(r"\b\d+(?:\.\d+)?\b", folded))
    concept = (definition_lead and domain_term) or numeric_measurement or (definition_lead and re.search(r"\b(?:digue|dike|dyke|yaere|yaeres|floodplain|drainage)\b", folded))

    standalone_concept = bool(re.search(
        r"^(?:qu['’]est-ce\s+qu['’]une?\s+digue|qu['’]est-ce\s+que\s+les?\s+yaeres?|what\s+is\s+a\s+d(?:y|i)ke|what\s+are\s+the\s+yaeres?|what\s+is\s+a\s+floodplain)\b",
        folded,
        re.I
    ))
    if standalone_concept:
        return True

    # Explicit live risk or forecast lookups are not conceptual
    live_lookup = bool(re.search(
        r"\b(?:risk|flood\s+risk|forecast|prediction|risque|prevision|prévision)\b.*\b(?:in|at|for|a|à|de|du|dans)\b",
        folded,
        re.I,
    ))
    return (concept or standalone_concept) and not live_lookup


def _is_followup_question(message: str) -> bool:
    return bool(re.fullmatch(
        r"\s*(?:why|how\s+so|what\s+about\s+it|and\s+why|pourquoi|et\s+pourquoi|"
        r"comment\s+ça|comment\s+ca|et\s+alors)\s*[?!.]*\s*",
        message or "",
        re.I,
    ))


def _detect_assistant_intent(message: str, loc_res: LocationResolution, context: Optional[Dict[str, Any]]) -> str:
    """Classify user request into one of the 8 authoritative assistant intents."""
    folded = _fold_far_north_text(message)

    # 1. GENERAL_CONCEPTUAL: definitions, concepts, soil moisture, dykes, Yaérés concept
    if _is_conceptual_question(message):
        return "GENERAL_CONCEPTUAL"

    # 2. SYSTEM_EXPLANATION: how the AI / prediction system operates
    if re.search(r"\b(?:how\s+does\s+the\s+system|comment\s+fonctionne\s+le\s+syst[eè]me|system\s+explanation|how\s+do\s+you\s+calculate|comment\s+calculez|sources?\s+de\s+donn[eé]es)\b", folded, re.I):
        return "SYSTEM_EXPLANATION"

    # 3. FOLLOW_UP_TO_PREVIOUS_RESULT: short questions like "Why?", "Pourquoi ?"
    if _is_followup_question(message) and loc_res.prediction_location:
        return "FOLLOW_UP_TO_PREVIOUS_RESULT"

    # 4. PREDICTION_EXPLANATION: questions asking WHY a location has a certain risk level or what factors contributed
    if re.search(r"\b(?:pourquoi|why|comment\s+se\s+fait-il|what\s+factors?|facteurs?)\b", folded, re.I) and \
       (loc_res.prediction_location or _context_locality(context)) and \
       re.search(r"\b(?:risk|risque|[eé]lev[eé]|high|medium|moyen|faible|low|class[eé]|rating)\b", folded, re.I):
        return "PREDICTION_EXPLANATION"

    # 5. SAFETY_PREPAREDNESS: guidance on what to do, evacuation, safety measures
    if re.search(r"\b(?:safety|safe|securit[eé]|s[eé]curit[eé]|evacuat\w*|[eé]vacu\w*|prepare|pr[eé]par\w*|checklist|consignes?|que\s+faire)\b", folded, re.I) and not re.search(r"\b(?:forecast|pr[eé]vision)\b", folded, re.I):
        return "SAFETY_PREPAREDNESS"

    # 6. LOCATION_INFORMATION: general questions about places/regions (e.g. fishermen in Yaérés, where is Yagoua)
    if loc_res.resolved_location in FAR_NORTH_GEOGRAPHIC_AREAS or loc_res.location_type == "area":
        if not re.search(r"\b(?:risk|flood|danger|forecast|pr[eé]vision|probabilit\w*|alerte|inond\w*)\b", folded, re.I):
            return "LOCATION_INFORMATION"
    if re.search(r"\b(?:o[uù]\s+(?:est|se\s+trouve|est\s+situ[eé])|where\s+is|where\s+are|tell\s+me\s+about|parle-?moi\s+de|population|habitants?|p[eê]cheurs?|fisherm[ae]n|g[eé]ographie|climat)\b", folded, re.I):
        if not re.search(r"\b(?:risk|flood|danger|forecast|pr[eé]vision|probabilit\w*|alerte|inond\w*)\b", folded, re.I):
            return "LOCATION_INFORMATION"

    # 7. FLOOD_RISK_QUERY: specific flood risk, probabilities, forecasts, rankings
    if re.search(r"\b(?:top|highest|most|which\s+(?:area|locality|region)|ranking|classement)\b", folded, re.I):
        return "FLOOD_RISK_QUERY"
    if re.search(r"\b(?:forecast|tomorrow|upcoming|next\s+\d+\s+days?|prevision|pr[eé]vision|dans\s+\d+\s+jours?)\b", folded, re.I):
        return "FLOOD_RISK_QUERY"
    if re.search(r"\b(?:risk|flood\s+risk|risque|inondation|probabilit[eé]|probability|r[eé]sum[eé]|situation|statut|status)\b", folded, re.I):
        return "FLOOD_RISK_QUERY"
    if loc_res.prediction_location or loc_res.location_type == "division":
        return "FLOOD_RISK_QUERY"

    # 8. UNKNOWN / GENERAL_CONVERSATION: fallback
    return "UNKNOWN_GENERAL_CONVERSATION"


def _router_intent(message: str, names: List[str], division: Optional[str], context: Optional[Dict[str, Any]]) -> str:
    """Backward-compatible wrapper for existing unit tests."""
    loc_res = LocationResolution(
        user_location=names[0] if names else division,
        resolved_location=names[0] if names else division,
        location_type="locality" if names else ("division" if division else None),
        prediction_location=names[0] if names else None,
        confidence="exact" if (names or division) else "unresolved",
    )
    return _detect_assistant_intent(message, loc_res, context)


def _log_router_decision(
    request: "NATChatMessage",
    intent: str,
    user_location: Optional[str],
    resolved_location: Optional[str],
    location_confidence: str,
    requires_prediction_data: bool,
    tool_called: bool,
    tool_name: str = "none"
) -> None:
    """Standardized development trace showing router decisions."""
    log.info(
        "[AI ROUTER] intent=%s user_location=%s resolved_location=%s "
        "location_confidence=%s requires_prediction_data=%s tool_called=%s tool_name=%s",
        intent,
        user_location or "none",
        resolved_location or "none",
        location_confidence,
        requires_prediction_data,
        tool_called,
        tool_name,
    )


def _whole_name_matches(message: str, choices: List[str]) -> List[str]:
    """Match complete names only; never match a fragment of a sentence word."""
    haystack = _fold_far_north_text(message)
    found = []
    for choice in choices:
        choice_folded = _fold_far_north_text(choice)
        tokens = re.findall(r"[a-z0-9]+", choice_folded)
        if not tokens:
            continue
        pattern = r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, tokens)) + r"(?![a-z0-9])"
        if re.search(pattern, haystack):
            found.append(choice)
        elif len(tokens) > 1:
            # Also test direct concatenation without separator (e.g. Kaikai -> Kai-Kai)
            joined = "".join(tokens)
            if re.search(r"(?<![a-z0-9])" + re.escape(joined) + r"(?![a-z0-9])", haystack):
                found.append(choice)
    return sorted(set(found), key=lambda value: (-len(value), value.casefold()))


def _ranking_count(message: str, default: int = 5) -> int:
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
             "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    numeric = re.search(r"\b(?:top|give\s+me|show\s+me|list|name|just)\s+(?:(?:exactly|just)\s+)?(\d{1,2})\b", message or "", re.I)
    if numeric:
        return max(1, min(20, int(numeric.group(1))))
    word = re.search(r"\b(?:give\s+me|show\s+me|list|name|just)\s+(?:(?:exactly|just)\s+)?(one|two|three|four|five|six|seven|eight|nine|ten)\b", message or "", re.I)
    if word:
        return words[word.group(1).casefold()]
    bare = re.fullmatch(r"\s*(?:just\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*", message or "", re.I)
    if bare:
        return max(1, min(20, int(bare.group(1)) if bare.group(1).isdigit() else words[bare.group(1).casefold()]))
    return max(1, min(20, default))


def _sanitize_agent_text(value: Any) -> str:
    """Remove logs/ReAct scaffolding/raw JSON before text reaches the UI."""
    if isinstance(value, dict):
        for key in ("output", "response", "answer", "message", "content"):
            if value.get(key):
                value = value[key]
                break
        else:
            return "The requested analysis completed, but it did not return a user-facing explanation."
    text = str(value or "").strip()
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return _sanitize_agent_text(parsed)
        except Exception:
            pass
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^(?:\[?(?:DEBUG|INFO|WARNING|ERROR|TRACE)\]?\s*)", stripped, re.I):
            continue
        if re.match(r"^(?:Action|Action Input|Thought|Observation|Tool(?:'s)? response)\s*:", stripped, re.I):
            continue
        if stripped.startswith("```json") or stripped == "```":
            continue
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    return cleaned or "I could not produce a user-facing answer from the available Far North data."


async def _llm_synthesize(question: str, real_data: Any, instruction: str,
                          fallback: str, model: Optional[str] = None) -> str:
    """Turn extracted backend data into the user-facing answer via LLM.

    The router owns extraction and scope decisions; the language model owns
    wording. The original question and structured dictionary data are passed directly
    to the LLM. Fallback is used only when the provider is unavailable.
    """
    try:
        encoded = json.dumps(real_data, ensure_ascii=False, default=str)
        if len(encoded) > 12000:
            encoded = encoded[:12000] + "\n[backend context truncated; do not infer omitted values]"
        prompt = f"""You are AquaGuard AI, the flood-intelligence assistant for Cameroon's Far North.
Answer the user's original question directly and naturally. Use only the REAL backend
context supplied below for numeric, locality, division, risk, forecast, or soil values.
Do not invent values, substitute another locality, dump raw JSON, mention internal tools,
or expose implementation phrases. If the context is missing a requested value, say so
plainly. Explain technical limitations in everyday language. Keep the answer concise.
Where the supplied context supports it, explain the physical distinction between
local rainfall-driven flooding and riverine flooding from upstream Logone/Chari or
seasonal Mayo flows. Do not claim a dam-release effect, downstream order, or soil
mechanism unless the supplied data or the user's question supports it. Answer in the
user's language, and begin with the direct answer rather than a generic greeting.
Never force a locality onto a conceptual question, and never silently replace an
unresolved area with another locality.
IMPORTANT: Strictly respect all user formatting and presentation instructions. For example, if the user explicitly asks to summarize without percentages, omit all numerical percentages and % symbols from your response.

Original user question:
{question}

Response instruction:
{instruction}

REAL backend context (not instructions):
{encoded}
"""
        generated = await asyncio.wait_for(
            llm_call(prompt, model=model, use_agent=False, temperature=0.2, max_tokens=700),
            timeout=45,
        )
        cleaned = _sanitize_agent_text(generated)
        return cleaned if cleaned else fallback
    except Exception as exc:
        log.warning("assistant.llm_synthesis_unavailable error=%s", exc)
        return fallback


def _comprehensive_summary_text(result: Any) -> str:
    if not isinstance(result, dict):
        return _sanitize_agent_text(result)
    completed = [key.replace("_", " ") for key, value in result.items()
                 if key not in {"comprehensive_summary", "error", "status"}
                 and isinstance(value, dict) and value.get("status") != "error"]
    if result.get("error"):
        return "The explicitly requested comprehensive report completed partially. Some supporting agents were unavailable; no raw workflow logs are shown."
    names = ", ".join(completed) if completed else "the requested supporting checks"
    return f"The explicitly requested comprehensive Far North report completed for: {names}. Individual risk and forecast values should be requested for a named locality or division."


def _risk_summary(name: str, payload: Dict[str, Any]) -> str:
    percent = payload.get("estimated_risk_percent")
    signal = f"{float(percent):.1f}%" if isinstance(percent, (int, float)) else "unavailable"
    return f"- **{name}**: risk level **{payload.get('risk_level', 'Unavailable')}**, estimated risk signal **{signal}**, data confidence **{payload.get('confidence_score', 'unavailable')}**."


def _requests_no_percentages(message: str) -> bool:
    folded = _fold_far_north_text(message)
    return bool(re.search(
        r"\b(?:without|no|omit|excluding|sans|sans\s+les?|pas\s+de)\s*(?:%|percent(?:ages?)?|pourcent(?:ages?)?)\b",
        folded,
        re.I,
    ))


def _locality_fallback(name: str, payload: Dict[str, Any], question: str) -> str:
    """Safe provider-outage fallback that still respects presentation requests."""
    level = payload.get("risk_level", "Unavailable")
    if _requests_no_percentages(question):
        return (f"{name} is currently assessed at {level} risk based on available Far North data. "
                "Numerical percentages have been omitted as requested. This is a rules-based assessment, not a probability; follow official alerts and local observations.")
    percent = payload.get("estimated_risk_percent")
    signal = f"{float(percent):.1f}%" if isinstance(percent, (int, float)) else "unavailable"
    conf = payload.get("confidence_score", "unavailable")
    return (f"Operational assessment for {name}: risk level is {level} (estimated risk signal {signal}, data confidence {conf}). "
            "This is a rules-based assessment derived from environmental indicators, not a generated probability.")


def _ranking_text(payload: Dict[str, Any], count: int) -> str:
    rows = list(payload.get("results", []))[:count]
    if not rows:
        return "No static Far North susceptibility ranking is available right now."
    lines = []
    for index, row in enumerate(rows, 1):
        caveat = f" — {row['caveat']}" if row.get("caveat") else ""
        lines.append(f"{index}. **{row.get('name')}** — susceptibility score **{float(row.get('susceptibility_score', 0)):.2f}**, documented event count **{row.get('historical_verified_event_count', 0)}**{caveat}")
    return ("**Far North static susceptibility ranking**\n\n" + "\n".join(lines) +
            "\n\nThis uses terrain and documented historical patterns, not live current conditions or a day-specific forecast.")


async def _route_nat_intent(request: NATChatMessage) -> Optional[Dict[str, Any]]:
    """Route conversational request through intent detection, explicit entity resolution, and LLM synthesis."""
    message = request.message or ""
    folded = _fold_far_north_text(message)

    # 1. Explicit Three-Tier Location Resolution
    loc_res = _resolve_location_hierarchy(message, request.context, request.location)

    # 2. Intent Detection
    intent = _detect_assistant_intent(message, loc_res, request.context)

    # An explicit full report is the only path allowed to run the legacy multi-agent workflow
    explicit_comprehensive = bool(re.search(r"\b(?:full|complete|comprehensive|all\s+agents|data\s+freshness|emergency\s+readiness)\b", folded, re.I))
    if request.agent_type == "all" and explicit_comprehensive:
        return None

    # Handle explicitly out-of-scope locations (Paris, Yaoundé, Douala, Texas)
    if loc_res.location_type == "out_of_scope":
        _log_router_decision(request, "OUT_OF_SCOPE", loc_res.user_location, loc_res.resolved_location,
                             "exact", False, False, "none")
        if loc_res.notes:
            fallback = loc_res.notes
        else:
            fallback = f"I am configured exclusively for Cameroon's Far North region and do not have operational data for {loc_res.resolved_location}."
        return {
            "status": "REFUSE_OUT_OF_BOUNDS",
            "output": await _llm_synthesize(
                message,
                {"scope": "Cameroon Far North only", "outside_location": loc_res.resolved_location, "explanation": fallback},
                "Politely explain the geographic coverage boundary and name the actual Cameroon region when known.",
                fallback,
            ),
        }

    # Decline fictional / creative requests without inventing data
    creative_request = bool(re.search(r"\b(?:story|character|fiction|novel|short\s+story|lost\s+in\s+the\s+forest)\b", folded, re.I))
    if creative_request:
        _log_router_decision(request, "UNKNOWN_GENERAL_CONVERSATION", loc_res.user_location, loc_res.resolved_location,
                             "unresolved", False, False, "none")
        fallback = "I’m a flood-intelligence assistant, so I can’t write fictional stories or attach made-up events to real Far North localities. I can help with verified flood history, risk, forecasts, or safety guidance."
        return {
            "status": "OUTSIDE_DATA_SCOPE",
            "output": await _llm_synthesize(
                message,
                {"scope": "verified Far North flood intelligence", "request_type": "creative writing"},
                "Politely decline the creative-writing request without asking the user to choose a real locality.",
                fallback,
            ),
        }

    # -------------------------------------------------------------------------
    # BRANCH A: GENERAL_CONCEPTUAL (No locality or flood tool required)
    # -------------------------------------------------------------------------
    if intent == "GENERAL_CONCEPTUAL":
        _log_router_decision(request, "GENERAL_CONCEPTUAL", loc_res.user_location, loc_res.resolved_location,
                             loc_res.confidence, False, False, "none")
        conceptual_context = {
            "question_type": "general_conceptual",
            "concept_query": message,
            "requested_locality": loc_res.resolved_location if loc_res.location_type == "locality" else None,
            "backend_data_required": False,
        }
        fallback = _local_flood_answer(message)
        output = await _llm_synthesize(
            message,
            conceptual_context,
            "Explain the hydrological or meteorological concept clearly, accurately, and directly. Do not require or imply a current locality prediction.",
            fallback,
        )
        return {"status": "llm_synthesized_knowledge", "output": output}

    # -------------------------------------------------------------------------
    # BRANCH B: SYSTEM_EXPLANATION (No locality or flood tool required)
    # -------------------------------------------------------------------------
    if intent == "SYSTEM_EXPLANATION":
        _log_router_decision(request, "SYSTEM_EXPLANATION", loc_res.user_location, loc_res.resolved_location,
                             loc_res.confidence, False, False, "none")
        system_context = {
            "system_name": "AquaGuard AI (Cameroon Flood Intelligence System)",
            "components": {
                "prediction_engine": "Authoritative Far North operational flood risk engine combining terrain susceptibility (DEM slope, elevation), hydrological networks (HydroRIVERS, basin upstream drainage), satellite precipitation (CHIRPS), reanalysis soil moisture and runoff (ERA5-Land), river discharge (GloFAS), and canonical documented flood events (2015-2025).",
                "ai_assistant": "Supporting conversational and explanation layer designed to interpret flood predictions, answer hydrological concepts, explain risk factors, and provide safety guidance without hallucinating predictions or inventing data.",
            },
            "coverage": "Far North Region of Cameroon (34 environmental coverage localities across 6 divisions).",
        }
        fallback = _local_flood_answer(message)
        output = await _llm_synthesize(
            message,
            system_context,
            "Explain how the flood prediction system and its two core components (authoritative engine + conversational assistant) work in clear, accessible language.",
            fallback,
        )
        return {"status": "llm_synthesized_system", "output": output}

    # -------------------------------------------------------------------------
    # BRANCH C: LOCATION_INFORMATION (Yaérés, regional geography, fishermen)
    # -------------------------------------------------------------------------
    if intent == "LOCATION_INFORMATION" or (loc_res.resolved_location == "Yaérés" and not re.search(r"\b(?:risk|flood\s+risk|forecast|prevision|risque)\b", folded, re.I)):
        _log_router_decision(request, "LOCATION_INFORMATION", loc_res.user_location, loc_res.resolved_location,
                             loc_res.confidence, False, False, "none")
        if loc_res.resolved_location == "Yaérés" or "yaere" in folded:
            yaeres_context = {
                "location": "Yaérés",
                "region": "Far North Cameroon (Logone-Chari river basin)",
                "environmental_features": "Vast seasonal floodplain that floods annually during the wet season and dries in the dry season. Vital ecosystem supporting biodiversity, pastoral grazing, and rich artisanal fisheries.",
                "fishermen_situation": "Local fishermen rely heavily on the annual flood cycle of the Yaérés. Seasonal flooding replenishes fish stocks and creates vast fishing grounds; receding floodwaters allow concentrated harvesting. Rapid abnormal flooding, dyke disruptions, or prolonged dry spells directly impact their livelihoods and safety.",
                "prediction_dataset_scope": "The authoritative prediction engine calculates point risk for 34 specific Far North municipalities and does not contain a specific point prediction for the Yaérés itself. Crucially, do not substitute Yagoua or any other municipality for Yaérés.",
            }
            fallback = "Les Yaérés sont des plaines inondables du bassin du Logone-Chari. L'alternance naturelle entre crue et décrue soutient la pêche artisanale, l'élevage et l'agriculture, mais expose aussi les campements lorsque la montée des eaux est soudaine. Le système ne dispose pas d'une prédiction chiffrée propre aux Yaérés et ne doit pas leur substituer Yagoua."
            output = await _llm_synthesize(
                message,
                yaeres_context,
                "Answer the user's question about the Yaérés and/or fishermen accurately. Explain the geographic and environmental context. Clearly acknowledge that while you can explain the flood dynamics in the Yaérés, the authoritative quantitative prediction model covers 34 specific Far North municipalities and does not generate a point prediction for the Yaérés itself. Do NOT substitute Yagoua for Yaérés.",
                fallback,
            )
            return {"status": "llm_synthesized_domain", "output": output}

        location_context = {
            "requested_location": loc_res.resolved_location or loc_res.user_location,
            "location_type": loc_res.location_type,
            "region": "Cameroon Far North",
        }
        output = await _llm_synthesize(
            message,
            location_context,
            "Provide accurate geographic and contextual information about the requested Far North location without inventing flood risk metrics.",
            _local_flood_answer(message),
        )
        return {"status": "llm_synthesized_location", "output": output}

    # -------------------------------------------------------------------------
    # BRANCH D: SAFETY_PREPAREDNESS
    # -------------------------------------------------------------------------
    if intent == "SAFETY_PREPAREDNESS":
        _log_router_decision(request, "SAFETY_PREPAREDNESS", loc_res.user_location, loc_res.resolved_location,
                             loc_res.confidence, False, False, "none")
        safety_context = {
            "scope": "Far North flood safety and preparedness",
            "location": loc_res.resolved_location or "Far North",
            "session_context": request.context or {},
        }
        fallback = _local_flood_answer(message)
        output = await _llm_synthesize(
            message,
            safety_context,
            "Provide practical, actionable flood preparedness and safety guidance. Explain monitoring versus evacuation triggers clearly without inventing numbers.",
            fallback,
        )
        return {"status": "ROUTED_PRACTICAL_GUIDANCE", "output": output}

    # -------------------------------------------------------------------------
    # BRANCH E: RANKING QUERY
    # -------------------------------------------------------------------------
    bare_quantity = bool(re.fullmatch(r"\s*(?:just\s+)?(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*", folded, re.I))
    ranking_request = bare_quantity or (bool(re.search(r"\b(?:highest|top\s*\d*|most\s+(?:at\s+)?risk|where\s+should\s+i\s+worry|which\s+(?:area|region|locality)|give\s+me|show\s+me|list|name|just)\b", folded, re.I)) and bool(re.search(r"\b(?:risk|flood|danger|worry|localit(?:y|ies)|areas?|places?)\b", folded, re.I)))
    if ranking_request and not loc_res.prediction_location and not loc_res.location_type == "division":
        count = _ranking_count(message)
        _log_router_decision(request, "FLOOD_RISK_QUERY", None, None, "unresolved", True, True, "get_top_risk_localities")
        payload = await asyncio.to_thread(_get_farnorth_top_risk, count, None)
        fallback = _ranking_text(payload, count)
        return {"status": "ROUTED_RANKING", "output": await _llm_synthesize(message, payload, f"Return exactly {count} ranked areas and explain that this is static susceptibility based on terrain and documented historical events, not a live forecast.", fallback)}

    # -------------------------------------------------------------------------
    # BRANCH F: DIVISION RISK QUERY
    # -------------------------------------------------------------------------
    if loc_res.location_type == "division" and loc_res.resolved_location:
        division = loc_res.resolved_location
        _log_router_decision(request, "FLOOD_RISK_QUERY", division, division, "exact", True, True, "get_division_risk")
        payload = await asyncio.to_thread(_get_farnorth_division_risk, division)
        fallback = _sanitize_agent_text(payload.get("coverage_note") if not payload.get("risk") else (f"**{division} division — maximum covered-locality risk**\n\nMaximum: **{payload['risk'].get('locality')}**, **{payload['risk'].get('estimated_risk_percent')}%** ({payload['risk'].get('risk_level')}).\n\nCoverage: {payload.get('coverage_note')}"))
        return {"status": "ROUTED_DIVISION", "output": await _llm_synthesize(message, payload, "Answer the division question using the maximum covered-locality risk and state the coverage note.", fallback),
                "conversation_context": {"division": division, "division_result": payload}}

    # -------------------------------------------------------------------------
    # BRANCH G: COMPARISON (2 or more covered localities)
    # -------------------------------------------------------------------------
    localities = _farnorth_names()
    matched_names = _whole_name_matches(message, localities)
    comparing = bool(re.search(r"\b(?:compare|versus|vs\.?|against)\b", folded))
    if comparing and len(matched_names) >= 2:
        selected = matched_names[:2]
        _log_router_decision(request, "FLOOD_RISK_QUERY", ",".join(selected), ",".join(selected), "exact", True, True, "get_locality_risk x2")
        results = await asyncio.gather(*(asyncio.to_thread(_get_farnorth_risk, name) for name in selected), return_exceptions=True)
        comparison_data = {name: result for name, result in zip(selected, results) if not isinstance(result, Exception)}
        fallback = f"Comparing {selected[0]} and {selected[1]} from operational assessment data."
        instruction = "Compare both named localities directly and recommend preparation priorities based only on their real results. Strictly respect user instructions on percentages."
        if _requests_no_percentages(message):
            instruction += " Omit all percentages and % signs from your comparison."
        return {"status": "ROUTED_COMPARISON", "output": await _llm_synthesize(message, comparison_data, instruction, fallback)}

    # -------------------------------------------------------------------------
    # BRANCH H: FORECAST QUERY FOR LOCALITY
    # -------------------------------------------------------------------------
    forecast_query = bool(re.search(r"\b(?:forecast|tomorrow|upcoming|next\s+(?:few|\d+)\s+days?|in\s+\d+\s+days?|prevision|pr[eé]vision)\b", folded, re.I))
    if forecast_query and loc_res.prediction_location:
        name = loc_res.prediction_location
        _log_router_decision(request, "FLOOD_RISK_QUERY", loc_res.user_location, name, "exact", True, True, "get_locality_forecast")
        raw_payload = await asyncio.to_thread(_get_farnorth_forecast, name, None)
        payload = {"requested_locality": loc_res.user_location or name, "resolved_locality": raw_payload.get("locality", name) if isinstance(raw_payload, dict) else name,
                   "forecast": raw_payload}
        fallback = _sanitize_agent_text(raw_payload)
        if "required discharge lag" in fallback.lower():
            fallback = "Upstream river-flow data for part of this forecast has not updated yet, so the experimental forecast number is unavailable for those days. The baseline risk assessment remains available."
        instruction = "Summarize the requested forecast and humanize any missing-discharge or lag limitation. Never invent a probability."
        if _requests_no_percentages(message):
            instruction += " Strictly omit all percentages and % symbols from the response."
        return {"status": "ROUTED_FORECAST", "output": await _llm_synthesize(message, payload, instruction, fallback),
                "conversation_context": {"locality": name, "forecast": raw_payload}}

    # -------------------------------------------------------------------------
    # BRANCH I: LOCALITY RISK QUERY / PREDICTION EXPLANATION / FOLLOW-UP
    # -------------------------------------------------------------------------
    if loc_res.prediction_location:
        name = loc_res.prediction_location
        tool_name = "get_locality_risk"
        _log_router_decision(request, intent, loc_res.user_location, name, "exact", True, True, tool_name)
        raw_payload = await asyncio.to_thread(_get_farnorth_risk, name)
        payload = {
            "requested_locality": loc_res.user_location or name,
            "resolved_locality": raw_payload.get("locality", name),
            "prediction": raw_payload
        }
        fallback = _locality_fallback(name, raw_payload, message)

        if _requests_no_percentages(message):
            instruction = (
                "Answer the user's question using the operational flood prediction result. "
                "CRITICAL: The user explicitly requested NO percentages. You MUST NOT include any percentages or '%' characters in your answer. "
                "Explain the risk level, data confidence, and physical indicators (soil moisture, rainfall, river distance) purely in words."
            )
        elif intent == "PREDICTION_EXPLANATION":
            instruction = (
                "Explain why this locality received its operational risk level based strictly on the provided real data factors "
                "(susceptibility score, soil moisture, 3-day rainfall, river distance, and historical events). "
                "Clarify the actual risk level and factors without inventing reasons."
            )
        elif intent == "FOLLOW_UP_TO_PREVIOUS_RESULT":
            instruction = (
                "Answer the follow-up question using the supplied previous prediction context. "
                "Explain the contributing physical factors and indicators. Do not ask for the locality again and do not invent missing values."
            )
        else:
            instruction = (
                "Answer the locality flood risk question directly using the operational result. "
                "Preserve the distinction between a rules-based risk signal and a probability; estimated_risk_percent must never be called a probability. "
                "If resolved_locality differs from requested_locality, disclose that explicitly rather than silently renaming the place."
            )

        output = await _llm_synthesize(message, payload, instruction, fallback)
        status = "ROUTED_FOLLOW_UP" if intent == "FOLLOW_UP_TO_PREVIOUS_RESULT" else "ROUTED_LOCALITY"
        return {"status": status, "output": output, "conversation_context": {"locality": name, "prediction": raw_payload}}

    # -------------------------------------------------------------------------
    # BRANCH J: EXPLICIT LOCALITY REQUESTED BUT NOT IN PREDICTION DATABASE (e.g. Yaérés)
    # -------------------------------------------------------------------------
    if loc_res.resolved_location and loc_res.prediction_location is None:
        _log_router_decision(request, intent, loc_res.user_location, loc_res.resolved_location,
                             "exact", False, False, "none")
        uncovered_context = {
            "requested_location": loc_res.resolved_location,
            "prediction_status": "not_in_prediction_dataset",
            "message": f"The authoritative flood prediction engine covers 34 specific Far North municipalities and does not have a quantitative point prediction for '{loc_res.resolved_location}'. Do not substitute Yagoua or any other locality."
        }
        fallback = f"I can explain the flood dynamics in {loc_res.resolved_location}, but the current prediction dataset does not provide a specific prediction for {loc_res.resolved_location} itself. I should not substitute Yagoua or another city for {loc_res.resolved_location}."
        output = await _llm_synthesize(
            message,
            uncovered_context,
            f"Clearly explain that while you can describe the flood dynamics in {loc_res.resolved_location}, the authoritative prediction model covers 34 specific Far North municipalities and does not produce an authoritative point prediction for {loc_res.resolved_location}. Emphasize that you cannot substitute another city like Yagoua.",
            fallback,
        )
        return {"status": "LOCALITY_NOT_COVERED", "output": output}

    # -------------------------------------------------------------------------
    # BRANCH K: UNSCOPED RISK QUERY (Missing locality)
    # -------------------------------------------------------------------------
    if intent in {"FLOOD_RISK_QUERY", "PREDICTION_EXPLANATION"}:
        _log_router_decision(request, intent, None, None, "unresolved", True, False, "none")
        fallback = "Please name a Far North locality or division for a real risk or forecast lookup. I will not attach an unscoped question to an arbitrary place."
        output = await _llm_synthesize(
            message,
            {"status": "missing locality or division"},
            "Ask briefly for a Far North locality or division; do not invent one.",
            fallback,
        )
        return {"status": "LOCALITY_REQUIRED", "output": output}

    # -------------------------------------------------------------------------
    # BRANCH L: GENERAL CONVERSATION FALLBACK
    # -------------------------------------------------------------------------
    _log_router_decision(request, "UNKNOWN_GENERAL_CONVERSATION", None, None, "unresolved", False, False, "none")
    output = await _llm_synthesize(
        message,
        {"status": "general conversation"},
        "Respond helpfully and naturally, distinguishing general education from live Far North data.",
        _local_flood_answer(message),
    )
    return {"status": "ROUTED_GENERAL", "output": output}


@app.post(_api("nat/chat"), response_model=NATChatResponse)
async def chat_with_nat_agent(user_id: UserID, request: NATChatMessage):
    """Chat with NAT agents (non-streaming)"""
    user_id = _require_authenticated_identity(user_id)
    if not _nat_runner:
        raise HTTPException(status_code=503, detail="NAT agents are not available")
    
    try:
        request.context = _assistant_context_for(user_id, request.context)
        routed = await _route_nat_intent(request)
        if routed is not None:
            _remember_assistant_context(user_id, routed)
            return NATChatResponse(output=_sanitize_agent_text(routed.get("output")), agent_type=request.agent_type,
                                   status=routed.get("status", "routed"), timestamp=datetime.now(timezone.utc).isoformat())
        # Deterministic safety route for ranking requests.  Keep quantity
        # constraints intact instead of allowing an LLM to expand "two" to a
        # default five-item answer.
        generic_location = str(request.location or "").strip().casefold() in {"", "cameroon", "cameroon region", "cameroon far north", "far north"}
        def has_named_place(message: str) -> bool:
            """Require a complete gazetteer/division name before data lookup."""
            choices = list(FAR_NORTH_DIVISIONS)
            try:
                if _get_farnorth_cache is not None:
                    cache = _get_farnorth_cache()
                    choices.extend(str(v) for v in getattr(cache, "index", []) if str(v).strip())
            except Exception:
                pass
            import unicodedata
            def fold(value: str) -> str:
                return "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch)).casefold()
            haystack = fold(message or "")
            for choice in choices:
                tokens = re.findall(r"[a-z0-9]+", fold(choice))
                if tokens and re.search(r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, tokens)) + r"(?![a-z0-9])", haystack):
                    return True
            return False
        # Handle educational questions before entity extraction or an agent
        # tool call. This keeps generic wording from becoming a locality query.
        educational_question = bool(re.search(r"\b(?:what\s+causes?\s+flood(?:ing)?|explain\s+flood\s+stages?|is\s+it\s+safe\s+to\s+travel|general\s+flood\s+safety|how\s+do\s+i\s+prepare)\b", request.message or "", re.I)) or bool(re.search(r"\bmaroua\b.*\bmayos?\b|\bmayos?\b.*\bmaroua\b", request.message or "", re.I))
        if request.agent_type == "risk_analyzer" and educational_question:
            return NATChatResponse(output=_local_flood_answer(request.message), agent_type=request.agent_type,
                                   status="deterministic_knowledge_base", timestamp=datetime.now(timezone.utc).isoformat())
        bare_quantity = bool(re.fullmatch(r"\s*(?:just\s+)?(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*", request.message or "", re.I))
        ranking_request = bare_quantity or (bool(re.search(r"\b(?:highest|top\s*\d*|most\s+(?:at\s+)?risk|which\s+(?:area|region|locality)|give\s+me|show\s+me|list|name|just)\b", request.message or "", re.I)) and bool(re.search(r"\b(?:risk|flood|danger|worry|localit(?:y|ies)|areas?|places?)\b", request.message or "", re.I)))
        if request.agent_type == "risk_analyzer" and ranking_request and generic_location:
            count_match = re.search(r"\b(?:top|give\s+me|show\s+me|list|name|just)\s+(?:just\s+)?(\d{1,2})\b", request.message or "", re.I)
            word_counts = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
            word_match = re.search(r"\b(?:give\s+me|show\s+me|list|name|just)\s+(?:just\s+)?(one|two|three|four|five|six|seven|eight|nine|ten)\b", request.message or "", re.I)
            bare_match = re.fullmatch(r"\s*(?:just\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*", request.message or "", re.I)
            count = int(count_match.group(1)) if count_match else word_counts.get(word_match.group(1).casefold(), 0) if word_match else (int(bare_match.group(1)) if bare_match and bare_match.group(1).isdigit() else word_counts.get(bare_match.group(1).casefold(), 5) if bare_match else 5)
            count = max(1, min(count or 5, 20))
            ranking = await asyncio.to_thread(_get_farnorth_top_risk, count, None)
            names = [row.get("name") for row in ranking.get("results", [])][:count]
            output = (f"Real tool call: get_top_risk_localities(n={count}).\n\n"
                      f"Static Far North susceptibility ranking (not live current conditions):\n"
                      + "\n".join(f"{i}. {name}" for i, name in enumerate(names, 1)))
            return NATChatResponse(output=output, agent_type=request.agent_type,
                                   status="deterministic_far_north_tool", timestamp=datetime.now(timezone.utc).isoformat())

        # Deterministic safety route for the common open-ended forecast query.
        # Do not let the LLM invent a city or feed fabricated numeric inputs to
        # a calculator. With no named locality, only the real static ranking is
        # safe; a dated forecast requires the user to choose a covered place.
        open_forecast = bool(re.search(r"\b(?:in|within|next)\s*(?:\d+\s*[-–]\s*)?\d*\s*days?\b|\btomorrow\b|\bupcoming\b", request.message or "", re.I))
        if request.agent_type == "risk_analyzer" and open_forecast and generic_location:
            ranking = await asyncio.to_thread(_get_farnorth_top_risk, 5, None)
            names = [r.get("name") for r in ranking.get("results", [])]
            output = ("Real tool call: get_top_risk_localities(n=5).\n\n"
                      "No locality was named, so this is a static susceptibility ranking, "
                      "not a 2–3 day forecast. Choose a covered Far North locality for a "
                      "dated forecast.\n\nCandidates: " + ", ".join(str(n) for n in names))
            return NATChatResponse(output=output, agent_type=request.agent_type,
                                   status="deterministic_far_north_tool", timestamp=datetime.now(timezone.utc).isoformat())

        # Never let an unscoped sentence fall through to an LLM that may pick
        # an arbitrary locality. General answers are handled locally; data
        # questions must include a complete Far North locality or division.
        if request.agent_type == "risk_analyzer" and generic_location and not has_named_place(request.message):
            if re.search(r"\b(?:risk\s+score|score|flood\s+stage|stages?|cause|safety|safe|prepare|evacuat)\b", request.message or "", re.I):
                return NATChatResponse(output=_local_flood_answer(request.message), agent_type=request.agent_type,
                                       status="deterministic_knowledge_base", timestamp=datetime.now(timezone.utc).isoformat())
            return NATChatResponse(output="Please name a Far North locality or division for a real risk/forecast lookup. I will not attach an unscoped question to an arbitrary place.", agent_type=request.agent_type,
                                   status="locality_required", timestamp=datetime.now(timezone.utc).isoformat())
        # Execute NAT agent workflow based on agent type
        if request.agent_type == "data_collector":
            result = await _nat_runner.run_data_collector(request.custom_prompt or request.message)
        elif request.agent_type == "risk_analyzer":
            result = await _nat_runner.run_risk_analyzer(request.location, request.custom_prompt or request.message)
        elif request.agent_type == "emergency_responder":
            result = await _nat_runner.run_emergency_responder(request.scenario, request.custom_prompt or request.message)
        elif request.agent_type == "predictor":
            result = await _nat_runner.run_predictor(request.forecast_hours, request.location, request.custom_prompt or request.message)
        elif request.agent_type == "h2ogpte_agent":
            result = await _nat_runner.run_h2ogpte_agent("train_model", request.custom_prompt or request.message, request.custom_prompt)
        elif request.agent_type == "all":
            result = await _nat_runner.run_comprehensive_analysis()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown agent type: {request.agent_type}")
        
        if request.agent_type == "all":
            output = await _llm_synthesize(
                request.message,
                result,
                "Write a concise comprehensive Far North report from the supporting-agent data. Do not expose logs or raw JSON.",
                _comprehensive_summary_text(result),
            )
        else:
            output = await _llm_synthesize(
                request.message,
                result,
                "Write the final answer directly from the agent's real result; do not expose workflow scaffolding.",
                _sanitize_agent_text(result.get("output", result)),
            )
        return NATChatResponse(
            output=output,
            agent_type=request.agent_type,
            status=result.get("status", "completed"),
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
    except Exception as e:
        log.error(f"Failed to process NAT chat: {str(e)}")
        return NATChatResponse(
            output=LLM_UNAVAILABLE_MESSAGE,
            agent_type=request.agent_type,
            status="local_fallback",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

@app.post(_api("nat/chat/stream"))
async def stream_chat_with_nat_agent(user_id: UserID, request: NATChatMessage):
    """Stream chat with NAT agents with filtered logs"""
    # Import before defining the routed generator; otherwise the later
    # function-local import makes ``json`` a free variable in that closure.
    import json
    if not _nat_runner:
        raise HTTPException(status_code=503, detail="NAT agents are not available")
    
    try:
        request.context = _assistant_context_for(user_id, request.context)
        routed = await _route_nat_intent(request)
        if routed is not None:
            _remember_assistant_context(user_id, routed)
            async def routed_stream():
                yield f"data: {json.dumps({'type': 'start', 'agent_type': request.agent_type, 'location': request.location}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'result', 'output': _sanitize_agent_text(routed.get('output')), 'status': routed.get('status', 'routed')}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return StreamingResponse(routed_stream(), media_type="text/event-stream; charset=utf-8", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})
        import asyncio
        import logging
        
        async def generate_nat_stream():
            try:
                import threading
                import concurrent.futures
                from collections import deque
                import io
                import sys
                
                # Create custom log handler to capture logs
                log_queue = deque()
                done_event = threading.Event()
                error_container = {'error': None}
                result_container = {'result': None}
                
                # Custom log handler for capturing NAT logs
                class NATLogHandler(logging.Handler):
                    def emit(self, record):
                        message = record.getMessage()
                        
                        # Include important agent logs and filter out noise
                        should_include = False
                        
                        # Always include warnings and errors
                        if record.levelno >= logging.WARNING:
                            should_include = True
                        
                        # Include agent-specific logs
                        elif any(keyword in message for keyword in [
                            '[AGENT]', 'Agent input:', 'Agent\'s thoughts:', 'Final Answer:',
                            'Action:', 'Action Input:', 'Tool\'s response:', 'Calling tools:',
                            'agent.react_agent', 'nat_base', 'Workflow completed'
                        ]):
                            should_include = True
                        
                        # Exclude HTTP requests and other noise
                        elif any(noise in message for noise in [
                            'HTTP Request:', 'httpx', 'POST http', 'GET http'
                        ]):
                            should_include = False
                        
                        if should_include:
                            log_entry = {
                                'timestamp': record.created,
                                'level': record.levelname,
                                'message': message,
                                'logger': record.name
                            }
                            log_queue.append(log_entry)
                
                # Add our handler to capture logs
                handler = NATLogHandler()
                logging.getLogger().addHandler(handler)
                
                def run_nat_sync():
                    try:
                        # Create a new event loop for this thread
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        # Execute NAT agent workflow based on agent type
                        if request.agent_type == "data_collector":
                            result = loop.run_until_complete(_nat_runner.run_data_collector(request.custom_prompt or request.message))
                        elif request.agent_type == "risk_analyzer":
                            result = loop.run_until_complete(_nat_runner.run_risk_analyzer(request.location, request.custom_prompt or request.message))
                        elif request.agent_type == "emergency_responder":
                            result = loop.run_until_complete(_nat_runner.run_emergency_responder(request.scenario, request.custom_prompt or request.message))
                        elif request.agent_type == "predictor":
                            result = loop.run_until_complete(_nat_runner.run_predictor(request.forecast_hours, request.location, request.custom_prompt or request.message))
                        elif request.agent_type == "h2ogpte_agent":
                            result = loop.run_until_complete(_nat_runner.run_h2ogpte_agent("train_model", request.custom_prompt or request.message, request.custom_prompt))
                        elif request.agent_type == "all":
                            result = loop.run_until_complete(_nat_runner.run_comprehensive_analysis())
                        else:
                            raise ValueError(f"Unknown agent type: {request.agent_type}")
                        
                        result_container['result'] = result
                        done_event.set()
                        return result
                        
                    except Exception as e:
                        error_container['error'] = str(e)
                        done_event.set()
                        return None
                    finally:
                        # Remove our log handler
                        logging.getLogger().removeHandler(handler)
                
                # Start NAT agent in background thread
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    nat_future = executor.submit(run_nat_sync)
                    
                    # Send initial metadata
                    yield f"data: {json.dumps({'type': 'start', 'agent_type': request.agent_type, 'location': request.location})}\n\n"
                    
                    # Stream logs as they arrive
                    while not done_event.is_set() or log_queue:
                        if log_queue:
                            # Logs remain server-side for diagnostics only;
                            # never stream ReAct scaffolding or raw warnings
                            # into the user conversation.
                            log_queue.clear()
                        else:
                            # Small delay and send keepalive
                            await asyncio.sleep(0.1)
                            if not done_event.is_set():
                                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                    
                    # Wait for completion and get result
                    final_result = nat_future.result()
                    
                    if error_container['error'] or (
                        isinstance(result_container.get('result'), dict)
                        and result_container['result'].get('status') == 'error'
                    ):
                        yield f"data: {json.dumps({'type': 'result', 'output': _sanitize_agent_text(_local_flood_answer(request.message)), 'status': 'local_fallback'}, ensure_ascii=False)}\n\n"
                    else:
                        result = result_container['result']
                        if request.agent_type == 'all':
                            output = await _llm_synthesize(request.message, result,
                                "Write a concise comprehensive Far North report from the supporting-agent data; do not expose logs or raw JSON.",
                                _comprehensive_summary_text(result))
                        else:
                            output = await _llm_synthesize(request.message, result,
                                "Write the final answer directly from the real agent result; do not expose workflow scaffolding.",
                                _sanitize_agent_text(result.get('output', result)))
                        yield f"data: {json.dumps({'type': 'result', 'output': output, 'status': result.get('status', 'completed')}, ensure_ascii=False)}\n\n"
                    
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
            except Exception as e:
                log.error("NAT stream generation error: %s", e)
                yield f"data: {json.dumps({'type': 'error', 'error': 'LLM service temporarily unavailable'})}\n\n"
        
        return StreamingResponse(
            generate_nat_stream(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            }
        )
        
    except Exception as e:
        log.error(f"Failed to process NAT streaming chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process NAT streaming chat")


# =============================================================================
# AI Provider Management API Endpoints
# =============================================================================

class AIProviderRequest(BaseModel):
    """Request model for AI provider operations"""
    provider: str = "auto"  # "h2ogpte", "nvidia", "auto"
    model: Optional[str] = None
    use_agent: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    context: Optional[Dict[str, Any]] = None

class EnhancedChatMessage(BaseModel):
    """Enhanced chat message model with provider selection"""
    message: str
    watershed_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None
    provider: str = "auto"  # "h2ogpte", "nvidia", "auto"
    model: Optional[str] = None
    use_agent: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

class EnhancedChatResponse(BaseModel):
    """Enhanced chat response with provider metadata"""
    response: str
    provider_used: str
    model_used: str
    agent_used: bool
    confidence: float
    recommendations: List[str] = []
    timestamp: str

def _local_flood_answer(question: str) -> str:
    """Context-aware offline answer used when remote LLM/NAT is unavailable."""
    q = (question or '').lower()
    if ('humid' in q and 'sol' in q) or 'soil moisture' in q:
        return ("L'humidité du sol indique la quantité d'eau présente dans la couche de sol analysée. "
                "Une valeur plus élevée signifie généralement que le sol a moins de capacité d'absorber une nouvelle pluie, "
                "mais cette mesure n'est pas à elle seule une probabilité d'inondation : il faut aussi regarder la pluie, le relief, "
                "le drainage et les cours d'eau voisins.")
    if 'digue' in q or 'dyke' in q or 'dike' in q:
        return ("Une digue est un ouvrage construit pour retenir ou guider l'eau et protéger des zones habitées ou agricoles. "
                "Elle peut réduire l'inondation dans certaines conditions, mais une brèche ou un débordement peut provoquer une montée rapide de l'eau. "
                "Il faut suivre les consignes des autorités et ne jamais approcher une digue endommagée.")
    if 'yaere' in q or 'yaérés' in q:
        return ("Les Yaérés sont des plaines inondables du bassin du Logone-Chari. Leur alternance entre inondation et assèchement soutient les sols, la pêche, "
                "l'élevage et l'agriculture, mais peut aussi exposer les populations et les routes lorsque l'eau monte. Le système ne doit pas remplacer les mesures locales par une autre ville.")
    if 'baseline' in q or 'rules-based status' in q or 'weekly planning' in q:
        return ("BASELINE means the operational rules-based status produced from the available environmental and historical signals. "
                "It is a consistent planning signal, not a percentage probability and not a guarantee that flooding will or will not occur. "
                "For weekly planning, use it with official alerts, rainfall and river observations, and local preparedness actions.")
    if 'maroua' in q and 'mayo' in q:
        return ("I don't have specific backend data identifying Maroua's named waterways. "
                "I can provide the available locality risk and forecast signals for Maroua, "
                "but I will not substitute a generic waterway definition.")
    if 'cause' in q or 'causes' in q or 'rainfall-driven' in q or 'river-driven' in q:
        return ("Flooding can be rainfall-driven, when intense rain overwhelms drainage or "
                "saturates the ground, or river-driven, when upstream runoff raises a river "
                "until it overtops its channel or defenses. Both can combine; the Blangoua "
                "case illustrates river overflow even when local rainfall is low.")
    if (('medium' in q and 'score' in q) or '65%' in q) and ('prediction' in q or 'risk' in q or 'score' in q):
        return ("A medium score of 65% is an elevated rules-based signal, not a measured "
                "65% probability of flooding. It summarizes the selected area's available "
                "environmental and historical indicators; check live alerts and local river "
                "conditions before making safety decisions.")
    if 'risk score' in q or 'score of' in q:
        return ("A risk score summarizes the rules-based flood signals for the selected area; "
                "it is not a percentage probability. A score around 6.5 should be treated as "
                "elevated risk: check rainfall and soil conditions, follow local alerts, and "
                "avoid floodwater.")
    if 'flood stage' in q or 'stages' in q:
        return ("Flood stage is the water level at which a river begins to affect its banks. "
                "Above flood stage, impacts generally progress from minor nuisance flooding "
                "to moderate and then major flooding. The exact levels are station-specific, "
                "so use the local authority's gauge guidance.")
    if 'prepare' in q or 'safety' in q or 'safe' in q:
        return ("Prepare by monitoring official alerts, moving valuables and medicines above "
                "expected water levels, keeping clean water and a charged phone ready, and "
                "planning a route to higher ground. Never walk or drive through moving water.")
    return ("I'm having trouble processing that request right now. Try asking about a "
            "specific Far North locality or division by name.")

LLM_UNAVAILABLE_MESSAGE = "I'm having trouble processing that request right now. Try asking about a specific Far North locality or division by name."

@app.get(_api("ai/providers"))
async def get_available_providers():
    """Get available AI providers and their capabilities"""
    try:
        providers_info = get_all_providers_info()
        current_provider = settings.ai_provider
        
        return {
            "providers": providers_info,
            "current_default": current_provider,
            "nvidia_features": {
                "agents_enabled": settings.enable_nvidia_agents,
                "rag_enabled": settings.enable_nvidia_rag,
                "evaluator_enabled": settings.enable_nvidia_evaluator
            }
        }
    except Exception as e:
        log.error(f"Failed to get available providers: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get available providers")

@app.get(_api("ai/providers/{provider_name}"))
async def get_provider_details(provider_name: str):
    """Get detailed information about a specific provider"""
    try:
        provider_info = get_provider_info(provider_name)
        return provider_info
    except Exception as e:
        log.error(f"Failed to get provider details: {str(e)}")
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found or not available")

@app.get(_api("ai/providers/{provider_name}/models"))
async def get_provider_models(provider_name: str):
    """Get available models for a specific provider"""
    try:
        models = get_available_llm_models(provider_name)
        provider_info = get_provider_info(provider_name)
        
        return {
            "provider": provider_name,
            "models": models,
            "default_model": provider_info.get("default_model"),
            "supports_agents": provider_info.get("supports_agents", False)
        }
    except Exception as e:
        log.error(f"Failed to get models for provider {provider_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get models for provider {provider_name}")

@app.post(_api("ai/chat/enhanced"), response_model=EnhancedChatResponse)
async def enhanced_chat_with_ai(user_id: UserID, request: EnhancedChatMessage):
    """Enhanced chat with AI assistant with provider selection"""
    user_id = _require_authenticated_identity(user_id)
    try:
        # Determine which provider to use
        provider_name = request.provider if request.provider != "auto" else None

        # The enhanced endpoint is the primary UI path.  Keep it on the same
        # intent/entity router as the normal and NAT endpoints; otherwise a
        # frontend request could bypass location validation and fall back to
        # the legacy generic prompt.  The router calls the authoritative
        # Far-North engine when needed and gives the final LLM the original
        # question plus structured backend data.
        session_context = _assistant_context_for(user_id, request.context)
        routed_request = NATChatMessage(
            message=request.message,
            agent_type="all" if request.use_agent else "risk_analyzer",
            location=session_context.get("location")
                     or session_context.get("name")
                     or "Cameroon Region",
            context=session_context,
        )
        routed = await _route_nat_intent(routed_request)
        if routed is not None:
            _remember_assistant_context(user_id, routed)
            provider_info = get_provider_info(provider_name)
            return EnhancedChatResponse(
                response=_sanitize_agent_text(routed.get("output")),
                provider_used=provider_info.get("name", "unknown"),
                model_used=request.model or provider_info.get("default_model", "unknown"),
                agent_used=False,
                confidence=1.0,
                recommendations=[],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        
        # Generate AI response using selected provider
        from .api import llm_call  # Import here to avoid circular imports
        
        # Prepare context for response generation
        context = request.context or {}
        if request.watershed_id:
            context["watershed_id"] = request.watershed_id
        
        # Build enhanced prompt with context
        if request.watershed_id:
            watershed_context = db.get_watershed_context(str(_db_path), request.watershed_id)
            enhanced_prompt = f"""
System: You are AquaGuard AI, the flood-intelligence assistant for Cameroon's Far North.
Discuss Far North localities and divisions, historical floods, safety guidance, and only
real risk/forecast data supplied below. Never refer to Texas or US watersheds, and never
invent a probability.

Watershed Information: {watershed_context}

User Question: {request.message}

Please provide a helpful and accurate response based on the available data and context.
"""
        else:
            enhanced_prompt = f"""
System: You are AquaGuard AI, the flood-intelligence assistant for Cameroon's Far North.
Answer general flood-education questions and interpret real backend results. Never refer
to Texas or unrelated template regions, and never invent live probabilities.

User Question: {request.message}
"""
        
        # Call the AI provider
        response = await llm_call(
            enhanced_prompt,
            model=request.model,
            use_agent=request.use_agent,
            provider_name=provider_name,
            temperature=request.temperature or 0.7,
            max_tokens=request.max_tokens or 4096
        )
        
        # Get provider info for response metadata
        provider_info = get_provider_info(provider_name)
        
        return EnhancedChatResponse(
            response=response,
            provider_used=provider_info.get("name", "unknown"),
            model_used=request.model or provider_info.get("default_model", "unknown"),
            agent_used=request.use_agent and provider_info.get("supports_agents", False),
            confidence=0.85,  # Placeholder confidence score
            recommendations=[],  # TODO: Add recommendation logic
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
    except Exception as e:
        log.error(f"Failed to process enhanced AI chat: {str(e)}")
        # Never expose provider status pages, model identifiers, or raw JSON
        # to the user. Keep the endpoint usable during an outage/deprecation.
        provider_info = get_provider_info(request.provider if request.provider != "auto" else None)
        return EnhancedChatResponse(
            response=LLM_UNAVAILABLE_MESSAGE,
            provider_used=provider_info.get("name", "unknown"),
            model_used=request.model or provider_info.get("default_model", "unknown"),
            agent_used=False,
            confidence=0.0,
            recommendations=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

@app.post(_api("ai/chat/enhanced/stream"))
async def enhanced_stream_chat_with_ai(user_id: UserID, request: EnhancedChatMessage):
    """Enhanced streaming chat with AI assistant with provider selection"""
    user_id = _require_authenticated_identity(user_id)
    request_started = time.perf_counter()
    log.info("assistant.stage.request_received message_chars=%d", len(request.message or ""))
    try:
        import asyncio
        import json
        
        # Determine which provider to use
        provider_name = request.provider if request.provider != "auto" else None

        # Route the UI's streaming path through the same safe router used by
        # /ai/chat and /nat/chat.  This prevents the enhanced legacy prompt
        # from receiving an unvalidated locality or a rigid risk template.
        session_context = _assistant_context_for(user_id, request.context)
        routed_request = NATChatMessage(
            message=request.message,
            agent_type="all" if request.use_agent else "risk_analyzer",
            location=session_context.get("location")
                     or session_context.get("name")
                     or "Cameroon Region",
            context=session_context,
        )
        routed = await _route_nat_intent(routed_request)
        if routed is not None:
            _remember_assistant_context(user_id, routed)
            provider_info = get_provider_info(provider_name)

            async def routed_stream():
                yield f"data: {json.dumps({'provider': provider_info.get('name', 'unknown'), 'model': request.model or provider_info.get('default_model', 'unknown')}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'chunk': _sanitize_agent_text(routed.get('output')), 'done': False}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'done': True, 'provider_used': provider_info.get('name', 'unknown')}, ensure_ascii=False)}\n\n"

            return StreamingResponse(
                routed_stream(),
                media_type="text/event-stream; charset=utf-8",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )
        
        async def generate_enhanced_stream():
            try:
                import threading
                import concurrent.futures
                from collections import deque
                
                # Use thread-safe deque and event for communication
                chunks_queue = deque()
                done_event = threading.Event()
                error_container = {'error': None}
                provider_info = get_provider_info(provider_name)
                
                def sync_callback(chunk: str):
                    chunks_queue.append(chunk)
                
                def run_llm_sync():
                    try:
                        # Build enhanced prompt with context
                        if request.watershed_id:
                            watershed_context = db.get_watershed_context(str(_db_path), request.watershed_id)
                            enhanced_prompt = f"""
System: You are AquaGuard AI, the flood-intelligence assistant for Cameroon's Far North.
Discuss Far North localities and divisions, live backend risk/forecast results, historical
flood events, and safety guidance. Never refer to Texas, US watersheds, or unrelated
template data. Never invent a probability that is not present in the supplied context.

Watershed Information: {watershed_context}

User Question: {request.message}

Please provide a helpful and accurate response based on the available data and context.
"""
                        else:
                            enhanced_prompt = f"""
System: You are AquaGuard AI, the flood-intelligence assistant for Cameroon's Far North.
You can explain flood mechanisms, historical events, safety guidance, and interpret the
real risk/forecast data returned by this application. Never refer to Texas, US watersheds,
or unrelated template data. Never invent a live probability.

User Question: {request.message}
"""
                        
                        # Create a new event loop for this thread
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        llm_started = time.perf_counter()
                        final_response = loop.run_until_complete(llm_call_stream(
                            enhanced_prompt, 
                            sync_callback, 
                            request.model, 
                            request.use_agent,
                            provider_name,
                            temperature=request.temperature or 0.7,
                            max_tokens=request.max_tokens or 4096
                        ))
                        log.info("assistant.stage.llm_generation_ms=%.1f", (time.perf_counter() - llm_started) * 1000)
                        chunks_queue.append("__DONE__")
                        done_event.set()
                        return final_response
                    except Exception as e:
                        log.warning("assistant.stage.llm_failed error=%s", e)
                        fallback = _local_flood_answer(request.message)
                        chunks_queue.append(fallback)
                        chunks_queue.append("__DONE__")
                        done_event.set()
                        return fallback
                
                # Start the LLM in a background thread
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    llm_future = executor.submit(run_llm_sync)
                    
                    # Send provider info first
                    yield f"data: {json.dumps({'provider': provider_info.get('name', 'unknown'), 'model': request.model or provider_info.get('default_model', 'unknown')})}\n\n"
                    
                    # Stream chunks as they arrive
                    while not done_event.is_set() or chunks_queue:
                        if chunks_queue:
                            chunk = chunks_queue.popleft()
                            if chunk == "__DONE__":
                                break
                            elif chunk.startswith("__ERROR__"):
                                error_msg = chunk[9:]  # Remove "__ERROR__:" prefix
                                yield f"data: {json.dumps({'error': error_msg})}\n\n"
                                break
                            else:
                                # Send streaming chunk
                                yield f"data: {json.dumps({'chunk': chunk, 'done': False})}\n\n"
                        else:
                            # Small delay to avoid busy waiting and send keepalive
                            await asyncio.sleep(0.1)
                            if not done_event.is_set():
                                yield f"data: {json.dumps({'keepalive': True})}\n\n"
                    
                    # Wait for LLM completion
                    final_response = llm_future.result()
                    
                    # Run evaluation for all responses (agent and non-agent) if we have a complete response
                    if final_response and not error_container['error']:
                        try:
                            evaluation_result = await evaluator.evaluate_chat_response(
                                question=request.message,
                                response=final_response,
                                model_used=request.model or provider_info.get("default_model", "unknown"),
                                agent_used=request.use_agent,
                                watershed_context=request.context,
                                response_provider=provider_info.get("name", "unknown")  # Use actual provider used
                            )
                            
                            # Send evaluation results
                            evaluation_data = {
                                'evaluation': {
                                    'id': evaluation_result.id,
                                    'overall_score': evaluation_result.metrics.overall,
                                    'confidence': evaluation_result.metrics.confidence,
                                    'safety_score': evaluation_result.metrics.safety,
                                    'helpfulness': evaluation_result.metrics.helpfulness,
                                    'accuracy': evaluation_result.metrics.accuracy,
                                    'reasoning': evaluation_result.judge_reasoning
                                }
                            }
                            yield f"data: {json.dumps(evaluation_data)}\n\n"
                            
                        except Exception as eval_error:
                            log.warning(f"Evaluation failed: {str(eval_error)}")
                            # Don't fail the entire response if evaluation fails
                    
                    yield f"data: {json.dumps({'done': True, 'provider_used': provider_info.get('name', 'unknown')})}\n\n"
                    log.info("assistant.stage.total_ms=%.1f", (time.perf_counter() - request_started) * 1000)
                
            except Exception as e:
                log.error("Enhanced stream generation error: %s", e)
                yield f"data: {json.dumps({'error': 'LLM service temporarily unavailable'})}\n\n"
        
        return StreamingResponse(
            generate_enhanced_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream",
            }
        )
        
    except Exception as e:
        log.error(f"Failed to process enhanced streaming AI chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process enhanced streaming chat message")


# =============================================================================
# Evaluation API Endpoints  
# =============================================================================

@app.post(_api("evaluation/evaluate"))
async def evaluate_response(request: Dict[str, Any]):
    """Evaluate a chat response using NVIDIA-style LLM-as-Judge"""
    try:
        question = request.get("question", "")
        response = request.get("response", "")
        model_used = request.get("model", "unknown")
        agent_used = request.get("agent_used", False)
        watershed_context = request.get("watershed_context")
        
        if not question or not response:
            raise HTTPException(status_code=400, detail="Question and response are required")
        
        # Run evaluation with cross-provider judging
        response_provider = request.get("response_provider")  # Allow manual specification
        evaluation_result = await evaluator.evaluate_chat_response(
            question=question,
            response=response,
            model_used=model_used,
            agent_used=agent_used,
            watershed_context=watershed_context,
            response_provider=response_provider
        )
        
        return {
            "evaluation_id": evaluation_result.id,
            "metrics": evaluation_result.metrics.dict(),
            "reasoning": evaluation_result.judge_reasoning,
            "duration_ms": evaluation_result.evaluation_duration_ms,
            "timestamp": evaluation_result.timestamp.isoformat()
        }
        
    except Exception as e:
        log.error(f"Failed to evaluate response: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to evaluate response")


@app.get(_api("evaluation/stats"))
async def get_evaluation_stats(hours: int = 24):
    """Get evaluation statistics for the last N hours"""
    try:
        stats = evaluator.get_evaluation_stats(hours=hours)
        return stats
        
    except Exception as e:
        log.error(f"Failed to get evaluation stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get evaluation statistics")


@app.get(_api("evaluation/history"))
async def get_evaluation_history(limit: int = 50):
    """Get recent evaluation history"""
    try:
        # Get recent evaluations from memory (limited to last 100)
        recent_evaluations = evaluator.evaluation_history[-limit:]
        
        return {
            "evaluations": [
                {
                    "id": eval_result.id,
                    "timestamp": eval_result.timestamp.isoformat(),
                    "question": eval_result.question[:100] + "..." if len(eval_result.question) > 100 else eval_result.question,
                    "model": eval_result.model_used,
                    "agent_used": eval_result.agent_used,
                    "overall_score": eval_result.metrics.overall,
                    "confidence": eval_result.metrics.confidence,
                    "safety_score": eval_result.metrics.safety
                }
                for eval_result in reversed(recent_evaluations)
            ]
        }
        
    except Exception as e:
        log.error(f"Failed to get evaluation history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get evaluation history")


# =============================================================================
# AI Agents API Endpoints
# =============================================================================

@app.get(_api("agents"))
async def get_agents_status():
    """Get status of all AI agents"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        agent_status = await _agent_manager.get_agent_status()
        return {
            "agents": agent_status,
            "manager_initialized": _agent_manager.is_initialized,
            "last_update": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        log.error(f"Failed to get agents status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get agents status")

@app.get(_api("agents/insights"))
async def get_agents_insights():
    """Get insights from all AI agents"""
    if not _agent_manager:
        return {
            "error": "AI agents are disabled",
            "insights": {},
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    try:
        insights = await _agent_manager.get_all_insights()
        return {
            "insights": insights,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        log.error(f"Failed to get agents insights: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get agents insights: {str(e)}")

@app.get(_api("agents/alerts"))
async def get_agents_alerts():
    """Get alerts from all AI agents"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        alerts = await _agent_manager.get_all_alerts()
        return {
            "alerts": alerts,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        log.error(f"Failed to get agents alerts: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get agents alerts")

@app.get(_api("agents/summary"))
async def get_agents_summary():
    """Get summary of all agent activities for dashboard"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        summary = await _agent_manager.get_dashboard_summary()
        return summary
    except Exception as e:
        log.error(f"Failed to get agents summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get agents summary")

@app.get(_api("agents/{agent_name}"))
async def get_agent_details(agent_name: str):
    """Get detailed information about a specific agent"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        details = await _agent_manager.get_agent_details(agent_name)
        return details
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"Failed to get agent details for {agent_name}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get agent details")

@app.post(_api("agents/{agent_name}/check"))
async def force_agent_check(agent_name: str, user_id: UserID):
    """Force an immediate check for a specific agent"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        result = await _agent_manager.force_agent_check(agent_name)
        return {
            "status": "success",
            "message": f"Force check completed for agent: {agent_name}",
            "result": result
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"Failed to force check for agent {agent_name}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to force agent check")

@app.post(_api("agents/start"))
async def start_all_agents(user_id: UserID):
    """Start all AI agents"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        await _agent_manager.start_all_agents()
        return {
            "status": "success",
            "message": "All agents started successfully"
        }
    except Exception as e:
        log.error(f"Failed to start agents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to start agents")

@app.post(_api("agents/stop"))
async def stop_all_agents(user_id: UserID):
    """Stop all AI agents"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        await _agent_manager.stop_all_agents()
        return {
            "status": "success",
            "message": "All agents stopped successfully"
        }
    except Exception as e:
        log.error(f"Failed to stop agents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to stop agents")

@app.post(_api("agents/collect-data"))
async def collect_external_data(user_id: UserID):
    """Trigger data collection from external APIs"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        data = await _agent_manager.collect_external_data()
        return {
            "status": "success",
            "message": "External data collection completed",
            "data": data
        }
    except Exception as e:
        log.error(f"Failed to collect external data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to collect external data")

@app.post(_api("agents/forecast"))
async def generate_ai_forecast(hours_ahead: int = 24):
    """Generate AI-powered flood forecast"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        forecast = await _agent_manager.generate_forecast(hours_ahead)
        return {
            "status": "success",
            "forecast": forecast
        }
    except Exception as e:
        log.error(f"Failed to generate forecast: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate forecast")

class EmergencyAlertRequest(BaseModel):
    """Emergency alert request model"""
    title: str
    message: str
    severity: str = "warning"  # info, warning, critical
    affected_areas: List[str] = []
    recommendations: List[str] = []
    channels: List[str] = ["EAS", "Cell", "Social"]

@app.post(_api("agents/emergency-alert"))
async def send_emergency_alert(user_id: UserID, request: EmergencyAlertRequest):
    """Send emergency alert through AI agents"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        alert_data = {
            "title": request.title,
            "message": request.message,
            "severity": request.severity,
            "affected_areas": request.affected_areas,
            "recommendations": request.recommendations,
            "channels": request.channels
        }
        
        success = await _agent_manager.send_emergency_alert(alert_data)
        
        if success:
            return {
                "status": "success",
                "message": "Emergency alert sent successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to send emergency alert")
    
    except Exception as e:
        log.error(f"Failed to send emergency alert: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to send emergency alert")

@app.get(_api("agents/available"))
async def get_available_agents():
    """Get list of available agents"""
    if not _agent_manager:
        raise HTTPException(status_code=503, detail="AI agents are disabled")
    
    try:
        agents = _agent_manager.get_available_agents()
        return {
            "agents": agents,
            "total_count": len(agents)
        }
    except Exception as e:
        log.error(f"Failed to get available agents: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get available agents")

# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Redis connection
        _redis.ping()
        
        # Check agents status if enabled
        agents_status = "disabled"
        if _agent_manager:
            try:
                agent_summary = await _agent_manager.get_dashboard_summary()
                agents_status = f"{agent_summary['running_agents']}/{agent_summary['total_agents']} running"
            except:
                agents_status = "error"
        
        return {
            "status": "healthy", 
            "redis": "connected",
            "agents": agents_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy", 
            "redis": f"error: {str(e)}",
            "agents": "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@app.get("/")
async def serve_index():
    """Serve the main index.html file"""
    # The bundled frontend is replaced during local development.  Prevent a
    # browser from keeping an old index/bundle mapping after a rebuild; the
    # asset filenames are content-hashed, so this is safe in production too.
    return FileResponse(
        server_dir / "index.html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )

@app.get("/{path:path}")
async def serve_static(path: str):
    """Serve static files, but exclude API routes"""
    # Don't serve static files for API routes
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    
    f = server_dir / path
    target = f if f.is_file() else server_dir / "index.html"
    return FileResponse(
        target,
        headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
    )

# =============================================================================
# Telemetry Status Endpoint
# =============================================================================

@app.get(_api("telemetry/status"))
async def get_telemetry_status():
    """
    Real-time health check for the three external data streams used by
    the Citizen Dashboard:
      - Open-Meteo High-Resolution Precipitation (free, keyless)
      - GloFAS River Discharge Monitoring (Open-Meteo Flood API, keyless)
      - NASA OPERA / GIBS tile server (public tile endpoint)

    Returns per-source: online (bool), latency_ms (int | null), label (str).
    """
    import time as _time

    async def ping_openmeteo() -> dict:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": "10.59", "longitude": "14.31",
            "daily": "precipitation_sum", "forecast_days": "1",
            "timezone": "Africa/Lagos",
        }
        t0 = _time.monotonic()
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url, params=params,
                                 headers={"User-Agent": "AquaGuard-Cameroon/1.0"}) as r:
                    ok = r.status == 200
                    if ok:
                        payload = await r.json()
                        ok = "daily" in payload
            latency = int((_time.monotonic() - t0) * 1000)
            return {"online": ok, "latency_ms": latency,
                    "label": "Open-Meteo High-Resolution Precipitation"}
        except Exception as exc:
            log.debug(f"OpenMeteo ping failed: {exc}")
            return {"online": False, "latency_ms": None,
                    "label": "Open-Meteo High-Resolution Precipitation"}

    async def ping_glofas() -> dict:
        url = "https://flood-api.open-meteo.com/v1/flood"
        params = {
            "latitude": "12.076", "longitude": "15.031",
            "daily": "river_discharge", "forecast_days": "1",
        }
        t0 = _time.monotonic()
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url, params=params,
                                 headers={"User-Agent": "AquaGuard-Cameroon/1.0"}) as r:
                    ok = r.status == 200
                    if ok:
                        payload = await r.json()
                        ok = "daily" in payload
            latency = int((_time.monotonic() - t0) * 1000)
            return {"online": ok, "latency_ms": latency,
                    "label": "GloFAS River Discharge Monitoring"}
        except Exception as exc:
            log.debug(f"GloFAS Flood API ping failed: {exc}")
            return {"online": False, "latency_ms": None,
                    "label": "GloFAS River Discharge Monitoring"}

    async def ping_nasa_opera() -> dict:
        # NASA GIBS WMTS endpoint for OPERA DSWx-S1 (public tile server)
        url = (
            "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/"
            "OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1/default/"
            "2024-01-01/250m/6/20/38.png"
        )
        t0 = _time.monotonic()
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url,
                                 headers={"User-Agent": "AquaGuard-Cameroon/1.0"}) as r:
                    # 200 → tile exists; 404 → server is up but no tile (still "online")
                    ok = r.status in (200, 404)
            latency = int((_time.monotonic() - t0) * 1000)
            return {"online": ok, "latency_ms": latency,
                    "label": "NASA OPERA Sentinel-1 Dynamic Surface Water"}
        except Exception as exc:
            log.debug(f"NASA OPERA ping failed: {exc}")
            return {"online": False, "latency_ms": None,
                    "label": "NASA OPERA Sentinel-1 Dynamic Surface Water"}

    om, gf, nasa = await asyncio.gather(
        ping_openmeteo(), ping_glofas(), ping_nasa_opera()
    )

    sources = [om, gf, nasa]
    online_count = sum(1 for s in sources if s["online"])

    return {
        "sources": sources,
        "online_count": online_count,
        "total": len(sources),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return {"error": "Not found", "detail": exc.detail}


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    return {"error": "Internal server error", "detail": str(exc)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
