from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parents[1]
out = root/'data_quality'/'farnorth_consolidation'
cp = out/'canonical_flood_events_farnorth.csv'
w = pd.read_excel('/home/ongou/Downloads/Far North Cameroon Flood Catalogue 2004–2026.xlsx','VERIFIED_CATALOGUE')
c = pd.read_csv(cp)
ids = ['FNR-FLD-2007-003','FNR-FLD-2007-004','FNR-FLD-2007-005']
rows = w[w.canonical_event_id.isin(ids)].copy()
for col in c.columns:
    if col not in rows.columns:
        rows[col] = pd.NA
rows = rows[c.columns]
c = pd.concat([c, rows[~rows.canonical_event_id.isin(c.canonical_event_id)]], ignore_index=True)
c.to_csv(cp, index=False)
print('promoted', ids, 'catalogue_total', len(c))
