#!/usr/bin/env python3
"""Far North only, 2015-2025: cross-reference new social/search sources."""
from pathlib import Path
import pandas as pd,re
ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence');OUT=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation';S=ROOT/'scrapers-data'
TERMS=re.compile(r'(inond|flood|crue).*(?:Mayo[- ]Kani|Diamar|Yagoua|Maga|Kousseri|Logone|Mayo[- ]Danay|Maroua)|(?:Mayo[- ]Kani|Diamar|Yagoua|Maga|Kousseri|Logone|Mayo[- ]Danay|Maroua).*(?:inond|flood|crue)',re.I|re.S)
def main():
 rows=[]
 for group in ['farnorth_youtube','farnorth_facebook','farnorth_google']:
  for f in (S/group).glob('*.csv'):
   d=pd.read_csv(f,dtype=str).fillna('')
   # Google exports are wide; each organic result is one candidate unit.
   if group=='farnorth_google':
    for _,r in d.iterrows():
     for i in range(30):
      title=r.get(f'organicResults/{i}/title','');desc=r.get(f'organicResults/{i}/description','');url=r.get(f'organicResults/{i}/url','');date=r.get(f'organicResults/{i}/date','')
      t=' '.join([title,desc])
      if TERMS.search(t): rows.append({'source_type':'google','source_file':str(f.relative_to(ROOT)),'source_unit':f'organicResults/{i}','date_metadata':date,'title':title,'text':desc,'url':url})
   else:
    for i,r in d.iterrows():
     title=r.get('title','');text=r.get('text','') or r.get('message','') or r.get('postText','');date=r.get('date','') or r.get('time','') or r.get('createdAt','');url=r.get('url','') or r.get('facebookUrl','')
     if TERMS.search(' '.join([title,text])): rows.append({'source_type':group.replace('farnorth_',''),'source_file':str(f.relative_to(ROOT)),'source_unit':f'row {i+2}','date_metadata':date,'title':title,'text':text,'url':url})
 a=pd.DataFrame(rows)
 # New Google results independently corroborate the already audited 2024
 # episode and explicitly extend its administrative footprint to Mayo-Kani;
 # it is a refinement, never a new episode.
 a['decision']='FLOOD_EVIDENCE_NEEDS_DATE';a['linked_episode']='';a['reason']='Candidate needs full-source reading or transcript before promotion.'
 mask=a.text.str.contains('2024|septembre|octobre',case=False,na=False)&a.text.str.contains('Mayo-Kani',case=False,na=False)
 a.loc[mask,['decision','linked_episode','reason']]=['ADDITIONAL_SUPPORTING_EVIDENCE','FLD-CMR-2024-001','Cross-confirms the 2024 Far North flood episode and its Mayo-Kani administrative impact footprint; not a separate event.']
 a.to_csv(OUT/'farnorth_new_sources_cross_reference_audit.csv',index=False)
 print({'candidates':len(a),'supporting_2024':int(mask.sum()),'new_events':0})
if __name__=='__main__':main()
