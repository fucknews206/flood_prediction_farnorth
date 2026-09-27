#!/usr/bin/env python3
"""Far North only: traceable reconciliation of every extracted source unit."""
from pathlib import Path
import re,pandas as pd
ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence');OUT=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation'
YEAR_EVENT={2017:'FLD-CMR-2017-001',2019:'FLD-CMR-2019-001',2020:'FLD-CMR-2020-001',2021:'FLD-CMR-2021-001',2022:'FLD-CMR-2022-001',2023:'FLD-CMR-2023-001',2024:'FLD-CMR-2024-001'}
def year_from_text(s):
 years=[int(x) for x in re.findall(r'20(?:1[5-9]|2[0-5])',s)]
 return max(years) if years else None
def main():
 pages=pd.read_csv(OUT/'farnorth_reliefweb_page_evidence_audit.csv')
 prow=[]
 for x in pages.itertuples(index=False):
  y=year_from_text(str(x.source_file)+' '+str(x.excerpt)); ev=YEAR_EVENT.get(y)
  # DTM survey aggregate pages are never individual events.
  is_dtm=any(z in str(x.source_file) for z in ['DTM','Displacement Report','Round 13','Round 15','RD17','RD18','Round 21'])
  if ev and not is_dtm:
   status='SUPPORTING_EVIDENCE'; reason=f'Full-page content is attributable to already audited {y} Far North episode; linked as supporting evidence, not a new episode.'
  elif is_dtm:
   status='GENERAL_FLOOD_REFERENCE'; ev='';reason='Full page is a DTM/survey aggregate or recurrent-risk reference, not an independently dated flood episode.'
  else:
   status='FLOOD_EVIDENCE_NEEDS_DATE';ev='';reason='Full page has flood and Far North terms but no defensible distinct event window after reconciliation.'
  prow.append({**x._asdict(),'reconciliation_status':status,'linked_canonical_event_id':ev,'reconciliation_reason':reason})
 p=pd.DataFrame(prow);p.to_csv(OUT/'farnorth_reliefweb_page_reconciliation.csv',index=False)
 s=pd.read_csv(OUT/'farnorth_scraper_evidence_audit.csv')
 s['reconciliation_status']='FLOOD_EVIDENCE_NEEDS_DATE';s['linked_canonical_event_id']='';s['reconciliation_reason']='Search/social scraper text is not a full source document. It cannot establish a new event or be assigned to an existing episode without opening its linked source.'
 s.to_csv(OUT/'farnorth_scraper_candidate_reconciliation.csv',index=False)
 stats={'reliefweb_supporting':int(p.reconciliation_status.eq('SUPPORTING_EVIDENCE').sum()),'reliefweb_general':int(p.reconciliation_status.eq('GENERAL_FLOOD_REFERENCE').sum()),'reliefweb_holds':int(p.reconciliation_status.eq('FLOOD_EVIDENCE_NEEDS_DATE').sum()),'scraper_holds':len(s),'new_independent_episodes':0}
 pd.DataFrame([stats]).to_csv(OUT/'farnorth_candidate_reconciliation_summary.csv',index=False);print(stats)
if __name__=='__main__':main()
