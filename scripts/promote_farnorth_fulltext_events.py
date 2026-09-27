#!/usr/bin/env python3
"""Promote only full-source-explicit Far North events, 2015-2025."""
from pathlib import Path
import pandas as pd
ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence');OUT=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation'; GAZ=ROOT/'boundaries-data/gazetteer_farnorth.csv'
def main():
 gaz=pd.read_csv(GAZ)
 specs=[
 ('FNR-FLD-2019-001','2019-10-04','Maga','Mayo-Danay','MDRCM028dfr.pdf',1,
  'IFRC DREF final report explicitly gives Date of disaster: 4 October 2019. It describes Logone River flooding affecting communities south of Lake Maga, including Guirvidig, and uses Maga as the defensible gazetteer locality footprint.'),
 ('FNR-FLD-2020-001','2020-09-11','Kai-Kai','Mayo-Danay','MDRCM029dfr.pdf',1,
  'IFRC final report explicitly states continuous intense rains on 11 and 12 September 2020 caused flooding in Mayo-Danay and Mayo-Kani; it identifies Kai-Kai in Mayo-Danay as an affected/response locality. Event start date is 11 September 2020.'),
 ]
 rows=[]
 for eid,date,loc,div,fn,page,summary in specs:
  x=gaz[gaz.name.eq(loc)]
  if len(x)!=1: raise ValueError(loc)
  x=x.iloc[0]
  rows.append({'canonical_event_id':eid,'event_status':'VERIFIED_FLOOD_EVENT','event_start_date':date,'event_end_date':date,'locality_name':loc,'division':div,'region':'Far North','latitude':x.lat,'longitude':x.lon,'source_document_title':fn,'source_document_url':'LOCAL_FILE:'+str((ROOT/'relief_web-datasets'/fn).relative_to(ROOT)),'source_event_id':'RELIEFWEB_PAGE_'+str(page),'evidence_summary':summary})
 pd.DataFrame(rows).to_csv(OUT/'canonical_flood_events_farnorth.csv',index=False)
 audit=pd.read_csv(OUT/'farnorth_evidence_fulltext_final_audit.csv')
 audit['final_status']=audit.final_status.fillna('FLOOD_EVIDENCE_NEEDS_DATE')
 audit.to_csv(OUT/'farnorth_evidence_fulltext_final_audit.csv',index=False)
 c=pd.DataFrame(rows); div=c.groupby('division').size().to_dict(); years=pd.to_datetime(c.event_start_date).dt.year.nunique()
 (OUT/'farnorth_build_summary.md').write_text(f'''# Far North region only, 2015-2025 — Readiness Gate

**FAIL — DO NOT TRAIN**

## Full-source refinement

- ReliefWeb PDFs opened: 104/104; flood-and-Far-North matching PDFs: 47; extracted relevant pages: 162.
- Canonical verified episodes: {len(c)}. Each has a source-explicit event date and a gazetteer locality footprint.

## Readiness Gate actual numbers

- Total positive rows: {len(c)}.
- Distinct localities: {c.locality_name.nunique()}.
- Distinct years: {years}.
- Positives per division: {div}.
- Divisions with zero positives: Diamaré, Logone-et-Chari, Mayo-Kani, Mayo-Sava, Mayo-Tsanaga.

## Decision rationale

The Far North gate requires roughly 30–50 independent verified events, multi-division coverage, and 4–5 years. It currently has only {len(c)} events, both in Mayo-Danay across 2019–2020. The dataset is not trainable and Phases F/G are not run. This is Far North region only, 2015-2025.
''',encoding='utf-8')
 print(c[['canonical_event_id','event_start_date','locality_name']].to_dict('records'))
if __name__=='__main__':main()
