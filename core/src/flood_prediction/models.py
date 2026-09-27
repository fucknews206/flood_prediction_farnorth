"""
SQLAlchemy + GeoAlchemy2 ORM models for Cameroon Flood Intelligence.

Geographic hierarchy:
    Region (admin-1, 10 rows)
      └─ Department (admin-2, 58 rows)
           └─ Arrondissement (admin-3, 360 rows)

Hydrology:
    RiverBasin  (HydroBASINS level-4 clipped to Cameroon, 32 rows)

All flow/area fields use metric units: m³/s (cms), km².
No imperial-unit field names (cfs, sqmi, ft) exist in this module.
"""

import json
from datetime import date, datetime, timezone
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime,
    Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Administrative Boundaries
# ---------------------------------------------------------------------------

class Region(Base):
    """Cameroon admin-1 regions (10 total)."""
    __tablename__ = "regions"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(100), nullable=False)          # English: "Far-North"
    name_fr     = Column(String(100), nullable=True)           # French:  "Extrême-Nord"
    pcode       = Column(String(20), nullable=False, unique=True)  # "CM004"
    area_sqkm   = Column(Float, nullable=True)
    center_lat  = Column(Float, nullable=True)
    center_lon  = Column(Float, nullable=True)
    geom        = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)

    departments = relationship("Department", back_populates="region",
                               cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_regions_pcode", "pcode"),
    )

    def __repr__(self):
        return f"<Region {self.pcode} {self.name}>"


class Department(Base):
    """Cameroon admin-2 departments (58 total)."""
    __tablename__ = "departments"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String(100), nullable=False)
    name_fr     = Column(String(100), nullable=True)
    pcode       = Column(String(20), nullable=False, unique=True)  # "CM004002"
    area_sqkm   = Column(Float, nullable=True)
    center_lat  = Column(Float, nullable=True)
    center_lon  = Column(Float, nullable=True)
    region_id   = Column(Integer, ForeignKey("regions.id"), nullable=False)
    geom        = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)

    region          = relationship("Region", back_populates="departments")
    arrondissements = relationship("Arrondissement", back_populates="department",
                                   cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_departments_pcode", "pcode"),
        Index("idx_departments_region", "region_id"),
    )

    def __repr__(self):
        return f"<Department {self.pcode} {self.name}>"


class Arrondissement(Base):
    """Cameroon admin-3 arrondissements (360 total)."""
    __tablename__ = "arrondissements"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    name            = Column(String(100), nullable=False)
    name_fr         = Column(String(100), nullable=True)
    pcode           = Column(String(20), nullable=False, unique=True)  # "CM004002003"
    area_sqkm       = Column(Float, nullable=True)
    center_lat      = Column(Float, nullable=True)
    center_lon      = Column(Float, nullable=True)
    department_id   = Column(Integer, ForeignKey("departments.id"), nullable=False)
    geom            = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)

    department = relationship("Department", back_populates="arrondissements")

    __table_args__ = (
        Index("idx_arrondissements_pcode", "pcode"),
        Index("idx_arrondissements_department", "department_id"),
    )

    def __repr__(self):
        return f"<Arrondissement {self.pcode} {self.name}>"


# ---------------------------------------------------------------------------
# Hydrology
# ---------------------------------------------------------------------------

