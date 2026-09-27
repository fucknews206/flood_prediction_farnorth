# Implementation Plan — Cameroon Flood Intelligence Migration (Revised)

## Summary of Revisions

Three issues from the first plan have been corrected before any code is written.
The sections below show the updated design for each fix, followed by the full
unchanged scope of work.

---

## FIX 1 — Unit Mismatch: Rename all imperial hydrology fields to metric

### What is wrong
The original plan carried over US customary units from the SQLite schema:
- `basin_size_sqmi` (square miles)
- `current_streamflow_cfs` (cubic feet per second)
- `flood_stage_cfs` (cubic feet per second)
- `trend_rate_cfs_per_hour`

These appear in **every layer** of the stack. A complete audit found them in:

| Location | Occurrences |
|---|---|
| `db.py` SQL schema & queries | `current_streamflow_cfs`, `flood_stage_cfs`, `basin_size_sqmi`, `trend_rate_cfs_per_hour` |
| `data_sources.py` | `StreamflowData.streamflow_cfs`, `calculate_risk_level(streamflow_cfs, flood_stage_cfs)`, `calculate_trend → rate_cfs_per_hour`, log strings "CFS" |
| `agents/risk_analyzer.py` | `basin_size_sqmi` weight, `current_streamflow_cfs`, `flood_stage_cfs`, `trend_rate_cfs_per_hour` |
| `agents/predictor.py` | `current_streamflow_cfs`, `trend_rate_cfs_per_hour`, `flood_stage_cfs`, `flow_cfs` keys |
| `agents/emergency_responder.py` | `basin_size_sqmi` population estimate |
| `agents/h2ogpte_agent.py` | `current_streamflow_cfs`, `trend_rate_cfs_per_hour` key list |
| `agents/mcp_unified_flood_server.py` | `usgs_flow_cfs`, `flood_stage_ft`, threshold constants (50 000 / 20 000 / 10 000 CFS) |
| `ui/src/lib/api.ts` — `Watershed` interface | `basin_size_sqmi`, `current_streamflow_cfs`, `flood_stage_cfs`, `trend_rate_cfs_per_hour` |
| `ui/src/components/GlobalWatershedMap.tsx` | Popup label "Streamflow: {x} CFS" |
| `ui/src/components/UnifiedDashboard.tsx` | Popup/tooltip strings referencing CFS, agent insight descriptions mentioning "CFS/hour" |

### Renamed fields (new names used everywhere)

| Old name | New name | Unit |
|---|---|---|
| `basin_size_sqmi` | `basin_size_sqkm` | km² |
| `current_streamflow_cfs` | `current_streamflow_cms` | m³/s |
| `flood_stage_cfs` | `flood_stage_cms` | m³/s |
| `trend_rate_cfs_per_hour` | `trend_rate_cms_per_hour` | m³/s per hour |
| `streamflow_cfs` (dataclass) | `streamflow_cms` | m³/s |
| `drainage_area_sqmi` | `drainage_area_sqkm` | km² |

### Conversion constants applied at ingestion boundary only
Any value arriving from an existing US-unit source (USGS, legacy DB rows) is
converted once at the point of ingestion:
- 1 CFS = 0.0283168 m³/s
- 1 sq mi = 2.58999 km²

All internal logic, DB columns, API responses, and UI labels use metric from
that point forward. No dual-unit display or conversion labels will remain.

### Risk-score thresholds updated to metric equivalents
`calculate_risk_level` thresholds (previously 500 / 1000 CFS) replaced with
metric equivalents (~14 / 28 m³/s). MCP server CFS constants (50 000 / 20 000
/ 10 000) similarly replaced with ~1 416 / 566 / 283 m³/s.

---

## FIX 2 — GlobalWatershedMap: fetch Cameroon PostGIS endpoints, not US data

### What is wrong
The component's `MapController` falls back to `center=[31.0, -100.0]` (Texas)
and renders markers from whatever `watersheds` prop it receives — which in
`UnifiedDashboard` comes from `dashboardApi.getDashboardData()` returning the
old `watersheds` table rows. The component has no GeoJSON layer at all; it
only plots point markers. No Cameroon boundary or basin polygons are shown.

### What changes

**`GlobalWatershedMap.tsx` — complete replacement of data source & rendering**

The component gains two new data-fetching calls (added as optional props with
reasonable defaults so existing usage still compiles):

