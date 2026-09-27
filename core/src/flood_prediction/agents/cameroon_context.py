"""Read-only Cameroon context used by the AI-facing tools.

This module deliberately consumes the Stage 1/2 PostGIS models and their
already-computed risk values.  It does not run ingestion or recalculate risk.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select

from ..db import _basin_to_dict, get_session, resolve_location_to_entities
from ..models import CommunityReport, Department, Region, RiverBasin, RiskTrend, Arrondissement
from .data_collector import DataCollectorAgent


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _find_named_entity(session, location: str):
    """Find a Cameroon administrative entity or basin by English/French name."""
    needle = _normalise(location)
    if not needle:
        return None, None
    for model, kind in ((Region, "region"), (Department, "department"),
                        (Arrondissement, "arrondissement"), (RiverBasin, "basin")):
        candidates = session.scalars(select(model)).all()
        for candidate in candidates:
            names = [getattr(candidate, "name", None), getattr(candidate, "name_fr", None)]
            if any(name and _normalise(name) == needle for name in names):
                return kind, candidate
    return None, None


def _basins_for_entity(session, kind: str, entity) -> List[RiverBasin]:
    if kind == "basin":
        return [entity]
    geom = entity.geom
    return session.scalars(
        select(RiverBasin).where(func.ST_Intersects(RiverBasin.geom, geom))
    ).all()


def _entity_summary(kind: Optional[str], entity) -> Optional[Dict[str, Any]]:
    if entity is None:
        return None
    result = {"type": kind, "id": entity.id, "name": entity.name}
    if hasattr(entity, "name_fr"):
        result["name_fr"] = entity.name_fr
    if hasattr(entity, "pcode"):
        result["pcode"] = entity.pcode
    return result


def _recent_reports(session, basin_ids: List[int], entity) -> List[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(days=7)
    filters = [CommunityReport.reported_at >= since]
    scoped = []
    if basin_ids:
        scoped.append(CommunityReport.basin_id.in_(basin_ids))
    if isinstance(entity, Region):
        scoped.append(CommunityReport.region_id == entity.id)
    elif isinstance(entity, Department):
        scoped.append(CommunityReport.department_id == entity.id)
    elif isinstance(entity, Arrondissement):
        scoped.append(CommunityReport.arrondissement_id == entity.id)
    if scoped:
        filters.append(or_(*scoped))
    reports = session.scalars(select(CommunityReport).where(*filters)
                              .order_by(CommunityReport.reported_at.desc()).limit(20)).all()
    return [{"id": report.id, "details": report.details, "risk_level": report.risk_level,
             "reported_at": report.reported_at.isoformat() if report.reported_at else None,
             "basin_id": report.basin_id} for report in reports]


def _risk_trend(session, basin_ids: List[int]) -> Dict[str, Any]:
    if not basin_ids:
        return {"direction": "unavailable", "recent_points": 0}
    rows = session.scalars(select(RiskTrend).where(RiskTrend.basin_id.in_(basin_ids))
                           .order_by(RiskTrend.timestamp.desc()).limit(20)).all()
    if len(rows) < 2:
        return {"direction": "stable", "recent_points": len(rows)}
    newest, oldest = rows[0], rows[-1]
    delta = round(newest.risk_score - oldest.risk_score, 1)
    return {"direction": "rising" if delta > 0 else "falling" if delta < 0 else "stable",
            "change": delta, "recent_points": len(rows)}


async def _rainfall_trend(basins: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Fetch a current Cameroon rainfall snapshot without altering stored risk."""
    if not basins:
        return {"status": "unavailable", "reason": "No matched basin"}
    rainfall = await DataCollectorAgent().collect_openmeteo_rainfall(basins)
    values = list(rainfall.values())
    return {"status": "available", "period": "next 24 hours", "basin_mm": rainfall,
            "average_mm": round(sum(values) / len(values), 1) if values else 0.0}


async def build_cameroon_context(location: Optional[str] = None,
                                 lat: Optional[float] = None,
                                 lon: Optional[float] = None) -> Dict[str, Any]:
    """Resolve a query and return its Stage 1/2 basin context.

    A named place is resolved before coordinates, so requests such as
    ``Far North`` never fall into a coordinate/USGS fallback.
    """
    with get_session() as session:
        kind = entity = None
        if location:
            kind, entity = _find_named_entity(session, location)
        if entity is None and lat is not None and lon is not None:
            resolved = resolve_location_to_entities(lat, lon)
            basin_id = resolved["basin"]["id"] if resolved["basin"] else None
            if basin_id:
                kind, entity = "basin", session.get(RiverBasin, basin_id)
        basins = _basins_for_entity(session, kind, entity) if entity is not None else []
        basin_dicts = []
        for basin in basins:
            lat, lon = session.execute(select(
                func.ST_Y(func.ST_Centroid(RiverBasin.geom)),
                func.ST_X(func.ST_Centroid(RiverBasin.geom)),
            ).where(RiverBasin.id == basin.id)).one()
            basin_dicts.append(_basin_to_dict(basin, lat=lat, lon=lon))
        basin_ids = [b.id for b in basins]
        reports = _recent_reports(session, basin_ids, entity)
        risk_trend = _risk_trend(session, basin_ids)
        target = _entity_summary(kind, entity)

    # Open-Meteo is only a current rainfall observation; risk values stay those
    # calculated and stored by the Stage 1/2 ingestion job.
    rainfall = await _rainfall_trend(basin_dicts)
    has_data = bool(basin_dicts or reports or rainfall.get("status") == "available")
    return {"location": location, "resolved_entity": target, "basins": basin_dicts,
            "recent_rainfall": rainfall, "recent_community_reports": reports,
            "risk_trend": risk_trend, "has_data": has_data,
            "timestamp": datetime.now(timezone.utc).isoformat()}
