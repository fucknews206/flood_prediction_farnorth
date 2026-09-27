"""
seed_cameroon.py — Load Cameroon geographic data into the PostGIS database.

Sources
-------
  core/data/geo/cmr_admin1.shp  →  Region         (10 rows)  — adm1_name (EN)
  core/data/geo/cmr_admin2.shp  →  Department     (58 rows)  — adm2_name1 (FR ref)
  core/data/geo/cmr_admin3.shp  →  Arrondissement (360 rows) — adm3_name1 (FR ref)
  core/data/geo/cameroon_basins.geojson → RiverBasin (32 rows)

Name fields
-----------
  adm1_name  = English display name  → Region.name
  adm1_name1 = French display name   → Region.name_fr
  (adm1_ref_n is identical to adm1_name1, not used as primary)

  adm2_name1 (French) used for Department.name/name_fr where English is blank.
  Same pattern for Arrondissement (adm3_name1 is always populated).

Usage
-----
  python -m flood_prediction.seed_cameroon
  or:
  python core/src/flood_prediction/seed_cameroon.py
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Optional

import shapefile
from geoalchemy2.shape import from_shape
from shapely.geometry import shape, MultiPolygon, Polygon
from sqlalchemy import select

# Allow running as a standalone script
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from flood_prediction.db import get_session, init_db
from flood_prediction.models import (
    Arrondissement,
    BasinFlow,
    Department,
    Region,
    RiverBasin,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

GEO_DIR = Path(__file__).resolve().parents[2] / "data" / "geo"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _shp_geom_to_multipolygon(shp_geom) -> Optional[MultiPolygon]:
    """Convert a pyshp geometry object to a Shapely MultiPolygon."""
    try:
        geom = shape(shp_geom.__geo_interface__)
        if isinstance(geom, Polygon):
            return MultiPolygon([geom])
        if isinstance(geom, MultiPolygon):
            return geom
        return None
    except Exception as e:
        log.warning(f"Could not convert geometry: {e}")
        return None


def _geojson_geom_to_multipolygon(geojson_geom: dict) -> Optional[MultiPolygon]:
    """Convert a GeoJSON geometry dict to a Shapely MultiPolygon."""
    try:
        geom = shape(geojson_geom)
        if isinstance(geom, Polygon):
            return MultiPolygon([geom])
        if isinstance(geom, MultiPolygon):
            return geom
        return None
    except Exception as e:
        log.warning(f"Could not convert GeoJSON geometry: {e}")
        return None


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------

def seed_regions(session) -> Dict[str, int]:
    """Load cmr_admin1.shp → Region. Returns {pcode: id} map."""
    path = GEO_DIR / "cmr_admin1.shp"
    sf = shapefile.Reader(str(path))
    fields = [f[0] for f in sf.fields[1:]]

    pcode_to_id: Dict[str, int] = {}
    count = 0

    for sr in sf.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        pcode = rec.get("adm1_pcode", "").strip()
        if not pcode:
            continue

        # Use English name; French from adm1_name1
        name    = (rec.get("adm1_name") or "").strip() or (rec.get("adm1_name1") or "").strip()
        name_fr = (rec.get("adm1_name1") or "").strip() or name

        geom_shp = _shp_geom_to_multipolygon(sr.shape)
        if geom_shp is None:
            log.warning(f"Skipping region {pcode} — no valid geometry")
            continue

        existing = session.scalars(select(Region).where(Region.pcode == pcode)).first()
        if existing:
            pcode_to_id[pcode] = existing.id
            continue

        region = Region(
            name=name,
            name_fr=name_fr,
            pcode=pcode,
            area_sqkm=rec.get("area_sqkm"),
            center_lat=rec.get("center_lat"),
            center_lon=rec.get("center_lon"),
            geom=from_shape(geom_shp, srid=4326),
        )
        session.add(region)
        session.flush()
        pcode_to_id[pcode] = region.id
        count += 1

    log.info(f"Regions inserted: {count}")
    return pcode_to_id


def seed_departments(session, region_pcode_to_id: Dict[str, int]) -> Dict[str, int]:
    """Load cmr_admin2.shp → Department. Returns {pcode: id} map."""
    path = GEO_DIR / "cmr_admin2.shp"
    sf = shapefile.Reader(str(path))
    fields = [f[0] for f in sf.fields[1:]]

    pcode_to_id: Dict[str, int] = {}
    count = 0

    for sr in sf.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        pcode      = rec.get("adm2_pcode", "").strip()
        adm1_pcode = rec.get("adm1_pcode", "").strip()
        if not pcode:
            continue

        # English name may be blank for French-primary departments
        name    = (rec.get("adm2_name") or "").strip() or (rec.get("adm2_name1") or "").strip()
        name_fr = (rec.get("adm2_name1") or "").strip() or name

        region_id = region_pcode_to_id.get(adm1_pcode)
        if not region_id:
            log.warning(f"Department {pcode}: parent region {adm1_pcode} not found, skipping")
            continue

        geom_shp = _shp_geom_to_multipolygon(sr.shape)
        if geom_shp is None:
            log.warning(f"Skipping department {pcode} — no valid geometry")
            continue

        existing = session.scalars(select(Department).where(Department.pcode == pcode)).first()
        if existing:
            pcode_to_id[pcode] = existing.id
            continue

        dept = Department(
            name=name,
            name_fr=name_fr,
            pcode=pcode,
            area_sqkm=rec.get("area_sqkm"),
            center_lat=rec.get("center_lat"),
            center_lon=rec.get("center_lon"),
            region_id=region_id,
            geom=from_shape(geom_shp, srid=4326),
        )
        session.add(dept)
        session.flush()
        pcode_to_id[pcode] = dept.id
        count += 1

    log.info(f"Departments inserted: {count}")
    return pcode_to_id


def seed_arrondissements(session, dept_pcode_to_id: Dict[str, int]) -> int:
    """Load cmr_admin3.shp → Arrondissement."""
    path = GEO_DIR / "cmr_admin3.shp"
    sf = shapefile.Reader(str(path))
    fields = [f[0] for f in sf.fields[1:]]

    count = 0

    for sr in sf.iterShapeRecords():
        rec = dict(zip(fields, sr.record))
        pcode      = rec.get("adm3_pcode", "").strip()
        adm2_pcode = rec.get("adm2_pcode", "").strip()
        if not pcode:
            continue

        name    = (rec.get("adm3_name") or "").strip() or (rec.get("adm3_name1") or "").strip()
        name_fr = (rec.get("adm3_name1") or "").strip() or name

        dept_id = dept_pcode_to_id.get(adm2_pcode)
        if not dept_id:
            log.warning(f"Arrondissement {pcode}: parent dept {adm2_pcode} not found, skipping")
            continue

        geom_shp = _shp_geom_to_multipolygon(sr.shape)
        if geom_shp is None:
            log.warning(f"Skipping arrondissement {pcode} — no valid geometry")
            continue

        existing = session.scalars(
            select(Arrondissement).where(Arrondissement.pcode == pcode)
        ).first()
        if existing:
            continue

        arr = Arrondissement(
            name=name,
            name_fr=name_fr,
            pcode=pcode,
            area_sqkm=rec.get("area_sqkm"),
            center_lat=rec.get("center_lat"),
            center_lon=rec.get("center_lon"),
            department_id=dept_id,
            geom=from_shape(geom_shp, srid=4326),
        )
        session.add(arr)
        count += 1

    session.flush()
    log.info(f"Arrondissements inserted: {count}")
    return count


def seed_river_basins(session) -> int:
    """Load cameroon_basins.geojson → RiverBasin."""
    path = GEO_DIR / "cameroon_basins.geojson"
    with open(path) as f:
        data = json.load(f)

    features = data.get("features", [])
    count = 0

    for feat in features:
        props = feat.get("properties", {})
        hybas_id = props.get("HYBAS_ID")

        existing = session.scalars(
            select(RiverBasin).where(RiverBasin.hybas_id == hybas_id)
        ).first()
        if existing:
            continue

        geom_json = feat.get("geometry")
        if not geom_json:
            log.warning(f"Basin HYBAS_ID={hybas_id}: no geometry, skipping")
            continue

        geom_shp = _geojson_geom_to_multipolygon(geom_json)
        if geom_shp is None:
            log.warning(f"Basin HYBAS_ID={hybas_id}: invalid geometry, skipping")
            continue

        # Use HYBAS_ID as unique identifier; derive a readable name
        name = f"Basin {hybas_id}"

        # area_sqkm comes from 'area_sqkm' or SUB_AREA (already in km²)
        area_sqkm = props.get("area_sqkm") or props.get("SUB_AREA")

        basin = RiverBasin(
            name=name,
            hybas_id=hybas_id,
            basin_size_sqkm=float(area_sqkm) if area_sqkm else None,
            geom=from_shape(geom_shp, srid=4326),
            current_streamflow_cms=0.0,
            flood_stage_cms=None,
            trend="stable",
            trend_rate_cms_per_hour=0.0,
            current_risk_level="Low",
            risk_score=0.0,
            discharge_cms=None,
            discharge_status="unavailable",
            discharge_source="none",
            data_completeness="partial",
            missing_inputs=json.dumps(["discharge"]),
            data_source="none",
            data_quality="unknown",
        )
        session.add(basin)
        count += 1

    session.flush()
    log.info(f"River basins inserted: {count}")
    return count


def seed_phase3_logone_corridor(session) -> int:
    """Seed only the documented Zina → Maga → Blangoua calibration corridor.

    HYBAS IDs were resolved from the supplied historical-event coordinates.
    The links intentionally represent the operational flood corridor from the
    calibration evidence, not an inferred nationwide HydroBASINS topology.
    """
    corridor = {
        "Zina": 1050734180,
        "Maga": 1050695540,
        "Blangoua": 1050695700,
    }
    basins = {}
    for name, hybas_id in corridor.items():
        basin = session.scalars(select(RiverBasin).where(RiverBasin.hybas_id == hybas_id)).first()
        if not basin:
            log.warning("Phase 3 corridor basin %s (HYBAS_ID=%s) not found", name, hybas_id)
            continue
        basin.name = f"{name} (Logone/Chari)"
        basin.local_rainfall_threshold_mm = 20.0
        basin.two_day_rainfall_threshold_mm = 30.0
        basins[name] = basin

    inserted = 0
    evidence = (
        "2019 OCHA/Open-Meteo calibration: Zina 28–29 Sep rainfall preceded "
        "Maga flooding on 4 Oct; Phase 3 operational corridor."
    )
    for upstream_name, downstream_name in (("Zina", "Maga"), ("Maga", "Blangoua")):
        upstream, downstream = basins.get(upstream_name), basins.get(downstream_name)
        if not upstream or not downstream:
            continue
        existing = session.scalars(select(BasinFlow).where(
            BasinFlow.upstream_basin_id == upstream.id,
            BasinFlow.downstream_basin_id == downstream.id,
        )).first()
        if not existing:
            session.add(BasinFlow(
                upstream_basin_id=upstream.id, downstream_basin_id=downstream.id,
                min_propagation_delay_days=5, max_propagation_delay_days=7,
                evidence_note=evidence,
            ))
            inserted += 1
    session.flush()
    log.info("Phase 3 Logone/Chari flow links inserted: %s", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_counts(session) -> bool:
    from sqlalchemy import func, select
    from flood_prediction.models import Region, Department, Arrondissement, RiverBasin

    counts = {
        "Regions":          session.scalar(select(func.count()).select_from(Region)),
        "Departments":      session.scalar(select(func.count()).select_from(Department)),
        "Arrondissements":  session.scalar(select(func.count()).select_from(Arrondissement)),
        "River Basins":     session.scalar(select(func.count()).select_from(RiverBasin)),
    }
    expected = {
        "Regions": 10, "Departments": 58, "Arrondissements": 360, "River Basins": 32
    }

    print("\n── Seed verification ──────────────────────")
    ok = True
    for label, actual in counts.items():
        exp = expected[label]
        status = "✓" if actual == exp else f"✗ (expected {exp})"
        print(f"  {label:<20} {actual:>4}  {status}")
        if actual != exp:
            ok = False
    print("───────────────────────────────────────────\n")
    return ok


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    log.info("Initialising database tables …")
    init_db()

    with get_session() as session:
        log.info("Seeding Regions …")
        region_map = seed_regions(session)

        log.info("Seeding Departments …")
        dept_map = seed_departments(session, region_map)

        log.info("Seeding Arrondissements …")
        seed_arrondissements(session, dept_map)

        log.info("Seeding River Basins …")
        seed_river_basins(session)

        log.info("Seeding Phase 3 Logone/Chari calibration corridor …")
        seed_phase3_logone_corridor(session)

        log.info("Verifying counts …")
        ok = verify_counts(session)

    if not ok:
        log.error("Count verification FAILED — check warnings above.")
        sys.exit(1)

    log.info("Seeding complete.")


if __name__ == "__main__":
    main()
