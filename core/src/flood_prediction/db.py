"""
Database access layer for Cameroon Flood Intelligence.

Connects to PostgreSQL + PostGIS using SQLAlchemy.
Provides:
  - Engine / session factory
  - Table creation (create_all)
  - Point-in-polygon geographic resolution (resolve_location_to_entities)
  - Basin CRUD helpers used by the ingestion pipeline and API handlers

Unit convention: all flow fields are metric (m³/s, km²).
No imperial-unit column names (_cfs, _sqmi, _ft) exist anywhere in this module.
"""

import json
import logging
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional

import csv
import hashlib
import base64
import secrets
from pathlib import Path

from geoalchemy2.functions import ST_Contains, ST_SetSRID, ST_Point
from sqlalchemy import create_engine, select, func, text, or_
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Alert,
    Arrondissement,
    Base,
    BasinFlow,
    BasinRainfallObservation,
    Cache,
    CommunityReport,
    PredictionFeedback,
    Department,
    Region,
    RiverBasin,
    RiskTrend,
    SystemMetric,
    UserPrediction,
    UserAccount,
    VerifiedFloodEvent,
    UserSetting,
)
from .settings import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _build_engine():
    url = settings.database_url
    if not url:
        raise RuntimeError(
            "APP_DATABASE_URL is not set. "
            "Add it to .env: postgresql://postgres:1234@localhost/flood_prediction"
        )
    # SQLite is used for the local/demo profile; QueuePool options are only
    # valid for the PostgreSQL deployment.
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, echo=False)
    return create_engine(url, pool_size=10, max_overflow=20, pool_pre_ping=True, echo=False)


_engine = None
_SessionFactory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session, auto-rolling back on error."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def init_db():
    """Create all tables and ensure PostGIS extension exists."""
    engine = get_engine()
    if engine.dialect.name != "sqlite":
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
    Base.metadata.create_all(engine)
    if engine.dialect.name != "sqlite":
        _apply_phase3_migration(engine)
    else:
        _apply_sqlite_migration(engine)
    log.info("Database initialised (all tables; PostGIS=%s)", engine.dialect.name != "sqlite")


def _apply_phase3_migration(engine) -> None:
    """Add Phase 3 columns when upgrading an existing PostGIS database."""
    statements = (
        "ALTER TABLE river_basins ADD COLUMN IF NOT EXISTS local_rainfall_threshold_mm DOUBLE PRECISION NOT NULL DEFAULT 20.0",
        "ALTER TABLE river_basins ADD COLUMN IF NOT EXISTS two_day_rainfall_threshold_mm DOUBLE PRECISION NOT NULL DEFAULT 30.0",
        "ALTER TABLE river_basins ADD COLUMN IF NOT EXISTS risk_source VARCHAR(40) NOT NULL DEFAULT 'none'",
        "ALTER TABLE river_basins ADD COLUMN IF NOT EXISTS trigger_reasons TEXT",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS user_id VARCHAR(100)",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS locality VARCHAR(200)",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS division VARCHAR(100)",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS observation_at TIMESTAMPTZ",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS water_depth_category VARCHAR(20)",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS evidence_name VARCHAR(255)",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS evidence_url VARCHAR(500)",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS evidence_media_type VARCHAR(100)",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'Submitted'",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS verification_notes TEXT",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS linked_event_id INTEGER",
        "ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS linked_event_reference VARCHAR(200)",
        "ALTER TABLE user_accounts ADD COLUMN IF NOT EXISTS username VARCHAR(100)",
        "ALTER TABLE user_accounts ADD COLUMN IF NOT EXISTS email VARCHAR(254)",
        "ALTER TABLE user_accounts ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
    )
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def _apply_sqlite_migration(engine) -> None:
    """Keep the local SQLite profile compatible with the PostgreSQL schema."""
    columns = {
        row[1] for row in engine.connect().execute(text("PRAGMA table_info(community_reports)"))
    }
    additions = {
        "user_id": "VARCHAR(100)", "locality": "VARCHAR(200)",
        "division": "VARCHAR(100)", "observation_at": "DATETIME",
        "water_depth_category": "VARCHAR(20)", "evidence_name": "VARCHAR(255)",
        "evidence_url": "VARCHAR(500)", "evidence_media_type": "VARCHAR(100)",
        "status": "VARCHAR(30) NOT NULL DEFAULT 'Submitted'",
        "verification_notes": "TEXT", "verified_at": "DATETIME", "linked_event_id": "INTEGER", "linked_event_reference": "VARCHAR(200)",
    }
    with engine.begin() as conn:
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(text(f"ALTER TABLE community_reports ADD COLUMN {name} {definition}"))
    account_columns = {row[1] for row in engine.connect().execute(text("PRAGMA table_info(user_accounts)"))}
    account_additions = {"username": "VARCHAR(100)", "email": "VARCHAR(254)", "password_hash": "VARCHAR(255)"}
    with engine.begin() as conn:
        for name, definition in account_additions.items():
            if name not in account_columns:
                conn.execute(text(f"ALTER TABLE user_accounts ADD COLUMN {name} {definition}"))


# ---------------------------------------------------------------------------
# Geographic Resolution
# ---------------------------------------------------------------------------

def resolve_location_to_entities(lat: float, lon: float) -> Dict[str, Any]:
    """
    Resolve a (lat, lon) coordinate to its Cameroon administrative context
    and enclosing river basin using PostGIS ST_Contains.

    Returns a dict with keys: region, department, arrondissement, basin.
    Each value is a dict with id/name/pcode, or None if not found.
    """
    point = func.ST_SetSRID(func.ST_Point(lon, lat), 4326)

    result: Dict[str, Any] = {
        "region": None,
        "department": None,
        "arrondissement": None,
        "basin": None,
    }

    with get_session() as session:
        # Region
        region = session.scalars(
            select(Region).where(func.ST_Contains(Region.geom, point))
        ).first()
        if region:
            result["region"] = {
                "id": region.id,
                "name": region.name,
                "name_fr": region.name_fr,
                "pcode": region.pcode,
            }

        # Department
        dept = session.scalars(
            select(Department).where(func.ST_Contains(Department.geom, point))
        ).first()
        if dept:
            result["department"] = {
                "id": dept.id,
                "name": dept.name,
                "name_fr": dept.name_fr,
                "pcode": dept.pcode,
            }

        # Arrondissement
        arr = session.scalars(
            select(Arrondissement).where(func.ST_Contains(Arrondissement.geom, point))
        ).first()
        if arr:
            result["arrondissement"] = {
                "id": arr.id,
                "name": arr.name,
                "name_fr": arr.name_fr,
                "pcode": arr.pcode,
            }

        # River basin
        basin = session.scalars(
            select(RiverBasin).where(func.ST_Contains(RiverBasin.geom, point))
        ).first()
        if basin:
            result["basin"] = {
                "id": basin.id,
                "name": basin.name,
                "hybas_id": basin.hybas_id,
            }

    return result


# ---------------------------------------------------------------------------
# Basin helpers
# ---------------------------------------------------------------------------

