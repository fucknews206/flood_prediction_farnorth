#!/usr/bin/env python3
"""Record the external-source extension audit; no unsupported labels are created."""
from pathlib import Path
import pandas as pd

OUT = Path(__file__).resolve().parents[1] / 'data_quality' / 'farnorth_consolidation'

ROWS = [
 ('2015', 'Zina / Logone-et-Chari', 'OCHA weekly snapshot candidate', 'FLOOD_EVIDENCE_NEEDS_DATE', '', 'No retrievable primary text found that establishes the asserted October 2015 flood date/window.'),
 ('2016', 'Mayo-Danay', 'IOM/UNHCR DTM candidate', 'FLOOD_EVIDENCE_NEEDS_DATE', '', 'Retrieved 2016 DTM search result concerns conflict assessment in Logone-et-Chari; it does not prove the asserted August Mayo-Danay flood.'),
 ('2017', 'Zina / Logone-et-Chari', 'OCHA humanitarian bulletin / UN-SPIDER', 'ADDITIONAL_SUPPORTING_EVIDENCE', 'FLD-CMR-2017-001', 'Already canonical; OCHA result describes hundreds displaced after heavy rains in Zina villages.'),
 ('2018', 'Mora / Kolofata, Mayo-Sava', 'IFRC/UNICEF cholera-response candidate', 'GENERAL_FLOOD_REFERENCE', '', 'Retrieved sources document cholera, displacement and preparedness, not a flood event at the asserted time/place.'),
 ('2019', 'Zina / Maga / Kai-Kai', 'ACAPS, IFRC, UNICEF', 'ADDITIONAL_SUPPORTING_EVIDENCE', 'FLD-CMR-2019-001', 'Multiple reports document dates and impacts, but within the canonical September-November 2019 episode.'),
 ('2020', 'Far North / Logone-et-Chari / Mayo-Danay', 'OCHA HNO, Cameroon Tribune, JRC', 'ADDITIONAL_SUPPORTING_EVIDENCE', 'FLD-CMR-2020-001', 'October-November impacts are part of the documented severe 2020 rainy-season episode, not independently established new waves.'),
 ('2021', 'Makary / Goulfey', 'OCHA candidate', 'FLOOD_EVIDENCE_NEEDS_DATE', '', 'No inspected source text establishes both an August 2021 flood window and these locations.'),
 ('2022', 'Kousseri / Far North', 'UNFPA and OCHA', 'ADDITIONAL_SUPPORTING_EVIDENCE', 'FLD-CMR-2022-001', 'UNFPA establishes an August-October 2022 season and later November dyke damage; already one canonical 2022 episode.'),
 ('2023', 'Bourrha / Mogodé / Maga', 'WFP/FEWS NET candidates', 'GENERAL_FLOOD_REFERENCE', '', 'Located results describe vulnerability or risk analysis, not a dated flood occurrence. Blangoua remains the sole verified 2023 episode.'),
 ('2024', 'five Far North divisions', 'IFRC, UNFPA, UNICEF, FAO', 'ADDITIONAL_SUPPORTING_EVIDENCE', 'FLD-CMR-2024-001', 'All corroborate/refine the existing July-November 2024 regional episode.'),
 ('2025', 'Mayo-Tsanaga / Mayo-Danay / Logone-et-Chari', 'IFRC, UNICEF, OCHA-reported source', 'ADDITIONAL_SUPPORTING_EVIDENCE', 'FNR-FLD-2025-001; FNR-FLD-2025-002', 'July-August and 7-8 October episodes already canonical. UNICEF Q3 report has a reporting-period date, not another event date.'),
]

def main():
 d=pd.DataFrame(ROWS, columns=['year','candidate_footprint','source_family','final_status','canonical_event_id','finding'])
 d['scope_label']='Far North region only, 2015-2025'
 d.to_csv(OUT/'farnorth_external_web_extension_audit.csv',index=False)
 text='''# Far North region only, 2015-2025 — external web extension audit

## Outcome

The audit did **not** find evidence sufficient to promote a new independent flood episode. The canonical catalogue remains at **11**.

The main pattern is that extra sources either:

1. corroborate an already-canonical seasonal episode;
2. give a report/publication period rather than an event date; or
3. discuss flood susceptibility, cholera, displacement or response without documenting a specific flood occurrence.

## Sources that did provide usable corroboration

- ACAPS establishes 1 October 2019 flooding in Zina, Logone-et-Chari.
- IFRC MDRCM028 establishes 4 October 2019 Maga-area flooding.
- OCHA's 2021 humanitarian needs overview establishes severe, continuing 2020 seasonal flooding rather than a distinct additional October label.
- UNFPA establishes the August-October 2022 window and the November 2022 dyke impacts as part of the same episode.

## What still must be collected to reach the training target

Obtain primary incident reports—not catalogue pages, map pages, risk studies or response summaries—for distinct waves in thin years and divisions, especially 2015, 2016, 2018, 2021 and 2023. Each record needs an explicit flood statement, event date/window, locality/division and source URL/page.

Do not convert recurrence claims (for example, 'floods occur every year') into annual positive labels.
'''
 (OUT/'farnorth_external_web_extension_audit_report.md').write_text(text,encoding='utf-8')

if __name__=='__main__': main()
