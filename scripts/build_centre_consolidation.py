#!/usr/bin/env python3
"""Build traceable Centre-region environmental and assistant datasets.

This script deliberately refuses to manufacture flood labels.  It produces an
unlabelled feature table and a knowledge layer when no verified Centre event
catalogue is available, and writes the reason to the validation reports.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from scipy.spatial import cKDTree


ROOT = Path("/home/ongou/Desktop/projects/end-of -year-defence")
PROJECT = ROOT / "h2oai-flood-intelligence-agent-main"
OUT = PROJECT / "data_quality" / "centre_consolidation"
ERA5_DIR = ROOT / "ERA5-datasets" / "Centre"
GLOFAS_DIR = ROOT / "GLOFAS-datasets"
CHIRPS_DIR = ROOT / "CHIRPS-datasets"
BOUNDARY_DIR = ROOT / "boundaries-data"
HYBASINS = ROOT / "HydroBasins-datasets" / "hybas_af_lev01-12_v1c" / "hybas_af_lev06_v1c.shp"
MASTER_EVENTS = ROOT / "flood-event-extractor" / "final_dataset" / "master_events.csv"
LOCALITY_DEM = Path("/home/ongou/Downloads/DEM_slope_localities.csv")

ERA5_RENAME = {
    "tp": "total_precipitation_m",
    "ro": "runoff_m",
    "ssro": "sub_surface_runoff_m",
    "swvl1": "soil_water_layer_1_m3m3",
    "t2m": "temperature_2m_k",
    "d2m": "dewpoint_2m_k",
    "pev": "potential_evaporation_m",
    "u10": "wind_u10_ms",
    "v10": "wind_v10_ms",
}
SUM_COLUMNS = ["total_precipitation_m", "runoff_m", "sub_surface_runoff_m", "potential_evaporation_m"]
MEAN_COLUMNS = ["soil_water_layer_1_m3m3", "temperature_2m_k", "dewpoint_2m_k", "wind_u10_ms", "wind_v10_ms"]


def write_csv(frame: pd.DataFrame, name: str) -> Path:
    path = OUT / name
    frame.to_csv(path, index=False)
    return path


def open_dataset_safely(path: Path) -> tuple[xr.Dataset | None, str | None]:
    try:
        return xr.open_dataset(path), None
    except Exception as exc:  # input integrity is recorded, never hidden
        return None, f"{type(exc).__name__}: {exc}"


def phase_a_glofas() -> pd.DataFrame:
    rows = []
    for path in sorted(GLOFAS_DIR.glob("*.nc")):
        ds, error = open_dataset_safely(path)
        if error:
            rows.append({"original_file": path.name, "status": "UNREADABLE", "error": error})
            continue
        try:
            time_name = "valid_time" if "valid_time" in ds.coords else "time"
            lat_name = "latitude" if "latitude" in ds.coords else "lat"
            lon_name = "longitude" if "longitude" in ds.coords else "lon"
            times = pd.to_datetime(ds[time_name].values)
            year = int(times.min().year)
            rows.append({
                "original_file": path.name,
                "confirmed_file": f"GLOFAS_Centre_{year}.nc",
                "status": "CONFIRMED_NO_RENAME_APPLIED",
                "start_date": times.min().date().isoformat(),
                "end_date": times.max().date().isoformat(),
                "records": len(times),
                "variables": ";".join(ds.data_vars),
                "latitude_min": float(ds[lat_name].min()), "latitude_max": float(ds[lat_name].max()),
                "longitude_min": float(ds[lon_name].min()), "longitude_max": float(ds[lon_name].max()),
            })
        finally:
            ds.close()
    inventory = pd.DataFrame(rows).sort_values("original_file")
    years = set(pd.to_datetime(inventory.loc[inventory.status.str.startswith("CONFIRMED"), "start_date"]).dt.year)
    gaps = sorted(set(range(2015, 2026)) - years)
    inventory["glofas_year_gaps_vs_2015_2025"] = ",".join(map(str, gaps))
    write_csv(inventory, "phase_a_glofas_inventory.csv")
    # Preserve raw UUID filenames: the confirmed identity is recorded rather than renaming source data.
    return inventory


def flatten_era5() -> tuple[pd.DataFrame, pd.DataFrame]:
    failures, frames = [], []
    for path in sorted(ERA5_DIR.glob("ERA5_Centre_*.nc")):
        ds, error = open_dataset_safely(path)
        if error:
            failures.append({"source_file": path.name, "status": "UNREADABLE", "error": error})
            continue
        try:
            required = {"valid_time", "latitude", "longitude", *ERA5_RENAME}
            absent = required - set(ds.variables)
            if absent:
                failures.append({"source_file": path.name, "status": "SCHEMA_MISMATCH", "error": f"missing={sorted(absent)}"})
                continue
            reduced = ds[list(ERA5_RENAME)].squeeze(drop=True).rename(ERA5_RENAME)
            frame = reduced.to_dataframe().reset_index().rename(columns={"valid_time": "datetime"})
            frame["datetime"] = pd.to_datetime(frame["datetime"])
            frame["source_file"] = path.name
            frames.append(frame)
        finally:
            ds.close()
    if not frames:
        raise RuntimeError("No readable ERA5 Centre files.")
    flat = pd.concat(frames, ignore_index=True)
    flat.to_parquet(OUT / "era5_centre_flat.parquet", index=False)
    daily = flat.assign(date=flat.datetime.dt.normalize()).groupby(
        ["date", "latitude", "longitude", "source_file"], as_index=False
    ).agg({**{column: "sum" for column in SUM_COLUMNS}, **{column: "mean" for column in MEAN_COLUMNS}})
    daily.to_parquet(OUT / "era5_centre_daily.parquet", index=False)
    failed = pd.DataFrame(failures, columns=["source_file", "status", "error"])
    write_csv(failed, "era5_unreadable_files.csv")
    return flat, daily


def flatten_glofas(inventory: pd.DataFrame) -> pd.DataFrame:
    frames = []
    confirmed = inventory[inventory.status.str.startswith("CONFIRMED")]
    for item in confirmed.itertuples(index=False):
        path = GLOFAS_DIR / item.original_file
        ds, error = open_dataset_safely(path)
        if error:
            continue
        try:
            time_name = "valid_time" if "valid_time" in ds.coords else "time"
            frame = ds[["avg_dis"]].to_dataframe().reset_index().rename(
                columns={time_name: "date", "avg_dis": "discharge_m3s"}
            )
            frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
            frame["source_file"] = item.original_file
            frame["confirmed_source_file"] = item.confirmed_file
            frames.append(frame)
        finally:
            ds.close()
    if not frames:
        raise RuntimeError("No readable GloFAS files.")
    flat = pd.concat(frames, ignore_index=True)
    flat.to_parquet(OUT / "glofas_centre_flat.parquet", index=False)
    return flat


def build_chirps_history() -> pd.DataFrame:
    frames = []
    raw_chunks = sorted(path for path in CHIRPS_DIR.glob("CHIRPS_*.csv") if re.fullmatch(r"CHIRPS_\d{4}_\d{4}\.csv", path.name))
    for path in raw_chunks:
        frame = pd.read_csv(path)
        frame["source_file"] = path.name
        frames.append(frame)
    chirps = pd.concat(frames, ignore_index=True)
    chirps.to_csv(CHIRPS_DIR / "CHIRPS_full_history.csv", index=False)
    write_csv(pd.DataFrame([{
        "rows": len(chirps), "date_min": chirps.date.min(), "date_max": chirps.date.max(),
        "unique_source_indices": chirps["system:index"].nunique(),
        "unique_name_coordinate_date": chirps.assign(_coord=chirps[".geo"]).drop_duplicates(["name", "_coord", "date"]).shape[0],
        "note": "Distinct localities sharing the name Ayéné are retained using coordinate-aware identity.",
    }]), "chirps_validation.csv")
    return chirps


def build_spatial_lookup(era5_daily: pd.DataFrame, glofas: pd.DataFrame) -> pd.DataFrame:
    gaz = pd.read_csv(BOUNDARY_DIR / "gazetteer_full_merged.csv").copy()
    gaz.insert(0, "locality_id", [f"CTR-LOC-{i:03d}" for i in range(1, len(gaz) + 1)])
    gaz["locality_key"] = gaz.apply(lambda r: f"{r['name']}|{r['lat']:.7f}|{r['lon']:.7f}", axis=1)
    era_points = era5_daily[["latitude", "longitude"]].drop_duplicates().reset_index(drop=True)
    glo_points = glofas[["latitude", "longitude"]].drop_duplicates().reset_index(drop=True)
    e_dist, e_idx = cKDTree(era_points[["latitude", "longitude"]]).query(gaz[["lat", "lon"]])
    g_dist, g_idx = cKDTree(glo_points[["latitude", "longitude"]]).query(gaz[["lat", "lon"]])
    gaz["era5_lat"] = era_points.iloc[e_idx].latitude.to_numpy(); gaz["era5_lon"] = era_points.iloc[e_idx].longitude.to_numpy()
    gaz["glofas_lat"] = glo_points.iloc[g_idx].latitude.to_numpy(); gaz["glofas_lon"] = glo_points.iloc[g_idx].longitude.to_numpy()
    gaz["era5_match_distance_deg"] = e_dist; gaz["glofas_match_distance_deg"] = g_dist
    gaz["era5_match_flag"] = np.where(gaz.era5_match_distance_deg <= .07, "WITHIN_TOLERANCE", "EXCEEDS_0.07_DEG")
    gaz["glofas_match_flag"] = np.where(gaz.glofas_match_distance_deg <= .03, "WITHIN_TOLERANCE", "EXCEEDS_0.03_DEG")
    points = gpd.GeoDataFrame(gaz, geometry=gpd.points_from_xy(gaz.lon, gaz.lat), crs="EPSG:4326")
    basins = gpd.read_file(HYBASINS, bbox=(10.5, 3.5, 12.5, 5.0))
    joined = gpd.sjoin(points, basins[["HYBAS_ID", "geometry"]], how="left", predicate="within")
    joined = joined.drop(columns=["geometry", "index_right"], errors="ignore")
    joined = joined.drop_duplicates("locality_id")
    joined = pd.DataFrame(joined)
    if not LOCALITY_DEM.exists():
        raise FileNotFoundError(f"Required GEE locality DEM table not found: {LOCALITY_DEM}")
    dem = pd.read_csv(LOCALITY_DEM)
    required_dem = {"name", "elevation_m", "slope_deg", ".geo"}
    missing_dem = required_dem - set(dem.columns)
    if missing_dem:
        raise ValueError(f"GEE locality DEM table missing columns: {sorted(missing_dem)}")
    coords = dem[".geo"].map(json.loads).map(lambda geo: geo["coordinates"])
    dem["lon"] = coords.map(lambda value: float(value[0])); dem["lat"] = coords.map(lambda value: float(value[1]))
    if dem[["elevation_m", "slope_deg"]].isna().any().any():
        problem = dem.loc[dem[["elevation_m", "slope_deg"]].isna().any(axis=1), ["name", "lat", "lon", "elevation_m", "slope_deg"]]
        raise ValueError(f"GEE locality DEM has missing samples: {problem.to_dict('records')}")
    if dem.duplicated(["name", "lat", "lon"]).any():
        raise ValueError("GEE locality DEM contains duplicate name/coordinate identities.")
    # GEE export and the merged gazetteer use the same named localities but
    # retain coordinates at slightly different precisions. Pair within each
    # name by the nearest coordinate; this also safely distinguishes Ayéné's
    # two separately geocoded localities.
    samples = []
    for record in joined.itertuples(index=False):
        choices = dem[dem.name.eq(record.name)].copy()
        if choices.empty:
            samples.append((np.nan, np.nan, np.nan))
            continue
        choices["distance_deg"] = np.hypot(choices.lat - record.lat, choices.lon - record.lon)
        nearest = choices.loc[choices.distance_deg.idxmin()]
        samples.append((nearest.elevation_m, nearest.slope_deg, nearest.distance_deg))
    joined[["elevation_m", "slope_deg", "dem_match_distance_deg"]] = pd.DataFrame(samples, index=joined.index)
    if joined[["elevation_m", "slope_deg"]].isna().any().any():
        problem = joined.loc[joined[["elevation_m", "slope_deg"]].isna().any(axis=1), ["locality_id", "name", "lat", "lon"]]
        raise ValueError(f"Gazetteer localities not covered by GEE locality DEM: {problem.to_dict('records')}")
    joined["dem_status"] = "COMPLETE_GEE_COPERNICUS_DEM_GLO30_LOCALITY_SAMPLE"
    write_csv(joined, "locality_spatial_lookup.csv")
    return joined


def build_feature_table(lookup: pd.DataFrame, era5_daily: pd.DataFrame, glofas: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range("2015-01-01", "2025-12-31", freq="D")
    panel = lookup.assign(_join=1).merge(pd.DataFrame({"date": dates, "_join": 1}), on="_join").drop(columns="_join")
    era = era5_daily.rename(columns={"latitude": "era5_lat", "longitude": "era5_lon", "source_file": "era5_source_file"})
    panel = panel.merge(era, on=["date", "era5_lat", "era5_lon"], how="left")
    glo = glofas.rename(columns={"latitude": "glofas_lat", "longitude": "glofas_lon", "source_file": "glofas_source_file"})
    panel = panel.merge(glo[["date", "glofas_lat", "glofas_lon", "discharge_m3s", "glofas_source_file", "confirmed_source_file"]], on=["date", "glofas_lat", "glofas_lon"], how="left")
    panel["era5_available"] = panel.total_precipitation_m.notna()
    panel["glofas_available"] = panel.discharge_m3s.notna()
    panel = panel.sort_values(["locality_id", "date"])
    for days in (1, 3, 7, 14):
        panel[f"rainfall_{days}d_m"] = panel.groupby("locality_id", group_keys=False)["total_precipitation_m"].transform(
            lambda series: series.rolling(days, min_periods=days).sum()
        )
    panel["month"] = panel.date.dt.month
    monthly_climatology = panel.groupby(["locality_id", "month"])["rainfall_7d_m"].transform("mean")
    panel["rainfall_anomaly_m"] = panel["rainfall_7d_m"] - monthly_climatology
    panel["soil_saturation"] = panel["soil_water_layer_1_m3m3"]
    for lag in (1, 3, 7):
        panel[f"discharge_lag{lag}_m3s"] = panel.groupby("locality_id")["discharge_m3s"].shift(lag)
    panel["data_completeness_flag"] = np.select(
        [panel.era5_available & panel.glofas_available, panel.era5_available, panel.glofas_available],
        ["COMPLETE", "MISSING_GLOFAS", "MISSING_ERA5"], default="MISSING_ERA5_AND_GLOFAS"
    )
    columns = [
        "locality_id", "locality_key", "name", "division", "region", "admin_level", "lat", "lon", "date",
        "era5_lat", "era5_lon", "glofas_lat", "glofas_lon", "era5_match_distance_deg", "glofas_match_distance_deg",
        "HYBAS_ID", "elevation_m", "slope_deg", "dem_status", "total_precipitation_m", "rainfall_1d_m", "rainfall_3d_m",
        "rainfall_7d_m", "rainfall_14d_m", "rainfall_anomaly_m", "soil_saturation", "discharge_m3s",
        "discharge_lag1_m3s", "discharge_lag3_m3s", "discharge_lag7_m3s", "month", "era5_available", "glofas_available",
        "data_completeness_flag", "era5_source_file", "glofas_source_file", "confirmed_source_file",
    ]
    features = panel[columns].rename(columns={"name": "locality_name", "HYBAS_ID": "basin_id"})
    features.to_parquet(OUT / "centre_ml_feature_table_unlabelled.parquet", index=False)
    return features


def build_event_audit() -> pd.DataFrame:
    # A separately reviewed Centre evidence audit takes precedence over the
    # old national extractor, whose four apparent Centre matches were known
    # false positives.  Never overwrite reviewed findings on re-runs.
    existing = OUT / "canonical_flood_events.csv"
    evidence_audit = OUT / "centre_evidence_verification_audit.csv"
    if existing.exists() and evidence_audit.exists():
        return pd.read_csv(existing)
    events = pd.read_csv(MASTER_EVENTS)
    candidates = events[events.region.eq("Centre")].copy()
    audit = pd.DataFrame({
        "source_event_id": candidates.event_id,
        "source_filename": candidates.filename,
        "source_report_title": candidates.report_title,
        "source_text": candidates.evidence_sentence,
        "decision": "GENERAL_FLOOD_REFERENCE_NOT_CENTRE_EVENT",
        "reason": "No verified Centre-region date, locality, or coordinates. Text refers to Far North locations or uses the word centre generically.",
        "canonical_event_id": pd.NA,
    })
    write_csv(audit, "centre_event_catalogue_audit.csv")
    canonical = pd.DataFrame(columns=[
        "canonical_event_id", "event_status", "event_start_date", "event_end_date", "locality_name", "division", "region",
        "latitude", "longitude", "source_document_title", "source_document_url", "source_event_id", "evidence_summary",
    ])
    write_csv(canonical, "canonical_flood_events.csv")
    return canonical


def build_knowledge_base(lookup: pd.DataFrame, features: pd.DataFrame, canonical: pd.DataFrame) -> pd.DataFrame:
    latest = features[features.era5_available].sort_values("date").groupby("locality_id", as_index=False).tail(1)
    base = lookup.merge(latest[[
        "locality_id", "date", "rainfall_7d_m", "soil_saturation", "discharge_m3s", "elevation_m", "slope_deg", "basin_id",
        "era5_match_distance_deg", "glofas_match_distance_deg", "data_completeness_flag",
    ]], on="locality_id", how="left", suffixes=("", "_latest"))
    rows = []
    for record in base.itertuples(index=False):
        grid_matched = record.era5_match_distance_deg <= .07 and record.glofas_match_distance_deg <= .03
        locality_events = canonical[
            canonical.get("event_status", pd.Series(dtype=str)).eq("VERIFIED_FLOOD_EVENT")
            & canonical.get("locality_name", pd.Series(dtype=str)).eq(record.name)
        ]
        confidence = "HIGH" if grid_matched and not locality_events.empty else ("MEDIUM" if grid_matched else "LOW")
        features_json = {
            "as_of_date": record.date.isoformat() if pd.notna(record.date) else None,
            "rainfall_7d_m": record.rainfall_7d_m, "soil_saturation": record.soil_saturation,
            "discharge_m3s": record.discharge_m3s, "elevation_m": record.elevation_m,
            "slope_deg": record.slope_deg, "basin_id": record.basin_id,
            "data_completeness_flag": record.data_completeness_flag,
        }
        if locality_events.empty:
            summary = "No verified flood events were found for this locality in the available Centre-region canonical catalogue; this does not imply the locality is safe."
            citations = "[]"
        else:
            years = sorted(pd.to_datetime(locality_events.event_start_date).dt.year.astype(str).unique())
            summary = f"{len(locality_events)} verified flood event(s) recorded here since 2015 ({', '.join(years)})."
            citations = json.dumps(locality_events[["source_document_title", "source_document_url", "canonical_event_id"]].to_dict("records"), ensure_ascii=False)
        rows.append({
            "locality_id": record.locality_id, "locality_name": record.name, "division": record.division,
            "region": record.region, "admin_level": record.admin_level,
            "current_risk_features": json.dumps(features_json, default=lambda value: None),
            "historical_flood_summary": summary, "source_citations": citations, "data_confidence": confidence,
        })
    knowledge = pd.DataFrame(rows)
    write_csv(knowledge, "assistant_knowledge_base.csv")
    (OUT / "assistant_knowledge_base.json").write_text(knowledge.to_json(orient="records", indent=2, force_ascii=False), encoding="utf-8")
    return knowledge


def write_final_report(era5_flat: pd.DataFrame, era5_daily: pd.DataFrame, glofas: pd.DataFrame, lookup: pd.DataFrame, features: pd.DataFrame, canonical: pd.DataFrame, knowledge: pd.DataFrame) -> None:
    status = "READY_FOR_LABEL_AND_TRAINING" if len(canonical) >= 2 else "BLOCKED_INSUFFICIENT_INDEPENDENT_POSITIVE_EPISODES"
    report = f"""# Centre consolidation validation report

