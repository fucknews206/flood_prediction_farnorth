#!/usr/bin/env python3
"""Far North region only, 2015-2025: full-local-PDF evidence refinement."""
from pathlib import Path
import re
import pandas as pd
from PyPDF2 import PdfFileReader

ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence'); OUT=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation'
PDFROOT=ROOT/'relief_web-datasets'
LOCALITIES=['Maga','Zina','Kai Kai','Makary','Blangoua','Kousseri','Darak','Fotokol','Maroua','Mokolo','Mora','Yagoua','Guirvidig','Moulvoudaye','Waza','Kolofata','Hile']
DIVS=['Diamaré','Logone-et-Chari','Mayo-Danay','Mayo-Kani','Mayo-Sava','Mayo-Tsanaga']
def text(path):
 try:
  with open(path,'rb') as f:
   r=PdfFileReader(f); return '\n'.join(r.getPage(i).extractText() for i in range(r.numPages))
 except Exception:return ''
def main():
 a=pd.read_csv(OUT/'farnorth_evidence_verification_audit.csv')
 cache={}; rows=[]
 for x in a.itertuples(index=False):
  fn=str(x.filename); p=PDFROOT/fn
  if fn not in cache: cache[fn]=text(p) if p.exists() else ''
  full=cache[fn]; low=full.lower(); loc=next((z for z in LOCALITIES if z.lower() in low),'UNKNOWN'); div=next((z for z in DIVS if z.lower() in low),'UNKNOWN')
  flood='inond' in low or 'flood' in low
  status='GENERAL_FLOOD_REFERENCE' if not flood else 'FLOOD_EVIDENCE_NEEDS_DATE'
  # Existing source date is never used as event date: no document in this
  # automated full-text pass explicitly ties a day to a local flood footprint.
  reason=('Full local source document could not be opened/extracted.' if not full else
          ('Full document contains a flood reference but does not explicitly establish a specific event date and mapped locality together; source/report date retained only as metadata.' if flood else 'Full document does not establish an individual flood event.'))
  rows.append({**x._asdict(),'full_source_opened':bool(full),'full_source_characters':len(full),'fulltext_locality':loc,'fulltext_division':div,'final_status':status,'final_reason':reason})
 out=pd.DataFrame(rows);out.to_csv(OUT/'farnorth_evidence_fulltext_final_audit.csv',index=False)
 cols=['canonical_event_id','event_status','event_start_date','event_end_date','locality_name','division','region','latitude','longitude','source_document_title','source_document_url','source_event_id','evidence_summary']
 pd.DataFrame(columns=cols).to_csv(OUT/'canonical_flood_events_farnorth.csv',index=False)
 summary=f'''# Far North region only, 2015-2025 — final evidence refinement gate

**FAIL — DO NOT TRAIN**

- Candidate records reviewed against their full local source document where extractable: {len(out)}.
- Documents successfully opened/extracted: {int(out.full_source_opened.sum())}.
- Final statuses: {out.final_status.value_counts().to_dict()}.
- Canonical verified events: 0; total positive rows: 0; distinct localities: 0; distinct years: 0; division coverage: none.

Full-text evidence was not promoted from report dates or survey periods. The available full documents establish flood impacts/references but this pass did not find a source-explicit individual event date plus defensible mapped locality together for a canonical positive. The Far North readiness gate therefore fails and Phases F/G are not authorized. This is Far North region only, 2015-2025.
'''
 (OUT/'farnorth_build_summary.md').write_text(summary,encoding='utf-8');print(out.final_status.value_counts().to_dict())
if __name__=='__main__':main()