class RiverBasin(Base):
    """
    HydroBASINS level-4 sub-basins clipped to Cameroon (32 total).

    All flow fields use metric units:
        basin_size_sqkm          — area in square kilometres
        current_streamflow_cms   — discharge in cubic metres per second (m³/s)
        flood_stage_cms          — flood threshold in m³/s
        trend_rate_cms_per_hour  — rate of change in m³/s per hour
        discharge_cms            — GloFAS forecast value (None when unavailable)

    discharge_status: "available" | "unavailable" | "stale"
    data_completeness: "full" | "partial"
    """
    __tablename__ = "river_basins"

    id                      = Column(Integer, primary_key=True, autoincrement=True)
    name                    = Column(String(200), nullable=False)
    hybas_id                = Column(BigInteger, nullable=True, unique=True)
    basin_size_sqkm         = Column(Float, default=0.0)
    geom                    = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=False)

    # Current hydrological state — metric units only
    current_streamflow_cms  = Column(Float, nullable=False, default=0.0)
    flood_stage_cms         = Column(Float, nullable=True)
    trend                   = Column(String(10), default="stable")
    trend_rate_cms_per_hour = Column(Float, default=0.0)

    # Risk assessment
    current_risk_level      = Column(
        String(10), nullable=False, default="Low",
        info={"check": "current_risk_level IN ('Low','Moderate','High')"}
    )
    risk_score              = Column(Float, nullable=False, default=0.0)
    # Per-basin calibration values.  Defaults are the evidence-backed Phase 3
    # starting values, and are deliberately stored rather than embedded in
    # scoring code so hydrologists can refine a basin independently.
    local_rainfall_threshold_mm = Column(Float, nullable=False, default=20.0)
    two_day_rainfall_threshold_mm = Column(Float, nullable=False, default=30.0)
    risk_source              = Column(String(40), nullable=False, default="none")
    trigger_reasons          = Column(Text, nullable=True)  # JSON list

    # Discharge / GloFAS
    discharge_cms           = Column(Float, nullable=True)   # None = not available
    discharge_status        = Column(String(20), nullable=False, default="unavailable")
    discharge_source        = Column(String(30), nullable=False, default="none")

    # Partial-data flag
    data_completeness       = Column(String(10), nullable=False, default="partial")
    missing_inputs          = Column(Text, nullable=True)    # JSON list, e.g. '["discharge"]'

    # Provenance
    data_source             = Column(String(20), default="none")
    data_quality            = Column(String(20), default="unknown")
    last_api_update         = Column(DateTime(timezone=True), nullable=True)
    last_updated            = Column(DateTime(timezone=True),
                                     default=lambda: datetime.now(timezone.utc))
    created_at              = Column(DateTime(timezone=True),
                                     default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 10", name="ck_risk_score"),
        CheckConstraint("discharge_status IN ('available','unavailable','stale')",
                        name="ck_discharge_status"),
        CheckConstraint("data_completeness IN ('full','partial')",
                        name="ck_data_completeness"),
        Index("idx_river_basins_hybas_id", "hybas_id"),
        Index("idx_river_basins_risk_level", "current_risk_level"),
        Index("idx_river_basins_last_updated", "last_updated"),
    )

    def __repr__(self):
        return f"<RiverBasin id={self.id} {self.name} risk={self.risk_score}>"


class BasinFlow(Base):
    """An evidence-backed directed flow relationship between two basins."""
    __tablename__ = "basin_flows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    upstream_basin_id = Column(Integer, ForeignKey("river_basins.id"), nullable=False)
    downstream_basin_id = Column(Integer, ForeignKey("river_basins.id"), nullable=False)
    min_propagation_delay_days = Column(Integer, nullable=False, default=5)
    max_propagation_delay_days = Column(Integer, nullable=False, default=7)
    evidence_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    upstream_basin = relationship("RiverBasin", foreign_keys=[upstream_basin_id])
    downstream_basin = relationship("RiverBasin", foreign_keys=[downstream_basin_id])

    __table_args__ = (
        CheckConstraint("upstream_basin_id <> downstream_basin_id", name="ck_basin_flow_not_self"),
        CheckConstraint("min_propagation_delay_days >= 0", name="ck_basin_flow_min_delay"),
        CheckConstraint("max_propagation_delay_days >= min_propagation_delay_days", name="ck_basin_flow_delay_range"),
        Index("idx_basin_flows_downstream", "downstream_basin_id"),
        Index("idx_basin_flows_pair", "upstream_basin_id", "downstream_basin_id", unique=True),
    )


class BasinRainfallObservation(Base):
    """Daily rainfall retained for local calibration and propagation replay."""
    __tablename__ = "basin_rainfall_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    basin_id = Column(Integer, ForeignKey("river_basins.id"), nullable=False)
    observed_on = Column(Date, nullable=False)
    precipitation_mm = Column(Float, nullable=False, default=0.0)
    source = Column(String(40), nullable=False, default="openmeteo")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    basin = relationship("RiverBasin")

    __table_args__ = (
        CheckConstraint("precipitation_mm >= 0", name="ck_rainfall_observation_nonnegative"),
        Index("idx_basin_rainfall_date", "basin_id", "observed_on", unique=True),
    )


# ---------------------------------------------------------------------------
# Community Reports
# ---------------------------------------------------------------------------

class VerifiedFloodEvent(Base):
    """A flood event confirmed by an administrator from a community report."""
    __tablename__ = "verified_flood_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_date = Column(Date, nullable=True)
    locality = Column(String(200), nullable=True)
    division = Column(String(100), nullable=True)
    region = Column(String(100), nullable=False, default="Far North")
    severity = Column(String(30), nullable=True)
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    description = Column(Text, nullable=False)
    source = Column(String(100), nullable=False, default="verified community report")
    originating_report_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    verified_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {"id": self.id, "event_date": self.event_date.isoformat() if self.event_date else None,
                "locality": self.locality, "division": self.division, "region": self.region,
                "severity": self.severity, "location_lat": self.location_lat, "location_lng": self.location_lng,
                "description": self.description, "source": self.source,
                "originating_report_id": self.originating_report_id,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "verified_at": self.verified_at.isoformat() if self.verified_at else None}