## Completed outputs

- ERA5 flat rows: {len(era5_flat):,}; daily rows: {len(era5_daily):,}; unique grid cells: {era5_daily[['latitude', 'longitude']].drop_duplicates().shape[0]}.
- GloFAS flat rows: {len(glofas):,}; unique grid cells: {glofas[['latitude', 'longitude']].drop_duplicates().shape[0]}.
- Gazetteer localities: {len(lookup):,}; ERA5 matches above 0.07°: {(lookup.era5_match_distance_deg > .07).sum()}; GloFAS matches above 0.03°: {(lookup.glofas_match_distance_deg > .03).sum()}.
- Unlabelled locality-day feature rows: {len(features):,}.
- Canonical verified Centre events: {len(canonical):,}.
- Assistant knowledge records: {len(knowledge):,}.

## Phase E/F decision

**{status}**. No `flood_label`, negative sample, chronological train/test split, classifier, or performance metric was created.

## Required next input for model training

Provide enough independent Centre-only canonical events for a chronological split with a positive event in both train and test. Each record must have a verified date/window, locality or defensible footprint, coordinates, and source document citation.

## Known coverage flags retained in the outputs

- ERA5 readability outcomes are listed in `era5_unreadable_files.csv`.
- GloFAS year coverage is recorded in `phase_a_glofas_inventory.csv`.
- Elevation and slope were matched from the complete GEE locality sample table, not from the broken OpenTopography GeoTIFFs.
- Assistant historical summaries only cite canonical verified events.
"""
    (OUT / "phase_b_to_g_validation_report.md").write_text(report, encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    glo_inventory = phase_a_glofas()
    era5_flat, era5_daily = flatten_era5()
    glofas = flatten_glofas(glo_inventory)
    build_chirps_history()
    lookup = build_spatial_lookup(era5_daily, glofas)
    features = build_feature_table(lookup, era5_daily, glofas)
    canonical = build_event_audit()
    knowledge = build_knowledge_base(lookup, features, canonical)
    write_final_report(era5_flat, era5_daily, glofas, lookup, features, canonical, knowledge)
    print(f"Completed safe Centre consolidation outputs in {OUT}")


if __name__ == "__main__":
    main()
