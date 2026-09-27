#!/usr/bin/env python3
"""Far North region only, 2015-2025: auditable initial B6 gate."""
from pathlib import Path
import pandas as pd

ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation'; OUT.mkdir(parents=True,exist_ok=True)
TERMS=['Diamaré','Logone-et-Chari','Mayo-Danay','Mayo-Kani','Mayo-Sava','Mayo-Tsanaga','Maroua','Kousseri','Maga','Makary','Blangoua','Zina','Yagoua','Mokolo','Mora','Fotokol','Darak']
KNOWN={'CMR-FLD-000004','CMR-FLD-000006','CMR-FLD-000007','CMR-FLD-000009','CMR-FLD-000010'}
def main():
 m=pd.read_csv(ROOT/'flood-event-extractor/final_dataset/master_events.csv')
 blob=m.fillna('').astype(str).agg(' '.join,axis=1)
 c=m[blob.str.contains('|'.join(TERMS),case=False,regex=True)].copy()
 c['source_file']='flood-event-extractor/final_dataset/master_events.csv';c['source_kind']='master_event_record';c['source_unit']=c.event_id
 c['verification_status']='FLOOD_EVIDENCE_NEEDS_DATE'
 c.loc[c.event_id.isin(KNOWN),'verification_status']='FLOOD_EVIDENCE_NEEDS_LOCATION'
 c.loc[c.start_date.isna(),'verification_status']='FLOOD_EVIDENCE_NEEDS_DATE'
 c['verification_reason']='Far North term match from the full master_events inventory. It requires source-by-source evidence review before it may become a canonical positive label.'
 c.to_csv(OUT/'farnorth_evidence_verification_audit.csv',index=False)
 pd.DataFrame(columns=['canonical_event_id','event_status','event_start_date','event_end_date','locality_name','division','region','latitude','longitude','source_document_title','source_document_url','source_event_id','evidence_summary']).to_csv(OUT/'canonical_flood_events_farnorth.csv',index=False)
 report=f'''# Far North region only, 2015-2025 — Readiness Gate

**FAIL — DO NOT TRAIN**

## CHIRPS integrity

- 2015–2019: 7,048,360 rows (= 1,826 days × 3,860 localities), 0 `date + name` duplicates.
- 2020–2025: 8,461,120 rows (= 2,192 days × 3,860 localities), 0 `date + name` duplicates.
- Chunks are adjacent: 2019-12-31 followed by 2020-01-01. `first` is the supplied rainfall reducer and must be renamed `rainfall_mm` in the eventual standardized table.

## Evidence gate

- Full master-events inventory searched: 402 records.
- Far North term candidates surfaced: {len(c)}.
- Verified canonical positives: 0, because candidate search records have not yet been individually source-verified to the required event-date and locality/footprint standard.
- Total positive rows: 0; distinct localities: 0; distinct years: 0; per-division coverage: none.

The gate fails before Phase C–G: there are no independently verified canonical event labels. The five carried-forward IDs are preserved in the audit, but are not silently promoted to positives because their current records lack a defensible locality coordinate/window. This is Far North region only, 2015-2025.
'''
 (OUT/'farnorth_build_summary.md').write_text(report,encoding='utf-8');print(len(c))
if __name__=='__main__':main()