```
GET /api/geo/regions          → GeoJSON FeatureCollection of 10 Region polygons
GET /api/geo/basins           → GeoJSON FeatureCollection of 32 River Basin polygons
```

Both endpoints are served by the new PostGIS layer built in this migration.
The component renders:
- A **Region boundary layer** (thin grey outline, no fill) using `GeoJSON` from
  `react-leaflet`.
- A **Basin layer** (semi-transparent fill, coloured by `current_risk_level`)
  using `GeoJSON`, with a popup showing basin name, risk score, streamflow
  (m³/s), and the discharge-unavailable flag from Fix 3.
- **Point markers** for `CommunityReport` locations (from
  `GET /api/community-reports/recent`).

The hardcoded Texas fallback `[31.0, -100.0]` is replaced with Cameroon
`[7.37, 12.35]`, zoom `6`. The `'TX'` default in `regionsApi.getCurrentRegion`
is changed to `'CM'`.

**New backend endpoints added in `server.py`:**
- `GET /api/geo/regions` — serves admin-1 boundaries as GeoJSON (from
  PostGIS `regions` table).
- `GET /api/geo/basins` — serves basin polygons with current risk attributes
  as GeoJSON (from PostGIS `river_basins` table).

---

## FIX 3 — No fake discharge data when GloFAS is unavailable

### What is wrong
The original plan said "placeholder required for user API key" for GloFAS but
did not specify what happens at runtime. Without an explicit rule, the risk
scorer would silently use zero or a made-up value as if it were real discharge.

### Design: explicit `discharge_status` field

Every `RiverBasin` row and every API response object for a basin now carries:

```python
discharge_cms: Optional[float]          # None when unavailable
discharge_status: str                   # "available" | "unavailable" | "stale"
discharge_source: str                   # "glofas" | "openmeteo_flood" | "none"
```

**Risk score calculation** (`calculate_risk_level` in `data_sources.py`):

```
risk_score = rainfall_component(weight=0.6)
           + community_report_component(weight=0.4)
           [+ discharge_component(weight=0.5, only when discharge_status=="available")]

When discharge is unavailable:
  - weights renormalise over the available inputs only
  - result is flagged: data_completeness = "partial"
  - risk_score is capped at 7.0 (cannot reach CRITICAL without discharge data)
```

**API response shape** for `/api/dashboard` and `/api/geo/basins`:
```json
{
  "risk_score": 4.2,
  "data_completeness": "partial",
  "missing_inputs": ["discharge"],
  "discharge_status": "unavailable"
}
```

**Frontend** (`UnifiedDashboard.tsx` and `GlobalWatershedMap.tsx`):
- When `discharge_status !== "available"`, show a yellow badge
  **"⚠ Discharge data unavailable"** in the basin popup and in the basin's
  row in the Watersheds table.
- When `data_completeness === "partial"`, the risk score is displayed as
  e.g. **"4.2 / 10 (partial)"** — never as if it is a complete reading.
- The dashboard summary card shows a persistent notice:
  **"GloFAS discharge data not configured — risk scores are based on rainfall
  and community reports only."**

**GloFAS integration hook** (`server.py`):
```python
GLOFAS_API_KEY = settings.glofas_api_key  # None by default
if GLOFAS_API_KEY:
    discharge = await fetch_glofas(basin, GLOFAS_API_KEY)
    discharge_status = "available"
else:
    discharge = None
    discharge_status = "unavailable"
```
No fabricated numbers. No silent zeroes.

---

## Full Proposed Changes (original scope + fixes applied)

### Environment

#### [MODIFY] [.env](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/.env)
- Add `APP_DATABASE_URL=postgresql://postgres:1234@localhost/flood_prediction`
- Add `APP_GLOFAS_API_KEY=` (empty — triggers unavailable path from Fix 3)
- `.env` is confirmed gitignored at lines 122 and 172 of `.gitignore` ✓

#### [MODIFY] [settings.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/settings.py)
- Add `glofas_api_key: Optional[str] = None`

---

### Database Layer

#### [NEW] [models.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/models.py)
SQLAlchemy + GeoAlchemy2 ORM models (metric units throughout):
- `Region` — id, name, pcode, geom (MultiPolygon/4326)
- `Department` — id, name, pcode, region_id FK, geom
- `Arrondissement` — id, name, pcode, department_id FK, geom
- `RiverBasin` — id, name, hybas_id, geom, **`basin_size_sqkm`**,
  **`current_streamflow_cms`**, **`flood_stage_cms`**,
  **`trend_rate_cms_per_hour`**, risk_score, current_risk_level,
  **`discharge_status`**, **`discharge_cms`**, **`data_completeness`**,
  data_source, data_quality, last_api_update, last_updated
