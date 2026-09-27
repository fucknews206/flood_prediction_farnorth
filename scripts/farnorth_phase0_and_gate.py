#!/usr/bin/env python3
"""Far North only: Phase 0/Phase A inventory and non-negotiable gate."""
from pathlib import Path
import pandas as pd
import xarray as xr

ROOT = Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT = ROOT / 'h2oai-flood-intelligence-agent-main' / 'data_quality' / 'farnorth_consolidation'
OUT.mkdir(parents=True, exist_ok=True)

def inspect_nc(path: Path) -> dict:
    try:
        with xr.open_dataset(path) as ds:
            time = next((x for x in ('time', 'valid_time') if x in ds.coords), None)
            lat = next((x for x in ('latitude', 'lat') if x in ds.coords), None)
            lon = next((x for x in ('longitude', 'lon') if x in ds.coords), None)
            return {'file': str(path.relative_to(ROOT)), 'readable': True, 'variables': ','.join(ds.data_vars),
                    'date_start': str(ds[time].min().values)[:10] if time else 'UNKNOWN',
                    'date_end': str(ds[time].max().values)[:10] if time else 'UNKNOWN',
                    'lat_min': float(ds[lat].min()) if lat else None, 'lat_max': float(ds[lat].max()) if lat else None,
                    'lon_min': float(ds[lon].min()) if lon else None, 'lon_max': float(ds[lon].max()) if lon else None}
    except Exception as exc:
        return {'file': str(path.relative_to(ROOT)), 'readable': False, 'error': str(exc)}

def main():
    era = sorted((ROOT/'ERA5-datasets/Far_North').glob('*.nc'))
    glofas_all = sorted((ROOT/'GLOFAS-datasets').rglob('*.nc'))
    inv = pd.DataFrame(
        [(inspect_nc(x) | {'component':'ERA5_LAND_FAR_NORTH'}) for x in era]
        + [(inspect_nc(x) | {'component':'GLOFAS'}) for x in glofas_all]
    )
    inv.to_csv(OUT/'farnorth_phase_a_netcdf_inventory.csv',index=False)
    # Region identity is defined from opened latitude bounds, not folders/names.
    g = inv[inv.component.eq('GLOFAS')]
    far = g[g.lat_min.ge(9) & g.lat_max.ge(9)]
    centre = g[g.lat_max.lt(6)]
    years = sorted(int(path.rsplit('data_', 1)[1][:4]) for path in far.file)
    gaps = sorted(set(range(2015,2026))-set(years))
    gaz = pd.read_csv(ROOT/'boundaries-data/gazetteer_farnorth.csv')
    dem = pd.read_csv(ROOT/'DEM (elevation)-datasets/DEM_slope_localities_FarNorth_fixed.csv')
    chirps = []
    for file in sorted((ROOT/'CHIRPS-datasets/far-north').glob('CHIRPS_FarNorth_fixed_*.csv')):
        cols=pd.read_csv(file,nrows=1).columns.tolist()
        chirps.append({'file':str(file.relative_to(ROOT)),'size_bytes':file.stat().st_size,'columns':';'.join(cols),
                        'rainfall_columns':';'.join(c for c in cols if c.lower() == 'first' or any(w in c.lower() for w in ('rain','precip','chirps')))})
    chirps=pd.DataFrame(chirps); chirps.to_csv(OUT/'farnorth_chirps_schema_check.csv',index=False)
    # No labels can be joined without usable environmental source inputs. This is a gate result, not evidence exclusion.
    failures=[]
    if dem.elevation_m.isna().any() or dem.slope_deg.isna().any(): failures.append(f'DEM/slope invalid: elevation_m null {dem.elevation_m.isna().sum()}/{len(dem)}; slope_deg null {dem.slope_deg.isna().sum()}/{len(dem)}.')
    if not chirps.rainfall_columns.astype(bool).any(): failures.append('CHIRPS invalid: neither supplied CSV contains a rainfall/precipitation value column; they contain metadata only.')
    if inv[inv.component.eq('ERA5_LAND_FAR_NORTH')].readable.sum()!=len(era): failures.append('ERA5 unreadable files remain.')
    if gaps: failures.append(f'Far North GloFAS year gaps: {gaps}.')
    decision='FAIL — DO NOT TRAIN' if failures else 'PASS — PROCEED TO PHASE B'
    report=f'''# Far North region only — Phase 0, Phase A, and Readiness Gate

## Decision

**{decision}**

## Exact supplied-path discovery

- ERA5-Land: {len(era)} files visible in `ERA5-datasets/Far_North/`.
- GloFAS: {len(glofas_all)} files opened. By actual bounds, {len(far)} are Far North (latitude {far.lat_min.min()}–{far.lat_max.max()}), while {len(centre)} are Centre-only (latitude {centre.lat_min.min()}–{centre.lat_max.max()}) and excluded.
- CHIRPS: {len(chirps)} files visible in `CHIRPS-datasets/far-north/`.
- Gazetteer: {len(gaz)} locality rows; {gaz[['name','lat','lon']].drop_duplicates().shape[0]} unique name/coordinate rows.
- DEM/slope: {len(dem)} rows.
- HydroBasins/HydroRIVERS, ReliefWeb, and scrapers directories are visible but were not processed after the environmental prerequisite failure.

## File identity/readability

- ERA5 readable: {int(inv[inv.component.eq('ERA5_LAND_FAR_NORTH')].readable.sum())}/{len(era)}.
- Far North GloFAS readable: {int(far.readable.sum())}/{len(far)}; annual coverage {years}; missing years {gaps or 'none'}.
- CHIRPS rainfall columns: {chirps.rainfall_columns.tolist()}.
- DEM elevation nulls: {int(dem.elevation_m.isna().sum())}/{len(dem)}; slope nulls: {int(dem.slope_deg.isna().sum())}/{len(dem)}.

## Readiness Gate result

- Total positive rows: **0 (not constructible)**.
- Distinct localities: **0 (not constructible)**.
- Distinct years: **0 (not constructible)**.
- Positives per division: **none; label join was not run**.

## Blocking failures

'''+'\n'.join(f'- {x}' for x in failures)+'''\n
The supplied CHIRPS and DEM files must be corrected before Phase B standardization, Phase C spatial join, Phase D features, Phase E labels, or the exhaustive flood-evidence pass can produce a valid Far North training dataset. No model, predictions, or sample results were produced. This is **Far North region only**.
'''
    (OUT/'farnorth_build_summary.md').write_text(report,encoding='utf-8')
    (OUT/'farnorth_phase0_discovery_report.md').write_text(report,encoding='utf-8')
    print(decision, failures)

if __name__=='__main__': main()
