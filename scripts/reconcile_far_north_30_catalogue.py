"""Reconcile the submitted Far North catalogue without inflating episodes."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
submitted = Path('/home/ongou/Downloads/Far North Cameroon Verified Flood Event Catalogue 2004–2026.csv')
out = ROOT / 'data_quality' / 'farnorth_consolidation'
canon_path = out / 'canonical_flood_events_farnorth.csv'
d = pd.read_csv(submitted)
d['_year'] = pd.to_datetime(d.event_start_date, errors='coerce').dt.year
in_window = d[d['_year'].between(2015, 2025)].copy()
outside = d[~d['_year'].between(2015, 2025)].copy()
outside.insert(1, 'training_eligibility', 'NOT_YET_USABLE_OUTSIDE_2015_2025')
outside.drop(columns=['_year']).to_csv(out / 'farnorth_catalogue_outside_environment_window.csv', index=False)

decisions = {
 'FNR-FLD-2015-001': ('POSSIBLE_DUPLICATE', 'Same 2015 Zina episode already canonical as FNR-FLD-2015-001; submitted row is an alternate claim with a different locality/date and is not promoted without source reconciliation.'),
 'FNR-FLD-2018-001': ('VERIFIED_FLOOD_EVENT', 'Independent July 24–25 2018 Maroua 1er (Gakle/Katoual) flood. Cameroon Tribune page states torrential rain in the night of 24–25 July 2018, 187 families affected, and names Maroua 1er/Diamaré.'),
 'FNR-FLD-2019-001': ('POSSIBLE_DUPLICATE', 'Same 1 October 2019 Zina pulse as canonical FNR-FLD-2019-001.'),
 'FNR-FLD-2019-002': ('POSSIBLE_DUPLICATE', 'November situation report follows the October 2019 Logone/Mayo-Danay crisis; no independent onset is established by the submitted row.'),
 'FNR-FLD-2020-002': ('POSSIBLE_DUPLICATE', 'Same 31 August 2020 Maroua bridge-collapse event as canonical FNR-FLD-2020-002.'),
 'FNR-FLD-2020-003': ('POSSIBLE_DUPLICATE', 'Same 11–12 September 2020 Mayo-Danay/Mayo-Kani episode as canonical FNR-FLD-2020-003.'),
 'FNR-FLD-2021-001': ('POSSIBLE_DUPLICATE', 'Same July 2021 Seradoumda/Mayo-Sava episode as canonical FLD-CMR-2021-001.'),
 'FNR-FLD-2022-001': ('POSSIBLE_DUPLICATE', 'Situation Note 1 is an early report within canonical 2022 episode FLD-CMR-2022-001.'),
 'FNR-FLD-2022-002': ('POSSIBLE_DUPLICATE', 'Situation Note 3 is a later report within canonical 2022 episode FLD-CMR-2022-001.'),
 'FNR-FLD-2023-002': ('POSSIBLE_DUPLICATE', 'November 2023 report is already represented by canonical FLD-CMR-2023-001.'),
 'FNR-FLD-2024-001': ('POSSIBLE_DUPLICATE', 'MDRCM039 early-period report is supporting evidence for canonical FLD-CMR-2024-001.'),
 'FNR-FLD-2024-002': ('POSSIBLE_DUPLICATE', 'October 2024 OCHA report is supporting evidence for canonical FLD-CMR-2024-001.'),
 'FNR-FLD-2025-001': ('POSSIBLE_DUPLICATE', 'MDRCM039 update locality cluster is within canonical FNR-FLD-2025-001.'),
 'FNR-FLD-2025-002': ('POSSIBLE_DUPLICATE', 'MDRCM039 update locality cluster is within canonical FNR-FLD-2025-001.'),
 'FNR-FLD-2025-003': ('POSSIBLE_DUPLICATE', 'MDRCM039 update locality cluster is within canonical FNR-FLD-2025-001.'),
 'FNR-FLD-2025-005': ('POSSIBLE_DUPLICATE', 'October 2025 OCHA report matches canonical FNR-FLD-2025-002 footprint/window.'),
}

audit_rows = []
for _, r in in_window.iterrows():
    status, rationale = decisions.get(r.canonical_event_id, ('FLOOD_EVIDENCE_NEEDS_DATE', 'No final reconciliation rule available.'))
    audit_rows.append({
        'source_event_id': r.canonical_event_id,
        'event_start_date': r.event_start_date,
        'event_end_date': r.event_end_date,
        'locality_name': r.locality_name,
        'division': r.division,
        'source_document_url': r.source_document_url,
        'source_verification_status': 'SOURCE_ACCESSIBLE_OR_PRIOR_AUDIT' if status != 'VERIFIED_FLOOD_EVENT' else 'SOURCE_VERIFIED',
        'final_status': status,
        'independent_episode': status == 'VERIFIED_FLOOD_EVENT',
        'rationale': rationale,
    })
pd.DataFrame(audit_rows).to_csv(out / 'farnorth_30_catalogue_verification_audit.csv', index=False)

canon = pd.read_csv(canon_path)
row = in_window[in_window.canonical_event_id.eq('FNR-FLD-2018-001')].iloc[0].drop(labels=['_year']).to_dict()
if not canon.canonical_event_id.eq('FNR-FLD-2018-001').any():
    canon = pd.concat([canon, pd.DataFrame([row])], ignore_index=True)
canon.to_csv(canon_path, index=False)

summary = f'''# Far North region only — 30-row catalogue reconciliation\n\n- Submitted rows: {len(d)}\n- In environmental window (2015–2025): {len(in_window)} (the file contains 16, not 20, in-window rows)\n- Outside window (historical narrative only): {len(outside)}\n- Newly promoted independent episode: 1 (FNR-FLD-2018-001)\n- Existing canonical catalogue after merge: {len(canon)} independent episodes\n- Duplicate/continuation candidates retained as supporting evidence: {sum(v[0] == 'POSSIBLE_DUPLICATE' for v in decisions.values())}\n\nThe 2018 source is Cameroon Tribune (26 Aug 2018): it explicitly reports torrential rain during the night of 24–25 July 2018, 187 affected families, and Maroua 1er/Diamaré (Gakle and Katoual). The other in-window rows are sitrep/update views of already-catalogued episodes and were not counted again.\n\nReadiness Gate: still below the 30-episode classifier threshold; do not train a supervised classifier.\n'''
(out / 'farnorth_30_catalogue_reconciliation_summary.md').write_text(summary)
print(summary)

if __name__ == '__main__':
    pass
