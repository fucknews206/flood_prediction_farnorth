#!/usr/bin/env python3
"""Reconcile audited Phase 1 Far North episodes into the Far North catalogue."""
from pathlib import Path
import pandas as pd
ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence'); OUT=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation'
PHASE1=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/phase1/clean_flood_events.csv'
def main():
 clean=pd.read_csv(PHASE1); clean=clean[clean.region.eq('Far North')].copy()
 rows=[]
 for x in clean.itertuples(index=False):
  rows.append({'canonical_event_id':x.event_id,'event_status':'VERIFIED_FLOOD_EVENT','event_start_date':x.event_date,'event_end_date':x.event_end_date if pd.notna(x.event_end_date) else 'UNKNOWN','date_precision':'MONTH_OR_WINDOW','locality_name':x.locality if pd.notna(x.locality) else 'UNKNOWN','division':x.division,'region':'Far North','latitude':x.latitude,'longitude':x.longitude,'location_precision':'ADMINISTRATIVE_FOOTPRINT' if pd.notna(x.division) else 'UNKNOWN','source_document_title':x.source,'source_document_url':'PHASE1_AUDITED_CATALOGUE','source_event_id':x.event_id,'duplicate_of':'','evidence_summary':'Imported unchanged from audited Phase 1 clean_flood_events.csv.'})
 c=pd.DataFrame(rows)
 # IFRC 2019 is inside Sep-Nov Logone-et-Chari; IFRC 2020 occurred within
 # the ongoing July 2020 Far North episode. Keep their exact dates only as
 # refinements to their Phase 1 canonical episodes.
 c.loc[c.canonical_event_id.eq('FLD-CMR-2019-001'),'evidence_summary'] += ' IFRC MDRCM028 refines this episode with 2019-10-04 Maga/Guirvidig evidence.'
 c.loc[c.canonical_event_id.eq('FLD-CMR-2020-001'),'evidence_summary'] += ' IFRC MDRCM029 refines this episode with 2020-09-11 Kai-Kai evidence.'
 refinements=pd.DataFrame([
 {'source_event_id':'FNR-FLD-2019-001','duplicate_of':'FLD-CMR-2019-001','precise_date':'2019-10-04','precise_locality':'Maga','source_document':'MDRCM028dfr.pdf','relationship':'within audited Sep-Nov 2019 Logone-et-Chari episode'},
 {'source_event_id':'FNR-FLD-2020-001','duplicate_of':'FLD-CMR-2020-001','precise_date':'2020-09-11','precise_locality':'Kai-Kai','source_document':'MDRCM029dfr.pdf','relationship':'within audited July-2020 onward Far North episode'},
 ])
 refinements.to_csv(OUT/'farnorth_event_refinements_and_duplicates.csv',index=False)
 c.to_csv(OUT/'canonical_flood_events_farnorth.csv',index=False)
 div=c.explode('division').assign(division=lambda d:d.division.str.split(';')).explode('division').assign(division=lambda d:d.division.str.strip()).groupby('division').size().to_dict()
 print({'episodes':len(c),'localities':c.locality_name.replace('UNKNOWN',pd.NA).nunique(),'years':pd.to_datetime(c.event_start_date).dt.year.nunique(),'division_coverage':div})
if __name__=='__main__':main()
