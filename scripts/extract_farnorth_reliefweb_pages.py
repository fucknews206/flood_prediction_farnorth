#!/usr/bin/env python3
"""Extract page-level Far North flood evidence from every matching ReliefWeb PDF."""
from pathlib import Path
import re
import pandas as pd
from PyPDF2 import PdfFileReader
ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence'); OUT=ROOT/'h2oai-flood-intelligence-agent-main/data_quality/farnorth_consolidation'; PDF=ROOT/'relief_web-datasets'
T=re.compile(r'\b(?:Diamar[eé]|Logone[ -]et[ -]Chari|Mayo[ -](?:Danay|Kani|Sava|Tsanaga)|Maroua|Kousseri|Maga|Makary|Blangoua|Zina|Yagoua|Mokolo|Mora|Fotokol|Darak|Guirvidig)\b',re.I); F=re.compile(r'inond|flood|crue',re.I)
def main():
 inv=pd.read_csv(OUT/'farnorth_reliefweb_full_inventory.csv');rows=[]
 for f in inv[inv.candidate].file:
  p=ROOT/f
  with open(p,'rb') as h:r=PdfFileReader(h); pages=[r.getPage(i).extractText() for i in range(r.numPages)]
  for n,t in enumerate(pages,1):
   if T.search(t) and F.search(t):
    lines=[x.strip() for x in t.splitlines() if F.search(x) or T.search(x)]
    rows.append({'source_file':f,'page_number':n,'matched_terms':'; '.join(dict.fromkeys(T.findall(t))),'excerpt':' | '.join(lines)[:3000], 'verification_status':'FLOOD_EVIDENCE_NEEDS_DATE','verification_reason':'Full source page extracted. Requires human/source-specific confirmation of an event date/window and mapped locality before promotion.'})
 d=pd.DataFrame(rows);d.to_csv(OUT/'farnorth_reliefweb_page_evidence_audit.csv',index=False);print(len(d))
if __name__=='__main__':main()
