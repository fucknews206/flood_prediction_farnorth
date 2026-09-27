from pathlib import Path
import pandas as pd

ROOT=Path('/home/ongou/Desktop/projects/end-of -year-defence')
SRC=ROOT/'relief_web-datasets'
OUT=Path(__file__).resolve().parents[1]/'data_quality'/'farnorth_consolidation'/'reliefweb_xlsx_file_audit.csv'
rows=[
 {'file':'cmr_exno_data_inondationlc_md_mt_v1.0_20221206.xlsx','sheets':'TCD;Data','date_signal':'2022-12-06 (filename/report snapshot)','locality_signal':'Logone-et-Chari, Mayo-Tsanaga, Mayo-Danay, Mayo-Kani, Mayo-Sava','status':'GENERAL_FLOOD_REFERENCE','relationship':'Administrative impact inventory; corroborates the existing 2022 season but has no event onset/window independent of that episode.','promotion':'NO'},
 {'file':'cmr_floodsdata_20241104.xlsx','sheets':'CMR_admin2_floods_04112024','date_signal':'2024-11-04 (filename/report snapshot)','locality_signal':'Diamaré, Logone-et-Chari, Mayo-Danay, Mayo-Kani, Mayo-Tsanaga','status':'POSSIBLE_DUPLICATE','relationship':'Administrative flood-impact snapshot; supports FLD-CMR-2024-001 and does not establish a distinct wave.','promotion':'NO'},
 {'file':'cmr_floods_data_251003.xlsx','sheets':'data','date_signal':'2025-10-03 (filename/report snapshot)','locality_signal':'Mayo-Danay, Mayo-Tsanaga, Logone-et-Chari','status':'POSSIBLE_DUPLICATE','relationship':'Administrative impact snapshot immediately before/within the documented 2025 flood season; supports FNR-FLD-2025-001/002 but contains no independent event window.','promotion':'NO'},
 {'file':'dtm-cameroon-baseline-assessment-round-12.xlsx','sheets':'13 sheets','date_signal':'DTM Round 12 snapshot; no flood-event date field','locality_signal':'Far North displacement locations','status':'GENERAL_FLOOD_REFERENCE','relationship':'Baseline displacement survey and reasons; flood is a reason/category, not a dated, located flood episode.','promotion':'NO'},
 {'file':'dtm-cameroon-baseline-assessment-round-15.xlsx','sheets':'14 sheets','date_signal':'2018-09-30 snapshot (survey date)','locality_signal':'Far North displacement locations','status':'GENERAL_FLOOD_REFERENCE','relationship':'Baseline displacement survey; flood mentions are aggregate displacement reasons and cannot be promoted as an independent event.','promotion':'NO'},
]
for r in rows:r['source_path']=str(SRC/r['file'])
pd.DataFrame(rows).to_csv(OUT,index=False)
print(f'wrote {OUT} ({len(rows)} files)')

