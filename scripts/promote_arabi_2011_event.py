from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parents[1]
out = root/'data_quality'/'farnorth_consolidation'
canon_path = out/'canonical_flood_events_farnorth.csv'
new = pd.read_excel('/home/ongou/Downloads/Far North Cameroon Flood Catalogue 2004–2026.xlsx', sheet_name='VERIFIED_CATALOGUE')
r = new[new.canonical_event_id.eq('FNR-FLD-2011-001')].iloc[0].to_dict()
r2005 = new[new.canonical_event_id.eq('FNR-FLD-2005-003')].iloc[0].to_dict()
canon = pd.read_csv(canon_path)
if not canon.canonical_event_id.eq('FNR-FLD-2011-001').any():
    canon = pd.concat([canon, pd.DataFrame([r])], ignore_index=True)
canon.to_csv(canon_path, index=False)
audit = pd.DataFrame([
 {'candidate_id':'FNR-FLD-2011-001','status':'VERIFIED_FLOOD_EVENT','source_check':'Arabi.pdf Table 2 directly states Juillet/Septembre 2011; quartiers Makabaye, Hardé; destruction of houses and loss of life.','source_url':r['source_document_url']},
 {'candidate_id':'FNR-FLD-2005-003','status':'FLOOD_EVIDENCE_NEEDS_DATE','source_check':'The submitted primary URL is SAHA thesis/Scribd, not Arabi.pdf. Arabi.pdf Table 2 contains no 2005 entry and therefore cannot verify 29 August 2005 Djarengol.','source_url':r2005['source_document_url']},
])
audit.to_csv(out/'farnorth_arabi_critical_recheck.csv', index=False)
print('canonical rows:', len(canon))
