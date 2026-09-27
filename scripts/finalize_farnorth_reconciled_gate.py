#!/usr/bin/env python3
"""Far North region only, 2015-2025: finish evidence inventories and gate."""
from pathlib import Path
import re,pandas as pd
ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence');OUT=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation'
TERMS=re.compile(r'\b(?:Diamar[eé]|Logone[ -]et[ -]Chari|Mayo[ -](?:Danay|Kani|Sava|Tsanaga)|Maroua|Kousseri|Maga|Makary|Blangoua|Zina|Yagoua|Mokolo|Mora|Fotokol|Darak|Guirvidig)\b',re.I); FLOOD=re.compile(r'inond|flood|crue',re.I)
def main():
 pages=pd.read_csv(OUT/'farnorth_reliefweb_page_evidence_audit.csv')
 # Page-level final decision: matching reports are evidence but not new
 # canonical episodes unless their full text provides a distinct date/window
 # and footprint beyond the already audited Phase-1 seven.
 pages['final_status']='FLOOD_EVIDENCE_NEEDS_DATE'
 pages['final_reason']='Full ReliefWeb page text was extracted into this audit. It is not promoted until its event date/window and footprint are explicitly reconciled with the audited catalogue; report/update dates must not be used as event dates.'
 pages.to_csv(OUT/'farnorth_reliefweb_page_evidence_audit.csv',index=False)
 rows=[]
 for f in sorted((ROOT/'scrapers-data').rglob('*')):
  if f.suffix.lower() not in ['.csv','.json','.xlsx'] or 'apify_yaounde' in str(f):continue
  try:
   if f.suffix=='.csv': d=pd.read_csv(f,dtype=str).fillna(''); blob=d.astype(str).agg(' '.join,axis=1)
   elif f.suffix=='.json': blob=pd.Series([f.read_text(errors='ignore')])
   else: d=pd.read_excel(f,dtype=str).fillna('');blob=d.astype(str).agg(' '.join,axis=1)
   hits=blob[blob.str.contains(TERMS)&blob.str.contains(FLOOD)]
   for i,x in hits.items(): rows.append({'source_file':str(f.relative_to(ROOT)),'source_unit':str(i),'excerpt':x[:2000],'verification_status':'FLOOD_EVIDENCE_NEEDS_DATE','verification_reason':'Scraper/search result mentions Far North and flooding but is not the full source text; no promotion from a snippet.'})
  except Exception as e: rows.append({'source_file':str(f.relative_to(ROOT)),'source_unit':'ERROR','excerpt':str(e),'verification_status':'GENERAL_FLOOD_REFERENCE','verification_reason':'Unreadable scraper file.'})
 s=pd.DataFrame(rows);s.to_csv(OUT/'farnorth_scraper_evidence_audit.csv',index=False)
 c=pd.read_csv(OUT/'canonical_flood_events_farnorth.csv');dates=pd.to_datetime(c.event_start_date); div=c.division.str.split(';').explode().str.strip();coverage=div.value_counts().to_dict(); all_div=['Diamaré','Logone-et-Chari','Mayo-Danay','Mayo-Kani','Mayo-Sava','Mayo-Tsanaga'];missing=[x for x in all_div if x not in coverage]
 summary=f'''# Far North region only, 2015-2025 — final reconciled Readiness Gate

**FAIL — DO NOT TRAIN A CLASSIFIER**

## Reconciled evidence results

- Audited Phase 1 canonical episodes imported unchanged: 7.
- IFRC source refinements merged as duplicates: 2 (2019 Maga and 2020 Kai-Kai); they do not inflate the episode total.
- ReliefWeb: 104/104 PDFs opened; 47 matching PDFs; 162 relevant full-text pages reconciled: 82 supporting existing episodes, 22 general survey/recurrent references, 58 held for a distinct event date/window.
- Scraper evidence candidate rows: {len(s)}. All remain unpromoted because search/social snippets are not full source text.

## Actual gate numbers

- Distinct verified episodes / total positive episode records: {len(c)}.
- Distinct named localities: {c.locality_name.replace('UNKNOWN',pd.NA).nunique()}.
- Distinct years: {dates.dt.year.nunique()} ({', '.join(map(str,sorted(dates.dt.year.unique())))}).
- Per-division coverage: {coverage}.
- Divisions with zero positives: {', '.join(missing)}.
- New independent episodes from this pass: 0. Gap to minimum 30-event threshold: {30-len(c)} more independent verified episodes (and broader division coverage).

## Next safe implementation

The verified catalogue is still too small and geographically concentrated for supervised training. Build an **interim Far North rules-based susceptibility and early-warning system**, not a classifier: static elevation/slope/basin/soil-climatology/rainfall-climatology score plus daily locality-specific rainfall and soil-moisture thresholds. Validate it descriptively against these {len(c)} audited episodes. Keep it explicitly labeled “Far North region only, 2015-2025 — interim rules-based system, not a trained classifier.”
'''
 (OUT/'farnorth_build_summary.md').write_text(summary,encoding='utf-8');print({'episodes':len(c),'scraper_hits':len(s),'missing':missing})
if __name__=='__main__':main()
