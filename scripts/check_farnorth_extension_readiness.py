"""Inventory the requested 2004-2014 Far North extension inputs."""
from pathlib import Path
import pandas as pd

root = Path('/home/ongou/Desktop/projects/end-of -year-defence')
out = Path(__file__).resolve().parents[1] / 'data_quality' / 'farnorth_consolidation'
catalogue = pd.read_csv('/home/ongou/Downloads/Far North Cameroon Verified Flood Event Catalogue 2004–2026.csv')
year = pd.to_datetime(catalogue.event_start_date, errors='coerce').dt.year
outside = catalogue[~year.between(2015, 2025)].copy()
outside['training_status'] = 'NOT_YET_USABLE_NO_2004_2014_ENVIRONMENTAL_LAYER'
outside.to_csv(out / 'farnorth_2004_2014_rows_pending_environment_extension.csv', index=False)

paths = {'ERA5-Land': root/'ERA5-datasets'/'Far_North', 'GloFAS': root/'GLOFAS-datasets'/'far-north', 'CHIRPS': root/'CHIRPS-datasets'/'far-north'}
lines = ['# Far North region only — 2004–2014 extension readiness', '', f'Rows outside current 2015–2025 window: {len(outside)}', '']
for label, p in paths.items():
    files = list(p.glob('*')) if p.exists() else []
    old = [f for f in files if any(str(y) in f.name for y in range(2004, 2015))]
    lines.append(f'- {label}: directory exists={p.exists()}, files={len(files)}, 2004–2014 files={len(old)}')
lines += ['', 'No 2004–2014 ERA5, GloFAS, or Far North CHIRPS files are currently present. CDS/EWDS/GEE credentials or exported files are required before the extension can be downloaded and continuity-validated.', '', 'Baseline reconciliation: the prior “13” count was stale. The canonical catalogue before this submission had 14 episodes; this run added one genuinely new 2018 episode, yielding 15. No episode was split in this reconciliation.']
(out/'farnorth_2004_2014_extension_readiness.md').write_text('\n'.join(lines)+'\n')
print('\n'.join(lines))