class CommunityReport(Base):
    """Crowd-sourced flood report submitted by a community member."""
    __tablename__ = "community_reports"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    reporter_name       = Column(String(200), nullable=True)
    contact_info        = Column(String(200), nullable=True)
    details             = Column(Text, nullable=False)
    location_lat        = Column(Float, nullable=False)
    location_lng        = Column(Float, nullable=False)
    risk_level          = Column(String(10), nullable=True)   # reporter's own assessment

    # Resolved geographic context (populated by point-in-polygon lookup)
    region_id           = Column(Integer, ForeignKey("regions.id"), nullable=True)
    department_id       = Column(Integer, ForeignKey("departments.id"), nullable=True)
    arrondissement_id   = Column(Integer, ForeignKey("arrondissements.id"), nullable=True)
    basin_id            = Column(Integer, ForeignKey("river_basins.id"), nullable=True)

    user_id             = Column(String(100), nullable=True)
    # Citizen-submitted report metadata.  These fields are nullable so
    # existing reports remain readable while the form evolves.
    locality            = Column(String(200), nullable=True)
    division            = Column(String(100), nullable=True)
    observation_at      = Column(DateTime(timezone=True), nullable=True)
    water_depth_category = Column(String(20), nullable=True)
    evidence_name       = Column(String(255), nullable=True)
    # Optional uploaded evidence.  The URL points to the authenticated
    # report-evidence endpoint; media type lets clients render images/videos
    # without guessing from a filename.
    evidence_url        = Column(String(500), nullable=True)
    evidence_media_type = Column(String(100), nullable=True)
    status              = Column(String(30), nullable=False, default="Submitted")
    verification_notes  = Column(Text, nullable=True)
    verified_at         = Column(DateTime(timezone=True), nullable=True)
    linked_event_id     = Column(Integer, nullable=True)
    linked_event_reference = Column(String(200), nullable=True)
    reported_at         = Column(DateTime(timezone=True),
                                  default=lambda: datetime.now(timezone.utc))

    region          = relationship("Region")
    department      = relationship("Department")
    arrondissement  = relationship("Arrondissement")
    basin           = relationship("RiverBasin")

    __table_args__ = (
        Index("idx_community_reports_reported_at", "reported_at"),
        Index("idx_community_reports_basin", "basin_id"),
        Index("idx_community_reports_region", "region_id"),
        Index("idx_community_reports_user_id", "user_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "locality": self.locality,
            "division": self.division,
            "observation_at": self.observation_at.isoformat() if self.observation_at else None,
            "water_depth_category": self.water_depth_category,
            "evidence_name": self.evidence_name,
            "evidence_url": self.evidence_url,
            "evidence_media_type": self.evidence_media_type,
            "status": self.status or "Submitted",
            "reporter_name": self.reporter_name,
            "contact_info": self.contact_info,
            "details": self.details,
            "location_lat": self.location_lat,
            "location_lng": self.location_lng,
            "risk_level": self.risk_level,
            "region": self.region.name if self.region else None,
            "department": self.department.name if self.department else None,
            "arrondissement": self.arrondissement.name if self.arrondissement else None,
            "basin": self.basin.name if self.basin else None,
            "reported_at": self.reported_at.isoformat() if self.reported_at else None,
            "verification_notes": self.verification_notes,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "linked_event_id": self.linked_event_id,
            "linked_event_reference": self.linked_event_reference,
        }

    def __repr__(self):
        return f"<CommunityReport id={self.id} lat={self.location_lat} lon={self.location_lng}>"


class PredictionFeedback(Base):
    """Citizen evaluation of a prediction they actually viewed."""
    __tablename__ = "prediction_feedback"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(String(100), nullable=False)
    prediction_id = Column(Integer, ForeignKey("user_predictions.id"), nullable=False)
    accuracy      = Column(String(30), nullable=False)
    comments      = Column(Text, nullable=True)
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    prediction = relationship("UserPrediction")
    __table_args__ = (
        Index("idx_prediction_feedback_user_time", "user_id", "created_at"),
        Index("idx_prediction_feedback_prediction", "prediction_id"),
    )

    def to_dict(self):
        prediction = self.prediction
        return {
            "id": self.id,
            "user_id": self.user_id,
            "prediction_id": self.prediction_id,
            "prediction_locality": prediction.locality if prediction else None,
            "prediction_risk_level": prediction.risk_level if prediction else None,
            "prediction_estimated_risk_percent": prediction.estimated_risk_percent if prediction else None,
            "accuracy": self.accuracy,
            "comments": self.comments,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class UserAccount(Base):
    """Local admin-manageable account metadata; external identities remain immutable."""
    __tablename__ = "user_accounts"
    user_id = Column(String(100), primary_key=True)
    display_name = Column(String(200), nullable=True)
    username = Column(String(100), nullable=True)
    email = Column(String(254), nullable=True)
    # Passwords are never stored in plaintext.  This is local account
    # metadata only; OIDC/provider credentials remain managed by the provider.
    password_hash = Column(String(255), nullable=True)
    role = Column(String(30), nullable=False, default="Citizen User")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Alert(Base):
    __tablename__ = "alerts"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    alert_type      = Column(String(100), nullable=False)
    basin_id        = Column(Integer, ForeignKey("river_basins.id"), nullable=True)
    message         = Column(Text, nullable=False)
    severity        = Column(String(20), nullable=False)
    issued_time     = Column(DateTime(timezone=True),
                              default=lambda: datetime.now(timezone.utc))
    resolved_time   = Column(DateTime(timezone=True), nullable=True)
    expires_time    = Column(DateTime(timezone=True), nullable=True)
    affected_areas  = Column(Text, default="")      # JSON list of area names
    is_active       = Column(Boolean, default=True)
    data_source     = Column(String(20), default="manual")
    created_at      = Column(DateTime(timezone=True),
                              default=lambda: datetime.now(timezone.utc))

    basin = relationship("RiverBasin")

    __table_args__ = (
        Index("idx_alerts_active", "is_active", "issued_time"),
        Index("idx_alerts_basin", "basin_id"),
    )


# ---------------------------------------------------------------------------
# Risk Trends (time-series for charts)
# ---------------------------------------------------------------------------

class RiskTrend(Base):
    __tablename__ = "risk_trends"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    basin_id    = Column(Integer, ForeignKey("river_basins.id"), nullable=True)
    risk_score  = Column(Float, nullable=False)
    # Streamflow snapshot at recording time — metric units
    streamflow_cms = Column(Float, nullable=False, default=0.0)
    timestamp   = Column(DateTime(timezone=True),
                          default=lambda: datetime.now(timezone.utc))

    basin = relationship("RiverBasin")

    __table_args__ = (
        Index("idx_risk_trends_basin_time", "basin_id", "timestamp"),
        Index("idx_risk_trends_timestamp", "timestamp"),
    )


# ---------------------------------------------------------------------------
# System Metrics & Settings
# ---------------------------------------------------------------------------

class SystemMetric(Base):
    __tablename__ = "system_metrics"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    metric_name  = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    timestamp    = Column(DateTime(timezone=True),
                           default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_system_metrics_name_time", "metric_name", "timestamp"),
    )


class UserSetting(Base):
    __tablename__ = "user_settings"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(String(100), nullable=False, unique=True)
    settings_data = Column(Text, nullable=False)
    created_at    = Column(DateTime(timezone=True),
                            default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(DateTime(timezone=True),
                            default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))


class Item(Base):
    """Legacy compatibility table."""
    __tablename__ = "items"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(200), nullable=False)
    data       = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True),
                         default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True),
                         default=lambda: datetime.now(timezone.utc))


class Cache(Base):
    __tablename__ = "cache"

    key        = Column(String(500), primary_key=True)
    value      = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True),
                         default=lambda: datetime.now(timezone.utc))


class UserPrediction(Base):
    """Authenticated user's historical and latest flood risk predictions."""
    __tablename__ = "user_predictions"

    id                     = Column(Integer, primary_key=True, autoincrement=True)
    user_id                = Column(String(100), nullable=False)
    locality               = Column(String(100), nullable=False)
    risk_level             = Column(String(30), nullable=False)
    estimated_risk_percent = Column(Float, nullable=False)
    confidence_score       = Column(Float, nullable=False, default=90.0)
    forecast_period        = Column(String(50), default="Next 24–72 hrs")
    details                = Column(Text, nullable=True)  # JSON-encoded raw factors/payload
    created_at             = Column(DateTime(timezone=True),
                                    default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_user_predictions_user_time", "user_id", "created_at"),
        Index("idx_user_predictions_user_id", "user_id"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "locality": self.locality,
            "risk_level": self.risk_level,
            "estimated_risk_percent": self.estimated_risk_percent,
            "confidence_score": self.confidence_score,
            "forecast_period": self.forecast_period,
            "details": json.loads(self.details) if self.details else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