- `CommunityReport` — id, reporter_name, details, location_lat, location_lng,
  region_id, department_id, arrondissement_id, basin_id, risk_level, reported_at
- `Alert`, `RiskTrend`, `SystemMetric`, `UserSetting`, `Item`, `Cache`

#### [MODIFY] [db.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/db.py)
- Replace SQLite connection logic with psycopg2/SQLAlchemy to PostgreSQL
- Translate `?` placeholders to `%s`
- Redirect `watersheds` queries → `river_basins` (column aliases maintain API compat)
- Add `resolve_location_to_entities(lat, lon)` using `ST_Contains`
- Add `init_postgis()` to run `CREATE EXTENSION IF NOT EXISTS postgis`

---

### Data Ingestion

#### [NEW] [seed_cameroon.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/seed_cameroon.py)
- Load `cmr_admin1.shp` → Region (10 rows), `adm1_ref_n` as name, `adm1_pcode` as pcode
- Load `cmr_admin2.shp` → Department (58 rows), linked to Region via `adm1_pcode`
- Load `cmr_admin3.shp` → Arrondissement (360 rows), linked to Department via `adm2_pcode`
- Load `cameroon_basins.geojson` → RiverBasin (32 rows), use `HYBAS_ID` as `hybas_id`
- All geometry inserted as WKT with `ST_GeomFromText(..., 4326)`

#### [MODIFY] [data_sources.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/data_sources.py)
- Remove `USGSWaterServices`, `USGSSite`, `StreamflowData` (US-specific classes)
- Rename dataclass field `streamflow_cfs` → `streamflow_cms`, `drainage_area_sqmi` → `drainage_area_sqkm`
- Replace `REGION_CONFIG` with Cameroon's 10 regions and basin centroids
- Rewrite `calculate_risk_level(streamflow_cms, flood_stage_cms)` with metric thresholds
- Rewrite `calculate_trend` → returns `trend_rate_cms_per_hour`
- Add `calculate_risk_with_partial_data(rainfall, community_count, discharge_cms, discharge_status)` implementing Fix 3 partial-weight logic

#### [MODIFY] [agents/data_collector.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/agents/data_collector.py)
- Remove `collect_usgs_data`, `collect_noaa_flood_data`, `_collect_noaa_tides_data`
- Remove Texas hardcoded locations from `collect_weather_data` and `collect_flood_forecast_data`
- Add `collect_openmeteo_rainfall(basins)` — calls Open-Meteo for each basin centroid, metric units
- Add `collect_glofas_discharge(basins)` — returns `discharge_status="unavailable"` when key is absent
- Update `_check_api_status` — replace USGS/NOAA URLs with Open-Meteo + GloFAS health checks
- Rename all internal `_cfs`/`_sqmi` variables

#### [MODIFY] [agents/risk_analyzer.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/agents/risk_analyzer.py)
- `_calculate_overall_risk`: weight key `basin_size_sqmi` → `basin_size_sqkm`
- `_check_threshold_breaches`: keys `current_streamflow_cfs`/`flood_stage_cfs` → metric equivalents
- `_detect_pattern_anomalies`: threshold `current_flow < 100` (CFS) → `< 2.8` (m³/s)
- `_detect_rapid_risk_change`: threshold `trend_rate > 100` CFS → `> 2.8` m³/s

#### [MODIFY] [agents/predictor.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/agents/predictor.py)
- All `_cfs` key lookups → `_cms`

#### [MODIFY] [agents/emergency_responder.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/agents/emergency_responder.py)
- `basin_size_sqmi` → `basin_size_sqkm`; population density estimate stays proportional

#### [MODIFY] [agents/mcp_unified_flood_server.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/agents/mcp_unified_flood_server.py)
- Rename params `usgs_flow_cfs` → `flow_cms`, `flood_stage_ft` → `flood_stage_m`
- Replace CFS thresholds (50000/20000/10000) with m³/s equivalents (1416/566/283)
- Remove `gage height in feet` references

