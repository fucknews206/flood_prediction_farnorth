#!/usr/bin/env python3
"""Create a transparent one-gap-first manual verification worklist."""
from pathlib import Path
import re
import pandas as pd

OUT=Path('/home/ongou/Desktop/projects/end-of -year-defence/h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation')
LOCALITY=re.compile(r'\b(?:Diamar[eé]|Logone[ -]et[ -]Chari|Mayo[ -](?:Danay|Kani|Sava|Tsanaga)|Maroua|Kousseri|Maga|Makary|Blangoua|Zina|Yagoua|Mokolo|Mora|Fotokol|Darak|Guirvidig|Kai[ -]Kai|Ka[iï][ -]Kai)\b',re.I)
# This deliberately excludes upload/publication metadata. It accepts only a
# date/window stated in the candidate text itself.
DATE=re.compile(r'(?:\b\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+20\d{2}\b|\b(?:entre|du)\s+\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(?:et|au)\s+\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+20\d{2}\b)',re.I)
def main():
 d=pd.read_csv(OUT/'farnorth_new_sources_cross_reference_audit.csv').fillna('')
 evidence=(d.title.astype(str)+'\n'+d.text.astype(str))
 d['missing_date']=~evidence.str.contains(DATE,na=False)
 d['missing_locality']=~evidence.str.contains(LOCALITY,na=False)
 d['source_url']=d.url.astype(str).replace('',pd.NA)
 d['missing_evidence_count']=d.missing_date.astype(int)+d.missing_locality.astype(int)
 d['manual_check_note']=d.apply(lambda r: (
     'Candidate text names both; manually verify that they refer to the same flood event.' if not r.missing_date and not r.missing_locality else
     'Need event date/window only.' if r.missing_date and not r.missing_locality else
     'Need locality/administrative footprint only.' if r.missing_locality and not r.missing_date else
     'Need both event date/window and locality/footprint.'), axis=1)
 cols=['source_type','source_file','source_unit','title','text','date_metadata','source_url','missing_date','missing_locality','manual_check_note','decision','linked_episode','reason']
 d.sort_values(['missing_evidence_count','source_type','source_file','source_unit']).reindex(columns=cols).to_csv(OUT/'farnorth_manual_verification_worklist.csv',index=False)
 print({'rows':len(d),'missing_date_only':int((d.missing_date&~d.missing_locality).sum()),'missing_locality_only':int((~d.missing_date&d.missing_locality).sum()),'missing_both':int((d.missing_date&d.missing_locality).sum()),'complete':int((~d.missing_date&~d.missing_locality).sum())})
if __name__=='__main__':main()
