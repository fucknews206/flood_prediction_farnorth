#!/usr/bin/env python3
"""Promote independently web-confirmed Far North episodes; do not infer 2015/16."""
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data_quality'/'farnorth_consolidation'
P=OUT/'canonical_flood_events_farnorth.csv'

def main():
 d=pd.read_csv(P)
 additions=pd.DataFrame([
  {"canonical_event_id":"FNR-FLD-2020-004","event_status":"VERIFIED_FLOOD_EVENT","event_start_date":"2020-10","event_end_date":"2020-10","date_precision":"MONTH_OR_WINDOW","locality_name":"Blangoua; Makary","division":"Logone-et-Chari","region":"Far North","latitude":None,"longitude":None,"location_precision":"ADMINISTRATIVE_FOOTPRINT","source_document_title":"Cameroon Tribune: Inondations dans le Logone et Chari : au secours des déplacés","source_document_url":"https://www.cameroon-tribune.cm/articles/5070/fr/","source_event_id":"candidate-FLD-CMR-2020-004","duplicate_of":None,"evidence_summary":"Published 27 October 2020: El Beid waters overflowed in Makary and Blangoua after weeks of heavy rain, flooding villages, homes and fields.","supporting_evidence":"OCHA 2021 HNO documents broader severe 2020 seasonal flooding."},
  {"canonical_event_id":"FNR-FLD-2023-002","event_status":"VERIFIED_FLOOD_EVENT","event_start_date":"2023-07","event_end_date":"2023-09","date_precision":"MONTH_OR_WINDOW","locality_name":"Maga arrondissement; Yagoua; Vélé; Kai-Kai; Zina; Logone-Birni","division":"Logone-et-Chari; Mayo-Danay","region":"Far North","latitude":None,"longitude":None,"location_precision":"ADMINISTRATIVE_FOOTPRINT","source_document_title":"OCHA-attributed Far North humanitarian review, reported by Journal du Cameroun","source_document_url":"https://en.journalducameroun.com/cameroon-far-north-more-than-300-hectares-of-rice-destroyed-by-floods/","source_event_id":"candidate-FLD-CMR-2023-003","duplicate_of":None,"evidence_summary":"Water rose from early July 2023, causing crop losses in named Mayo-Danay and Logone-et-Chari localities; 337 hectares of rice were destroyed in 12 Maga-arrondissement villages.","supporting_evidence":"Additional syndications cite the same OCHA/MINADER evidence."},
 ])
 d=pd.concat([d,additions],ignore_index=True,sort=False).drop_duplicates('canonical_event_id',keep='last')
 d.to_csv(P,index=False)
 # Preserve a concise gate update for this incremental evidence pass.
 divisions={}
 for value in d.division.fillna(''):
  for item in str(value).split(';'):
   if item.strip(): divisions[item.strip()]=divisions.get(item.strip(),0)+1
 years=sorted({str(x)[:4] for x in d.event_start_date if str(x)[:4].isdigit()})
 report=f'''# Far North region only, 2015-2025 — Readiness Gate after external source audit

**FAIL — DO NOT TRAIN A CLASSIFIER**

- Independent verified episodes: {len(d)}.
- New promotions in this pass: 2: FNR-FLD-2020-004 and FNR-FLD-2023-002.
- 2015 and 2016 remain held: their supplied claims did not expose a primary source statement tying a flood event to a defensible date/window and footprint.
- Distinct years: {len(years)} ({', '.join(years)}).
- Per-division episode coverage: {divisions}.
- Gap to the 30-episode minimum: {30-len(d)}.

This remains adequate for an interim rules-based warning system, but not a reliable supervised flood classifier.
'''
 (OUT/'farnorth_build_summary.md').write_text(report,encoding='utf-8')

if __name__=='__main__': main()