#### [MODIFY] [agents/h2ogpte_agent.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/agents/h2ogpte_agent.py)
- Key list `["current_streamflow_cfs", ...]` → `["current_streamflow_cms", ...]`

---

### Server / API

#### [MODIFY] [server.py](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/core/src/flood_prediction/server.py)
- Background ingestion tasks: call `collect_openmeteo_rainfall` + `collect_glofas_discharge`
- Add `GET /api/geo/regions` — serves Region polygons as GeoJSON (Fix 2)
- Add `GET /api/geo/basins` — serves RiverBasin polygons with risk + discharge_status (Fix 2 + 3)
- Add `POST /api/community-reports` — accepts lat/lon + text, runs `resolve_location_to_entities`, stores CommunityReport
- Add `GET /api/community-reports/recent` — last 50 reports with coordinates
- Remove NOAA-alert-refresh endpoints or stub them to return `{"status": "not_applicable", "region": "Cameroon"}`
- All JSON responses: rename CFS/sqmi fields to metric names (Fix 1)

---

### Frontend

#### [MODIFY] [api.ts](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/ui/src/lib/api.ts)
- `Watershed` interface: rename `basin_size_sqmi` → `basin_size_sqkm`, `current_streamflow_cfs` → `current_streamflow_cms`, `flood_stage_cfs` → `flood_stage_cms`, `trend_rate_cfs_per_hour` → `trend_rate_cms_per_hour`
- Add `discharge_status`, `discharge_cms`, `data_completeness` fields
- `regionsApi.getCurrentRegion()` default: `'TX'` → `'CM'`
- Add `geoApi.getRegions()` → `GET /api/geo/regions`
- Add `geoApi.getBasins()` → `GET /api/geo/basins`
- Add `communityReportsApi.submit()` and `communityReportsApi.getRecent()`

#### [MODIFY] [GlobalWatershedMap.tsx](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/ui/src/components/GlobalWatershedMap.tsx)
- Default center `[31.0, -100.0]` → `[7.37, 12.35]`, zoom `6 → 6` (unchanged)
- Add `GeoJSON` layer for region boundaries from `GET /api/geo/regions`
- Add `GeoJSON` layer for basin polygons from `GET /api/geo/basins`, coloured by risk level
- Basin popup shows: name, risk score with `(partial)` suffix if `data_completeness==="partial"`, streamflow in m³/s, ⚠ badge if `discharge_status !== "available"`
- Community report markers from `GET /api/community-reports/recent`
- Remove any remaining USGS/Texas URL or coordinate references

#### [MODIFY] [UnifiedDashboard.tsx](file:///home/ongou/Desktop/projects/end-of%20-year-defence/h2oai-flood-intelligence-agent-main/ui/src/components/UnifiedDashboard.tsx)
- All "CFS" label strings → "m³/s"
- Agent insight description strings: "CFS/hour" → "m³/s per hour", "sq.mi" → "km²"
- USGS/NOAA URL references in `getAgentInsightDescription` → Open-Meteo / GloFAS URLs
- Dashboard summary: persistent notice when any basin has `discharge_status="unavailable"`
- Risk score display: append `(partial)` when `data_completeness === "partial"`

---

## Verification Plan

### Step 1 — PostGIS & connection
```bash
PGPASSWORD=1234 psql -h localhost -U postgres -d flood_prediction \
  -c "SELECT PostGIS_Full_Version();"
```

### Step 2 — Seed counts
```bash
core/venv/bin/python -m flood_prediction.seed_cameroon
```
Expected output:
```
Regions:        10
Departments:    58
Arrondissements: 360
River Basins:   32
```

### Step 3 — Spatial resolution (Far North / Maga)
```python
result = db.resolve_location_to_entities(lat=10.85, lon=14.93)
# Expected:
# region: "Far North" (CM010)
# department: "Mayo-Danay" (CM010004)
# arrondissement: "Maga" (CM010004003)
```

### Step 4 — Metric fields in API response
```bash
curl http://localhost:8000/api/geo/basins | python -m json.tool | grep -E "sqkm|cms|discharge_status"
# Must show basin_size_sqkm, current_streamflow_cms, discharge_status: "unavailable"
# Must NOT show any _cfs, _sqmi, or _ft field names
```

### Step 5 — Partial-risk flag visible in UI
Open dashboard → any basin popup → confirm "⚠ Discharge data unavailable" badge
and risk score displayed as "X.X / 10 (partial)".