def get_all_basins(region_pcode: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all river basins serialised as dicts (metric units)."""
    with get_session() as session:
        stmt = select(
            RiverBasin,
            func.ST_Y(func.ST_Centroid(RiverBasin.geom)),
            func.ST_X(func.ST_Centroid(RiverBasin.geom))
        )
        rows = session.execute(stmt).all()
        return [_basin_to_dict(row[0], lat=row[1], lon=row[2]) for row in rows]


def get_basins_with_centroids() -> List[Dict[str, Any]]:
    """Return all river basins with their calculated centroid coordinates."""
    with get_session() as session:
        stmt = select(
            RiverBasin.id,
            RiverBasin.name,
            RiverBasin.hybas_id,
            func.ST_Y(func.ST_Centroid(RiverBasin.geom)).label("lat"),
            func.ST_X(func.ST_Centroid(RiverBasin.geom)).label("lon"),
            RiverBasin.flood_stage_cms,
            RiverBasin.basin_size_sqkm
        )
        rows = session.execute(stmt).all()
        return [
            {
                "id": r[0],
                "name": r[1],
                "hybas_id": r[2],
                "lat": r[3],
                "lon": r[4],
                "flood_stage_cms": r[5],
                "basin_size_sqkm": r[6]
            }
            for r in rows
        ]


def record_basin_rainfall(session: Session, basin_id: int, observed_on: date,
                          precipitation_mm: float, source: str = "openmeteo") -> None:
    """Upsert one daily observation used by calibration and propagation."""
    observation = session.scalars(select(BasinRainfallObservation).where(
        BasinRainfallObservation.basin_id == basin_id,
        BasinRainfallObservation.observed_on == observed_on,
    )).first()
    if observation:
        observation.precipitation_mm = max(0.0, precipitation_mm)
        observation.source = source
    else:
        session.add(BasinRainfallObservation(
            basin_id=basin_id, observed_on=observed_on,
            precipitation_mm=max(0.0, precipitation_mm), source=source,
        ))


def get_rainfall_two_day_total(session: Session, basin_id: int, observed_on: date) -> float:
    values = session.scalars(select(BasinRainfallObservation.precipitation_mm).where(
        BasinRainfallObservation.basin_id == basin_id,
        BasinRainfallObservation.observed_on.in_(
            (observed_on, observed_on - timedelta(days=1))
        ),
    )).all()
    return float(sum(values or []))


def get_upstream_propagation_signals(session: Session, basin_id: int,
                                     risk_date: date) -> List[str]:
    """Find local-rain triggers whose configured arrival window includes today."""
    signals: List[str] = []
    flows = session.scalars(select(BasinFlow).where(
        BasinFlow.downstream_basin_id == basin_id
    )).all()
    for flow in flows:
        upstream = session.get(RiverBasin, flow.upstream_basin_id)
        if not upstream:
            continue
        start = risk_date - timedelta(days=flow.max_propagation_delay_days)
        end = risk_date - timedelta(days=flow.min_propagation_delay_days)
        dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        observations = session.scalars(select(BasinRainfallObservation).where(
            BasinRainfallObservation.basin_id == upstream.id,
            BasinRainfallObservation.observed_on.in_(dates),
        )).all()
        for observation in observations:
            two_day = get_rainfall_two_day_total(session, upstream.id, observation.observed_on)
            if (observation.precipitation_mm >= upstream.local_rainfall_threshold_mm
                    or two_day >= upstream.two_day_rainfall_threshold_mm):
                signals.append(
                    f"upstream:{upstream.name}:rainfall_on:{observation.observed_on.isoformat()}"
                )
                break
    return signals


def get_basin_by_id(basin_id: int) -> Optional[Dict[str, Any]]:
    with get_session() as session:
        row = session.execute(
            select(
                RiverBasin,
                func.ST_Y(func.ST_Centroid(RiverBasin.geom)),
                func.ST_X(func.ST_Centroid(RiverBasin.geom))
            ).where(RiverBasin.id == basin_id)
        ).first()
        return _basin_to_dict(row[0], lat=row[1], lon=row[2]) if row else None


def update_basin_hydro(
    basin_id: int,
    *,
    streamflow_cms: float,
    risk_level: str,
    risk_score: float,
    trend: str,
    trend_rate_cms_per_hour: float,
    discharge_cms: Optional[float],
    discharge_status: str,
    discharge_source: str,
    data_completeness: str,
    missing_inputs: List[str],
    data_source: str = "openmeteo",
    data_quality: str = "provisional",
) -> bool:
    """Update hydrological state for a single basin. Returns True on success."""
    with get_session() as session:
        basin = session.get(RiverBasin, basin_id)
        if not basin:
            log.warning(f"Basin id={basin_id} not found for update")
            return False
        basin.current_streamflow_cms   = streamflow_cms
        basin.current_risk_level       = risk_level
        basin.risk_score               = risk_score
        basin.trend                    = trend
        basin.trend_rate_cms_per_hour  = trend_rate_cms_per_hour
        basin.discharge_cms            = discharge_cms
        basin.discharge_status         = discharge_status
        basin.discharge_source         = discharge_source
        basin.data_completeness        = data_completeness
        basin.missing_inputs           = json.dumps(missing_inputs)
        basin.data_source              = data_source
        basin.data_quality             = data_quality
        basin.last_api_update          = datetime.now(timezone.utc)
        basin.last_updated             = datetime.now(timezone.utc)
    return True


def insert_risk_trend(basin_id: int, risk_score: float, streamflow_cms: float):
    with get_session() as session:
        session.add(RiskTrend(
            basin_id=basin_id,
            risk_score=risk_score,
            streamflow_cms=streamflow_cms,
        ))


def _basin_to_dict(b: RiverBasin, lat: Optional[float] = None, lon: Optional[float] = None) -> Dict[str, Any]:
    """Serialise a RiverBasin ORM object to a plain dict (metric units only)."""
    missing = []
    if b.missing_inputs:
        try:
            missing = json.loads(b.missing_inputs)
        except Exception:
            pass
    trigger_reasons = []
    if b.trigger_reasons:
        try:
            trigger_reasons = json.loads(b.trigger_reasons)
        except Exception:
            pass
    return {
        "id":                       b.id,
        "name":                     b.name,
        "hybas_id":                 b.hybas_id,
        "basin_size_sqkm":          b.basin_size_sqkm,
        "current_streamflow_cms":   b.current_streamflow_cms,
        "current_risk_level":       b.current_risk_level,
        "risk_score":               b.risk_score,
        "local_rainfall_threshold_mm": b.local_rainfall_threshold_mm,
        "two_day_rainfall_threshold_mm": b.two_day_rainfall_threshold_mm,
        "risk_source":              b.risk_source,
        "trigger_reasons":          trigger_reasons,
        "flood_stage_cms":          b.flood_stage_cms,
        "trend":                    b.trend,
        "trend_rate_cms_per_hour":  b.trend_rate_cms_per_hour,
        "discharge_cms":            b.discharge_cms,
        "discharge_status":         b.discharge_status,
        "discharge_source":         b.discharge_source,
        "data_completeness":        b.data_completeness,
        "missing_inputs":           missing,
        "data_source":              b.data_source,
        "data_quality":             b.data_quality,
        "location_lat":             lat,
        "location_lng":             lon,
        "last_api_update":          b.last_api_update.isoformat() if b.last_api_update else None,
        "last_updated":             b.last_updated.isoformat() if b.last_updated else None,
    }


# ---------------------------------------------------------------------------
# Dashboard summary (replaces old SQLite get_dashboard_summary)
# ---------------------------------------------------------------------------

def get_dashboard_summary(db_path: Optional[str] = None) -> Dict[str, Any]:
    with get_session() as session:
        total   = session.scalar(select(func.count()).select_from(RiverBasin))
        alerts  = session.scalar(
            select(func.count()).select_from(Alert).where(Alert.is_active == True)
        )
        high    = session.scalar(
            select(func.count()).select_from(RiverBasin)
            .where(RiverBasin.current_risk_level == "High")
        )
        moderate = session.scalar(
            select(func.count()).select_from(RiverBasin)
            .where(RiverBasin.current_risk_level == "Moderate")
        )
        low     = session.scalar(
            select(func.count()).select_from(RiverBasin)
            .where(RiverBasin.current_risk_level == "Low")
        )
        any_partial = session.scalar(
            select(func.count()).select_from(RiverBasin)
            .where(RiverBasin.discharge_status == "unavailable")
        ) > 0

    return {
        "total_basins":           total,
        "active_alerts":          alerts,
        "high_risk_basins":       high,
        "moderate_risk_basins":   moderate,
        "low_risk_basins":        low,
        "discharge_unavailable":  any_partial,
        "last_updated":           datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Community reports
# ---------------------------------------------------------------------------

def insert_community_report(
    details: str,
    lat: float,
    lon: float,
    reporter_name: Optional[str] = None,
    contact_info: Optional[str] = None,
    risk_level: Optional[str] = None,
    user_id: Optional[str] = None,
    locality: Optional[str] = None,
    division: Optional[str] = None,
    observation_at: Optional[datetime] = None,
    water_depth_category: Optional[str] = None,
    evidence_name: Optional[str] = None,
    evidence_url: Optional[str] = None,
    evidence_media_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store a community flood report and resolve its geographic context
    using the PostGIS point-in-polygon lookup.
    """
    geo = resolve_location_to_entities(lat, lon)

    report = CommunityReport(
        reporter_name=reporter_name,
        contact_info=contact_info,
        user_id=user_id,
        details=details,
        location_lat=lat,
        location_lng=lon,
        risk_level=risk_level,
        locality=locality,
        division=division,
        observation_at=observation_at,
        water_depth_category=water_depth_category,
        evidence_name=evidence_name,
        evidence_url=evidence_url,
        evidence_media_type=evidence_media_type,
        status="Submitted",
        region_id=geo["region"]["id"] if geo["region"] else None,
        department_id=geo["department"]["id"] if geo["department"] else None,
        arrondissement_id=geo["arrondissement"]["id"] if geo["arrondissement"] else None,
        basin_id=geo["basin"]["id"] if geo["basin"] else None,
    )

    with get_session() as session:
        session.add(report)
        session.flush()
        report_id = report.id

    return {
        "id": report_id,
        "geo_context": geo,
        "reported_at": datetime.now(timezone.utc).isoformat(),
    }


def attach_community_report_evidence(
    report_id: int,
    evidence_url: str,
    evidence_media_type: str,
    evidence_name: str,
    requester_id: str,
) -> Optional[Dict[str, Any]]:
    """Attach an uploaded image/video to its report after ownership checks."""
    with get_session() as session:
        report = session.get(CommunityReport, int(report_id))
        if report is None:
            return None
        requester = str(requester_id).strip()
        if requester not in {"admin", "administrator", "admin@aquaguard.local"} and report.user_id != requester:
            raise PermissionError("You can only attach evidence to your own report")
        report.evidence_url = evidence_url
        report.evidence_media_type = evidence_media_type
        report.evidence_name = evidence_name
        session.flush()
        return report.to_dict()


def get_recent_community_reports(limit: int = 50) -> List[Dict[str, Any]]:
    with get_session() as session:
        reports = session.scalars(
            select(CommunityReport)
            .order_by(CommunityReport.reported_at.desc())
            .limit(limit)
        ).all()
        return [r.to_dict() for r in reports]


def get_user_community_reports(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve flood reports strictly submitted by the authenticated citizen."""
    clean_id = str(user_id).strip()
    with get_session() as session:
        reports = session.scalars(
            select(CommunityReport)
            .where(
                or_(
                    CommunityReport.user_id == clean_id,
                    CommunityReport.contact_info == clean_id,
                )
            )
            .order_by(CommunityReport.reported_at.desc())
            .limit(limit)
        ).all()
        return [r.to_dict() for r in reports]


def insert_prediction_feedback(user_id: str, prediction_id: int, accuracy: str, comments: Optional[str] = None) -> Dict[str, Any]:
    with get_session() as session:
        prediction = session.get(UserPrediction, int(prediction_id))
        if prediction is None or prediction.user_id != str(user_id):
            raise ValueError("Prediction not found for this user")
        row = PredictionFeedback(user_id=str(user_id), prediction_id=int(prediction_id), accuracy=accuracy, comments=comments)
        session.add(row)
        session.flush()
        return row.to_dict()


def get_user_prediction_feedback(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    with get_session() as session:
        rows = session.scalars(select(PredictionFeedback).where(PredictionFeedback.user_id == str(user_id)).order_by(PredictionFeedback.created_at.desc()).limit(limit)).all()
        return [r.to_dict() for r in rows]


def get_admin_feedback(limit: int = 200) -> List[Dict[str, Any]]:
    with get_session() as session:
        rows = session.scalars(select(PredictionFeedback).order_by(PredictionFeedback.created_at.desc()).limit(limit)).all()
        return [r.to_dict() for r in rows]


def get_admin_community_reports(limit: int = 200) -> List[Dict[str, Any]]:
    with get_session() as session:
        rows = session.scalars(select(CommunityReport).order_by(CommunityReport.reported_at.desc()).limit(limit)).all()
        return [r.to_dict() for r in rows]


def delete_community_report(report_id: int) -> Optional[Dict[str, Any]]:
    """Permanently delete a report, but only after it was explicitly rejected.

    Keeping this guard in the database layer as well as the HTTP handler prevents
    an accidental delete from any future caller or background job.
    """
    with get_session() as session:
        report = session.get(CommunityReport, int(report_id))
        if report is None:
            return None
        if (report.status or "").strip().lower() != "rejected":
            raise ValueError("Only rejected reports can be permanently deleted")
        deleted_id = int(report.id)
        session.delete(report)
        session.flush()
        return {"id": deleted_id}


REGISTERED_DATASETS: List[Dict[str, Any]] = [
    {
        "id": "hydrobasins-cameroon",
        "name": "HydroBASINS Level-4 Cameroon River Basins",
        "category": "Hydrology",
        "description": "Delineated watershed sub-basins with hydrological attributes, flow directions, and drainage area (km²).",
        "coverage": "National (Cameroon - 32 basins)",
        "source": "HydroSHEDS / USGS / WWF",
        "format": "PostGIS / GeoJSON",
        "status": "Active",
        "records": 32,
    },
    {
        "id": "cameroon-admin-boundaries",
        "name": "Cameroon Administrative Boundaries (Admin 1-3)",
        "category": "Geospatial",
        "description": "Standardized geographic hierarchy of 10 regions, 58 departments, and 360 arrondissements.",
        "coverage": "National (Cameroon)",
        "source": "OCHA / GADM / INC Cameroon",
        "format": "PostGIS / Shapefiles",
        "status": "Active",
        "records": 428,
    },
    {
        "id": "farnorth-flood-catalogue",
        "name": "Far North Historical Flood Events Catalogue",
        "category": "Historical Events",
        "description": "Verified historical flood disaster events across Far North divisions used for benchmark validation.",
        "coverage": "Far North Region (Logone-et-Chari, Mayo-Danay, Diamaré)",
        "source": "UN OCHA / ReliefWeb / Civil Protection",
        "format": "Catalogue JSON / DB",
        "status": "Active",
        "records": 15,
    },
    {
        "id": "openmeteo-weather-api",
        "name": "Open-Meteo High-Resolution Meteorological Reanalysis",
        "category": "Meteorology",
        "description": "Near-real-time precipitation, 1-day/3-day rainfall accumulation, and volumetric soil moisture index.",
        "coverage": "Far North & Cameroon Grid",
        "source": "Open-Meteo / ECMWF IFS",
        "format": "Live API Feed",
        "status": "Active",
        "records": "Dynamic",
    },
    {
        "id": "copernicus-glofas-discharge",
        "name": "Copernicus GloFAS River Discharge Forecasts",
        "category": "Hydrological Forecast",
        "description": "Global Flood Awareness System gridded river discharge forecasts and multi-day lead times.",
        "coverage": "Lake Chad / Logone-Chari Basin",
        "source": "Copernicus Emergency Management Service (CEMS)",
        "format": "API / NetCDF",
        "status": "Active",
        "records": "Dynamic",
    },
    {
        "id": "farnorth-gazetteer",
        "name": "Far North Locality Flood Gazetteer & Exposure Index",
        "category": "Risk Intelligence",
        "description": "Curated dictionary of 34 Far North localities with geographic coordinates, population exposure, and river proximity.",
        "coverage": "Far North Region (34 Localities)",
        "source": "AquaGuard Knowledge Base / Humanitarian Data",
        "format": "Database / Python Engine",
        "status": "Active",
        "records": 34,
    },
]


def get_admin_datasets() -> List[Dict[str, Any]]:
    """Return catalogue of registered operational datasets."""
    return list(REGISTERED_DATASETS)


def update_community_report_status(report_id: int, status: str) -> Optional[Dict[str, Any]]:
    """Update review/action status of a community report."""
    valid_statuses = {"Submitted", "Pending", "Under Review", "Verified", "Rejected", "Resolved"}
    clean_status = status.strip()
    matched_status = None
    for s in valid_statuses:
        if s.lower() == clean_status.lower():
            matched_status = s
            break
    if not matched_status:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid_statuses))}")
    if matched_status in {"Verified", "Linked to existing event"}:
        raise ValueError("Use the explicit verification action to verify and link a report")

    with get_session() as session:
        report = session.get(CommunityReport, int(report_id))
        if not report:
            return None
        report.status = matched_status
        session.flush()
        return report.to_dict()


def verify_community_report(report_id: int, verified: bool, notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Explicitly verify/reject a report and, on verification, link or create one event."""
    with get_session() as session:
        report = session.get(CommunityReport, int(report_id))
        if not report:
            return None
        report.verification_notes = notes
        report.verified_at = datetime.now(timezone.utc) if verified else None
        if not verified:
            report.status = "Rejected"
            return report.to_dict()
        report.status = "Verified"
        # A same-locality/date report is evidence for an existing event, not a duplicate.
        event_date = report.observation_at.date() if report.observation_at else None
        # Check the curated catalogue before creating a new community event.
        # This preserves one event identity while retaining the report as evidence.
        catalogue = Path(__file__).resolve().parent.parent.parent.parent / "data_quality" / "farnorth_consolidation" / "canonical_flood_events_farnorth.csv"
        if event_date and report.locality and catalogue.exists():
            with catalogue.open(encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    if row.get("locality_name", "").strip().casefold() == report.locality.strip().casefold() and str(row.get("event_start_date", ""))[:10] == event_date.isoformat():
                        report.linked_event_reference = f"catalogue:{row.get('canonical_event_id') or 'existing'}"
                        report.status = "Linked to existing event"
                        return report.to_dict()
        existing = None
        if event_date and report.locality:
            existing = session.scalars(select(VerifiedFloodEvent).where(
                VerifiedFloodEvent.event_date == event_date,
                VerifiedFloodEvent.locality == report.locality,
                VerifiedFloodEvent.region == "Far North")).first()
        if existing is None:
            existing = VerifiedFloodEvent(event_date=event_date, locality=report.locality,
                division=report.division, severity=report.risk_level,
                location_lat=report.location_lat, location_lng=report.location_lng,
                description=report.details, originating_report_id=report.id)
            session.add(existing)
            session.flush()
        report.linked_event_id = existing.id
        report.linked_event_reference = f"community:{existing.id}"
        report.status = "Verified" if existing.originating_report_id == report.id else "Linked to existing event"
        return report.to_dict()


def create_alert_from_report(report_id: int, message: str, severity: str, expires_time: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Create an internal platform alert referencing a verified report/event."""
    with get_session() as session:
        report = session.get(CommunityReport, int(report_id))
        if not report or report.status not in {"Verified", "Linked to existing event"}:
            raise ValueError("Only a verified community report can create an alert")
        alert = Alert(alert_type="Verified community flood event", basin_id=report.basin_id,
                      message=message, severity=severity, expires_time=expires_time,
                      affected_areas=json.dumps([x for x in [report.locality, report.division] if x]),
                      data_source="community")
        session.add(alert)
        session.flush()
        return {"alert_id": alert.id, "message": alert.message, "severity": alert.severity,
                "issued_time": alert.issued_time.isoformat() if alert.issued_time else None,
                "data_source": alert.data_source, "source_report_id": report.id}


def _hash_local_password(password: str) -> str:
    """Create a salted PBKDF2 hash; plaintext credentials never reach the DB."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
    return "pbkdf2_sha256$240000$%s$%s" % (base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode())


def _verify_local_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds_text, salt_text, digest_text = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds_text))
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def authenticate_local_user(identifier: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticate an account whose credentials are managed locally by an admin."""
    clean = str(identifier).strip()
    with get_session() as session:
        account = session.scalar(select(UserAccount).where(or_(
            UserAccount.user_id == clean,
            UserAccount.username == clean,
            UserAccount.email == clean,
        )))
        if account is None or not account.is_active or not account.password_hash or not _verify_local_password(password, account.password_hash):
            return None
        return {"user_id": account.user_id, "username": account.username or account.user_id, "email": account.email, "name": account.display_name or account.username or account.email or account.user_id, "role": "admin" if account.role.lower() in {"admin", "administrator"} else "citizen"}


def local_account_exists(identifier: str) -> bool:
    clean = str(identifier).strip()
    with get_session() as session:
        return session.scalar(select(UserAccount.user_id).where(or_(UserAccount.user_id == clean, UserAccount.username == clean, UserAccount.email == clean))) is not None


def update_user_account(
    user_id: str,
    display_name: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    username: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Any]:
    with get_session() as session:
        account = session.get(UserAccount, str(user_id))
        if account is None:
            account = UserAccount(user_id=str(user_id), display_name=display_name, role=role or "Citizen User", is_active=True if is_active is None else is_active, username=username, email=email, password_hash=_hash_local_password(password) if password else None)
            session.add(account)
        else:
            if display_name is not None: account.display_name = display_name
            if role is not None: account.role = role
            if is_active is not None: account.is_active = is_active
            if username is not None: account.username = username.strip() or None
            if email is not None: account.email = email.strip() or None
            if password: account.password_hash = _hash_local_password(password)
        session.flush()
        return {"user_id": account.user_id, "display_name": account.display_name, "username": account.username, "email": account.email, "role": account.role, "is_active": account.is_active,
                "updated_at": account.updated_at.isoformat() if account.updated_at else None}


def deactivate_user_account(user_id: str) -> Optional[Dict[str, Any]]:
    return update_user_account(user_id, is_active=False)


def is_user_active(user_id: str) -> bool:
    """Return account state; identities without local metadata remain active."""
    with get_session() as session:
        account = session.get(UserAccount, str(user_id))
        return account is None or bool(account.is_active)


def get_admin_overview() -> Dict[str, Any]:
    """Return persisted admin metrics strictly from application database and registered services."""
    with get_session() as session:
        prediction_count = int(session.scalar(select(func.count()).select_from(UserPrediction)) or 0)
        active_alerts = int(session.scalar(select(func.count()).select_from(Alert).where(Alert.is_active == True)) or 0)
        pending_reports = int(session.scalar(
            select(func.count()).select_from(CommunityReport).where(
                CommunityReport.status.in_(["Submitted", "Pending", "Under Review"])
            )
        ) or 0)
        known_ids = set(session.scalars(select(UserPrediction.user_id)).all())
        known_ids.update(session.scalars(select(CommunityReport.user_id).where(CommunityReport.user_id.is_not(None))).all())
        known_ids.update(session.scalars(select(PredictionFeedback.user_id)).all())
        clean_user_ids = {str(value).strip() for value in known_ids if value and str(value).strip()}
        latest_prediction = session.scalars(select(UserPrediction).order_by(UserPrediction.created_at.desc()).limit(1)).first()
        model_metric = session.scalars(
            select(SystemMetric).where(SystemMetric.metric_name.in_(["model_pr_auc", "model_accuracy", "model_performance"]))
            .order_by(SystemMetric.timestamp.desc()).limit(1)
        ).first()
        # Prefer a persisted evaluation metric.  When no offline evaluation
        # has been recorded yet, expose the observed citizen-feedback
        # agreement rate instead of a fabricated accuracy value.
        feedback_total = int(session.scalar(select(func.count()).select_from(PredictionFeedback)) or 0)
        feedback_agree = int(session.scalar(select(func.count()).select_from(PredictionFeedback).where(PredictionFeedback.accuracy == "accurate")) or 0)
        reports_total = int(session.scalar(select(func.count()).select_from(CommunityReport)) or 0)
        activity_predictions = session.scalars(select(UserPrediction).order_by(UserPrediction.created_at.desc()).limit(8)).all()
        activity_reports = session.scalars(select(CommunityReport).order_by(CommunityReport.reported_at.desc()).limit(8)).all()
        activity_feedback = session.scalars(select(PredictionFeedback).order_by(PredictionFeedback.created_at.desc()).limit(8)).all()

        activity: List[Dict[str, Any]] = []
        for row in activity_predictions:
            activity.append({"type": "prediction", "message": f"Prediction generated for {row.locality} ({row.risk_level} risk)", "timestamp": row.created_at.isoformat() if row.created_at else None})
        for row in activity_reports:
            activity.append({"type": "report", "message": f"Community flood report submitted for {row.locality or 'an unlabelled location'} ({row.status})", "timestamp": row.reported_at.isoformat() if row.reported_at else None})
        for row in activity_feedback:
            activity.append({"type": "feedback", "message": f"Prediction feedback received ({row.accuracy})", "timestamp": row.created_at.isoformat() if row.created_at else None})
        activity.sort(key=lambda item: item.get("timestamp") or "", reverse=True)

        return {
            "active_users": len(clean_user_ids),
            "active_users_reason": f"{len(clean_user_ids)} citizen account(s) observed across prediction, report, and feedback records.",
            "known_user_id_count": len(clean_user_ids),
            "predictions_generated": prediction_count,
            "active_alerts": active_alerts,
            "pending_reports": pending_reports,
            # Totals let the admin UI detect newly-arrived citizen submissions
            # without exposing report/feedback payloads in the overview call.
            "reports_submitted": reports_total,
            "feedback_submissions": feedback_total,
            "datasets": len(REGISTERED_DATASETS),
            "datasets_reason": f"{len(REGISTERED_DATASETS)} registered operational datasets (HydroBASINS, Admin Boundaries, Far North Flood Catalogue, Open-Meteo, GloFAS, Far North Gazetteer).",
            "model_performance": (model_metric.metric_value if model_metric else (round((feedback_agree / feedback_total) * 100, 1) if feedback_total else None)),
            "model_performance_metric": (model_metric.metric_name if model_metric else (f"citizen feedback agreement ({feedback_total} record{'s' if feedback_total != 1 else ''})" if feedback_total else "no evaluation records")),
            "far_north_latest_prediction": latest_prediction.to_dict() if latest_prediction else None,
            "activity": activity[:12],
        }


def get_admin_users(limit: int = 200) -> List[Dict[str, Any]]:
    """List identities observed in persisted application records."""
    with get_session() as session:
        rows: Dict[str, Dict[str, Any]] = {}
        for prediction in session.scalars(select(UserPrediction).order_by(UserPrediction.created_at.desc())).all():
            key = str(prediction.user_id)
            item = rows.setdefault(key, {"user_id": key, "source": "prediction records", "role": "Citizen User", "prediction_count": 0, "report_count": 0, "feedback_count": 0, "last_seen": None})
            item["prediction_count"] += 1
            item["last_seen"] = max(item["last_seen"] or "", prediction.created_at.isoformat() if prediction.created_at else "")
        for report in session.scalars(select(CommunityReport).where(CommunityReport.user_id.is_not(None)).order_by(CommunityReport.reported_at.desc())).all():
            key = str(report.user_id)
            item = rows.setdefault(key, {"user_id": key, "source": "community reports", "role": "Citizen User", "prediction_count": 0, "report_count": 0, "feedback_count": 0, "last_seen": None})
            item["report_count"] += 1
            item["last_seen"] = max(item["last_seen"] or "", report.reported_at.isoformat() if report.reported_at else "")
        for feedback in session.scalars(select(PredictionFeedback).order_by(PredictionFeedback.created_at.desc())).all():
            key = str(feedback.user_id)
            item = rows.setdefault(key, {"user_id": key, "source": "prediction feedback", "role": "Citizen User", "prediction_count": 0, "report_count": 0, "feedback_count": 0, "last_seen": None})
            item["feedback_count"] += 1
            item["last_seen"] = max(item["last_seen"] or "", feedback.created_at.isoformat() if feedback.created_at else "")
        for account in session.scalars(select(UserAccount)).all():
            item = rows.setdefault(account.user_id, {"user_id": account.user_id, "source": "account metadata", "role": account.role, "prediction_count": 0, "report_count": 0, "feedback_count": 0, "last_seen": None})
            item["display_name"] = account.display_name
            item["username"] = account.username
            item["email"] = account.email
            item["role"] = account.role
            item["is_active"] = account.is_active
        return sorted(rows.values(), key=lambda item: item.get("last_seen") or "", reverse=True)[:limit]


def get_admin_predictions(limit: int = 200) -> List[Dict[str, Any]]:
    with get_session() as session:
        rows = session.scalars(select(UserPrediction).order_by(UserPrediction.created_at.desc()).limit(limit)).all()
        return [row.to_dict() for row in rows]


def get_admin_analytics() -> Dict[str, Any]:
    with get_session() as session:
        rows = session.scalars(select(UserPrediction).order_by(UserPrediction.created_at.asc())).all()
        risk_counts: Dict[str, int] = {}
        locality_counts: Dict[str, int] = {}
        for row in rows:
            risk_counts[row.risk_level] = risk_counts.get(row.risk_level, 0) + 1
            locality_counts[row.locality] = locality_counts.get(row.locality, 0) + 1
        return {
            "prediction_count": len(rows),
            "risk_distribution": [{"risk_level": key, "count": value} for key, value in sorted(risk_counts.items())],
            "locality_distribution": [{"locality": key, "count": value} for key, value in sorted(locality_counts.items(), key=lambda pair: pair[1], reverse=True)[:20]],
            "date_range": {"from": rows[0].created_at.isoformat() if rows and rows[0].created_at else None, "to": rows[-1].created_at.isoformat() if rows and rows[-1].created_at else None},
            "recent_predictions": [row.to_dict() for row in reversed(rows[-10:])],
        }


def get_historical_flood_events(limit: int = 50) -> List[Dict[str, Any]]:
    """Load canonical documented Far North historical flood events."""
    csv_path = Path(__file__).resolve().parent.parent.parent.parent / "data_quality" / "farnorth_consolidation" / "canonical_flood_events_farnorth.csv"
    if not csv_path.exists():
        # Fallback to alternate relative location
        csv_path = Path("data_quality/farnorth_consolidation/canonical_flood_events_farnorth.csv")
    events: List[Dict[str, Any]] = []
    try:
      if csv_path.exists():
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Map severity based on evidence quality and summary
                evidence_text = row.get("evidence_summary") or row.get("supporting_evidence") or ""
                sev = "critical" if row.get("evidence_quality") == "VERY_HIGH" and ("morts" in str(evidence_text).lower() or "death" in str(evidence_text).lower() or "homeless" in str(evidence_text).lower() or "deplaces" in str(evidence_text).lower()) else ("high" if row.get("evidence_quality") in ("VERY_HIGH", "HIGH") else "moderate")
                events.append({
                    "id": row.get("canonical_event_id"),
                    "event_id": row.get("canonical_event_id"),
                    "status": row.get("event_status"),
                    "start_date": row.get("event_start_date"),
                    "end_date": row.get("event_end_date"),
                    "date": row.get("event_start_date"),
                    "year": str(row.get("event_start_date") or "")[:4] or None,
                    "date_precision": row.get("date_precision"),
                    "locality": row.get("locality_name"),
                    "division": row.get("division"),
                    "region": row.get("region", "Far North"),
                    "severity": sev,
                    "evidence_quality": row.get("evidence_quality"),
                    "evidence_summary": evidence_text,
                    "description": evidence_text,
                    "supporting_evidence": row.get("supporting_evidence"),
                    "source_title": row.get("source_document_title"),
                    "source_url": row.get("source_document_url"),
                    "source": row.get("source_document_url") or row.get("source_document_title"),
                })
                if len(events) >= limit:
                    break
      # Verified community events retain provenance and are deliberately
      # surfaced here without being injected into model-training data.
      with get_session() as session:
        verified = session.scalars(select(VerifiedFloodEvent).order_by(VerifiedFloodEvent.event_date.desc().nullslast()).limit(limit)).all()
        events.extend({"id": f"COMMUNITY-{row.id}", "event_id": f"COMMUNITY-{row.id}",
                       "status": "VERIFIED", "date": row.event_date.isoformat() if row.event_date else None,
                       "year": str(row.event_date.year) if row.event_date else None,
                       "locality": row.locality, "division": row.division, "region": row.region,
                       "severity": row.severity or "moderate", "description": row.description,
                       "evidence_summary": row.description, "source": "Verified community report"} for row in verified)
    except Exception as e:
        log.error("Failed to read canonical historical flood events: %s", e)
    return events[:limit]


# ---------------------------------------------------------------------------
# GeoJSON endpoints (served by server.py)
# ---------------------------------------------------------------------------

def get_regions_geojson() -> Dict[str, Any]:
    """Return all Region boundaries as a GeoJSON FeatureCollection."""
    with get_session() as session:
        regions = session.scalars(select(Region)).all()
        features = []
        for r in regions:
            geom_wkb = session.scalar(
                select(func.ST_AsGeoJSON(Region.geom)).where(Region.id == r.id)
            )
            features.append({
                "type": "Feature",
                "properties": {
                    "id":       r.id,
                    "name":     r.name,
                    "name_fr":  r.name_fr,
                    "pcode":    r.pcode,
                },
                "geometry": json.loads(geom_wkb) if geom_wkb else None,
            })
    return {"type": "FeatureCollection", "features": features}


def get_basins_geojson() -> Dict[str, Any]:
    """Return all RiverBasin polygons with risk attributes as a GeoJSON FeatureCollection."""
    with get_session() as session:
        basins = session.scalars(select(RiverBasin)).all()
        features = []
        for b in basins:
            geom_json = session.scalar(
                select(func.ST_AsGeoJSON(RiverBasin.geom)).where(RiverBasin.id == b.id)
            )
            missing = []
            if b.missing_inputs:
                try:
                    missing = json.loads(b.missing_inputs)
                except Exception:
                    pass
            features.append({
                "type": "Feature",
                "properties": {
                    "id":                       b.id,
                    "name":                     b.name,
                    "hybas_id":                 b.hybas_id,
                    "basin_size_sqkm":          b.basin_size_sqkm,
                    "current_streamflow_cms":   b.current_streamflow_cms,
                    "current_risk_level":       b.current_risk_level,
                    "risk_score":               b.risk_score,
                    "local_rainfall_threshold_mm": b.local_rainfall_threshold_mm,
                    "two_day_rainfall_threshold_mm": b.two_day_rainfall_threshold_mm,
                    "risk_source":              b.risk_source,
                    "trigger_reasons":          json.loads(b.trigger_reasons) if b.trigger_reasons else [],
                    "flood_stage_cms":          b.flood_stage_cms,
                    "trend":                    b.trend,
                    "trend_rate_cms_per_hour":  b.trend_rate_cms_per_hour,
                    "discharge_cms":            b.discharge_cms,
                    "discharge_status":         b.discharge_status,
                    "data_completeness":        b.data_completeness,
                    "missing_inputs":           missing,
                    "last_updated":             b.last_updated.isoformat() if b.last_updated else None,
                },
                "geometry": json.loads(geom_json) if geom_json else None,
            })
    return {"type": "FeatureCollection", "features": features}


def get_farnorth_risk_zones_geojson() -> Dict[str, Any]:
    """Return Far North Arrondissement polygons with operational risk attributes as GeoJSON."""
    try:
        import sys
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from farnorth_risk_engine import _scores, _catalogue, norm
        scores_df = _scores()
        cat_df = _catalogue()
    except Exception as exc:
        log.warning(f"Could not load risk engine caches for GIS zones: {exc}")
        scores_df = None
        cat_df = None

    with get_session() as session:
        stmt = (
            select(
                Arrondissement.id,
                Arrondissement.name,
                Arrondissement.name_fr,
                Arrondissement.pcode,
                Arrondissement.center_lat,
                Arrondissement.center_lon,
                Department.name.label("department_name"),
                func.ST_AsGeoJSON(Arrondissement.geom).label("geom_json")
            )
            .join(Department, Arrondissement.department_id == Department.id)
            .join(Region, Department.region_id == Region.id)
            .where(or_(Region.name == "Far-North", Region.pcode == "CM004"))
        )
        rows = session.execute(stmt).all()
        features = []
        for r in rows:
            aname = r.name or ""
            dname = r.department_name or ""
            susceptibility = 50.0
            event_count = 0
            if scores_df is not None:
                hit = scores_df[scores_df.name.map(norm).eq(norm(aname))]
                if not hit.empty:
                    susceptibility = float(hit.iloc[0].susceptibility_score)
                else:
                    dept_hits = scores_df[scores_df.division.astype(str).map(norm).eq(norm(dname))]
                    if not dept_hits.empty:
                        susceptibility = float(dept_hits.susceptibility_score.median())

            if cat_df is not None:
                for _, e in cat_df.iterrows():
                    text = ' '.join([str(e.get('locality_name', '')), str(e.get('division', ''))]).casefold()
                    if norm(aname) in norm(text) or (dname and norm(dname) in norm(text)):
                        event_count += 1

            density = min(100.0, (event_count / 3.0) * 100.0)
            risk_score = round(0.70 * susceptibility + 0.30 * density, 1)
            risk_level = "High" if risk_score >= 67.0 else ("Moderate" if risk_score >= 34.0 else "Low")

            features.append({
                "type": "Feature",
                "properties": {
                    "id": r.id,
                    "name": aname,
                    "name_fr": r.name_fr,
                    "pcode": r.pcode,
                    "department": dname,
                    "center_lat": r.center_lat,
                    "center_lon": r.center_lon,
                    "risk_level": risk_level,
                    "risk_score": risk_score,
                    "susceptibility_score": round(susceptibility, 1),
                    "historical_events": event_count,
                },
                "geometry": json.loads(r.geom_json) if r.geom_json else None,
            })
    return {"type": "FeatureCollection", "features": features}


# ---------------------------------------------------------------------------
# Cache (lightweight key-value, compatible with existing usage)
# ---------------------------------------------------------------------------

def cache_put(key: str, value: str) -> str:
    with get_session() as session:
        existing = session.get(Cache, key)
        if existing:
            existing.value = value
        else:
            session.add(Cache(key=key, value=value))
    return value


def cache_get(key: str) -> Optional[str]:
    with get_session() as session:
        row = session.get(Cache, key)
        return row.value if row else None


def cache_delete(key: str):
    with get_session() as session:
        row = session.get(Cache, key)
        if row:
            session.delete(row)


# ---------------------------------------------------------------------------
# SQLite Adapter Wrappers (for compatibility with agents & server.py)
# ---------------------------------------------------------------------------

def init_app_db(db_path: str):
    """Initialise database (wrapper for backwards compatibility)."""
    init_db()


def get_watersheds(db_path: str = None, region_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all watersheds (river basins) for compatibility."""
    return get_all_basins(region_pcode=region_code)


def get_active_alerts(db_path: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Get active alerts."""
    with get_session() as session:
        alerts = session.scalars(
            select(Alert)
            .where(Alert.is_active == True)
            .order_by(Alert.issued_time.desc())
            .limit(limit)
        ).all()
        return [
            {
                "alert_id": a.id,
                "alert_type": a.alert_type,
                "watershed": a.basin.name if a.basin else "Cameroon",
                "message": a.message,
                "severity": a.severity,
                "issued_time": a.issued_time.isoformat() if a.issued_time else None,
                "expires_time": a.expires_time.isoformat() if a.expires_time else None,
                "affected_counties": json.loads(a.affected_areas) if a.affected_areas else [],
                "data_source": a.data_source,
            }
            for a in alerts
        ]


def get_risk_trend_data(db_path: str = None) -> List[Dict[str, Any]]:
    """Get risk trend data."""
    with get_session() as session:
        trends = session.scalars(
            select(RiskTrend)
            .order_by(RiskTrend.timestamp.desc())
            .limit(24)
        ).all()
        return [
            {
                "time": t.timestamp.strftime('%H:00') if t.timestamp else "",
                "risk": round(t.risk_score, 1),
                "watersheds": 1
            }
            for t in reversed(trends)
        ]


def clear_expired_alerts(db_path: str = None):
    """Mark expired alerts as inactive."""
    with get_session() as session:
        now = datetime.now(timezone.utc)
        expired = session.scalars(
            select(Alert).where(Alert.expires_time < now).where(Alert.is_active == True)
        ).all()
        for a in expired:
            a.is_active = False


def clear_sample_alerts(db_path: str = None) -> int:
    """Clear all sample alerts from the database."""
    with get_session() as session:
        deleted = session.execute(
            text("DELETE FROM alerts WHERE data_source = 'sample'")
        )
        return deleted.rowcount


def populate_sample_data(db_path: str = None):
    """Populate with mock/sample data."""
    with get_session() as session:
        basins = session.scalars(select(RiverBasin)).all()
        for i, b in enumerate(basins):
            b.current_streamflow_cms = 15.0 + (i * 2.5) % 30.0
            b.flood_stage_cms = 50.0 + (i * 5.0) % 50.0
            b.risk_score = round((b.current_streamflow_cms / b.flood_stage_cms) * 10.0, 1) if b.flood_stage_cms else 2.0
            b.current_risk_level = "High" if b.risk_score >= 7.0 else "Moderate" if b.risk_score >= 4.0 else "Low"


def get_user_settings(db_path: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user settings."""
    with get_session() as session:
        row = session.scalars(select(UserSetting).where(UserSetting.user_id == user_id)).first()
        return json.loads(row.settings_data) if row else None


def save_user_settings(db_path: str, user_id: str, settings_data: Dict[str, Any]):
    """Save user settings."""
    with get_session() as session:
        row = session.scalars(select(UserSetting).where(UserSetting.user_id == user_id)).first()
        if row:
            row.settings_data = json.dumps(settings_data)
        else:
            session.add(UserSetting(user_id=user_id, settings_data=json.dumps(settings_data)))


def delete_user_settings(db_path: str, user_id: str):
    """Delete user settings."""
    with get_session() as session:
        row = session.scalars(select(UserSetting).where(UserSetting.user_id == user_id)).first()
        if row:
            session.delete(row)


def save_user_prediction(user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Persist an authenticated user's prediction to the database."""
    with get_session() as session:
        locality = str(data.get("locality") or data.get("name") or "Unknown")
        risk_level_value = data.get("risk_level")
        risk_pct_value = data.get("estimated_risk_percent") if data.get("estimated_risk_percent") is not None else data.get("risk_percent")
        confidence_value = data.get("confidence_score") if data.get("confidence_score") is not None else data.get("confidence")
        if not locality or locality == "Unknown" or risk_level_value is None or risk_pct_value is None or confidence_value is None:
            raise ValueError("Cannot persist an incomplete authoritative prediction")
        risk_level = str(risk_level_value)
        risk_pct = float(risk_pct_value)
        confidence = float(confidence_value)
        forecast_period = str(data.get("forecast_period") or "Next 24–72 hrs")
        details_json = json.dumps(data.get("details") or data)

        record = UserPrediction(
            user_id=str(user_id),
            locality=locality,
            risk_level=risk_level,
            estimated_risk_percent=risk_pct,
            confidence_score=confidence,
            forecast_period=forecast_period,
            details=details_json,
        )
        session.add(record)
        session.flush()
        return record.to_dict()


def get_user_latest_prediction(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the most recent prediction for an authenticated user."""
    with get_session() as session:
        stmt = (
            select(UserPrediction)
            .where(UserPrediction.user_id == str(user_id))
            .order_by(UserPrediction.created_at.desc(), UserPrediction.id.desc())
        )
        row = session.scalars(stmt).first()
        return row.to_dict() if row else None


def list_user_predictions(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve prediction history strictly owned by the authenticated user."""
    with get_session() as session:
        stmt = (
            select(UserPrediction)
            .where(UserPrediction.user_id == str(user_id))
            .order_by(UserPrediction.created_at.desc(), UserPrediction.id.desc())
            .limit(limit)
        )
        rows = session.scalars(stmt).all()
        return [r.to_dict() for r in rows]



def get_watershed_context(db_path: str, watershed_id: int) -> Dict[str, Any]:
    """Get watershed context for chat."""
    with get_session() as session:
        b = session.get(RiverBasin, watershed_id)
        return _basin_to_dict(b) if b else {}


def generate_ai_response(db_path: str, message: str, watershed_id: Optional[int], context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate AI response (dummy fallback)."""
    return {
        "content": f"I am the Cameroon Flood Intelligence AI. I received your message about basin {watershed_id}: '{message}'. Currently, all systems are monitoring the Cameroon river basins.",
        "confidence": 0.95,
        "recommendations": ["Monitor weather updates", "Check community report status"]
    }


def get_analytics_data(db_path: str, time_range: str, metric: str) -> Dict[str, Any]:
    """Get analytics data."""
    # The analytics UI uses aggregate fields that are different from the
    # dashboard summary.  Return them explicitly instead of exposing the
    # dashboard's internal ``*_basins`` names.
    with get_session() as session:
        avg_risk_score = session.scalar(select(func.avg(RiverBasin.risk_score))) or 0.0
        avg_flow = session.scalar(
            select(func.avg(RiverBasin.current_streamflow_cms))
        ) or 0.0
        high_risk_count = session.scalar(
            select(func.count())
            .select_from(RiverBasin)
            .where(RiverBasin.current_risk_level == "High")
        ) or 0
        trending_up_count = session.scalar(
            select(func.count())
            .select_from(RiverBasin)
            .where(RiverBasin.trend == "rising")
        ) or 0

    return {
        "summary": {
            "avg_risk_score": round(avg_risk_score, 1),
            "high_risk_count": high_risk_count,
            "avg_flow": round(avg_flow, 1),
            "trending_up_count": trending_up_count,
        },
        "historical_data": get_historical_analytics_data(db_path, time_range),
        "risk_distribution": get_risk_distribution_data(db_path),
        "watershed_comparison": get_watershed_comparison_data(db_path),
        "flow_comparison": get_flow_comparison_data(db_path)
    }


def get_historical_analytics_data(db_path: str, time_range: str) -> List[Dict[str, Any]]:
    """Get historical analytics data."""
    with get_session() as session:
        trends = session.scalars(select(RiskTrend).order_by(RiskTrend.timestamp.desc()).limit(30)).all()
        return [
            {
                "date": t.timestamp.strftime('%Y-%m-%d') if t.timestamp else "",
                "time": t.timestamp.strftime('%H:%M') if t.timestamp else "",
                "avg_risk_score": round(t.risk_score, 1),
                "avg_flow": round(t.streamflow_cms, 1),
                "high_risk_count": 1 if t.risk_score >= 7.0 else 0,
                "alerts_count": 0
            }
            for t in reversed(trends)
        ]


def get_risk_distribution_data(db_path: str) -> List[Dict[str, Any]]:
    """Get risk distribution data."""
    with get_session() as session:
        high = session.scalar(select(func.count()).select_from(RiverBasin).where(RiverBasin.current_risk_level == "High")) or 0
        mod = session.scalar(select(func.count()).select_from(RiverBasin).where(RiverBasin.current_risk_level == "Moderate")) or 0
        low = session.scalar(select(func.count()).select_from(RiverBasin).where(RiverBasin.current_risk_level == "Low")) or 0
        total = high + mod + low
        if total == 0:
            return []
        return [
            {"name": "High Risk", "value": high, "color": "#ef4444", "percentage": int((high/total)*100)},
            {"name": "Moderate Risk", "value": mod, "color": "#f59e0b", "percentage": int((mod/total)*100)},
            {"name": "Low Risk", "value": low, "color": "#10b981", "percentage": int((low/total)*100)}
        ]


def get_watershed_comparison_data(db_path: str) -> List[Dict[str, Any]]:
    """Get watershed comparison data."""
    with get_session() as session:
        basins = session.scalars(select(RiverBasin).limit(10)).all()
        return [
            {
                "name": b.name,
                "risk_score": b.risk_score,
                "flow_ratio": round(b.current_streamflow_cms / (b.flood_stage_cms or 50.0), 2) if b.flood_stage_cms else 0.2,
                "current_flow": b.current_streamflow_cms
            }
            for b in basins
        ]


def get_flow_comparison_data(db_path: str) -> List[Dict[str, Any]]:
    """Get flow comparison data."""
    with get_session() as session:
        basins = session.scalars(select(RiverBasin).limit(10)).all()
        return [
            {
                "name": b.name,
                "current_flow": b.current_streamflow_cms,
                "flood_stage": b.flood_stage_cms or 50.0,
                "capacity_used": round((b.current_streamflow_cms / (b.flood_stage_cms or 50.0)) * 100, 1)
            }
            for b in basins
        ]
