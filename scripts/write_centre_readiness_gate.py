#!/usr/bin/env python3
"""Write an explicit, non-negotiable readiness-gate result for Centre data."""
from pathlib import Path
import pandas as pd

ROOT = Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT = ROOT / 'h2oai-flood-intelligence-agent-main' / 'data_quality' / 'centre_consolidation'


def main() -> None:
    canonical = pd.read_csv(OUT / 'canonical_flood_events.csv')
    audit = pd.read_csv(OUT / 'centre_evidence_verification_audit.csv')
    scanned_files = pd.read_csv(OUT / 'centre_evidence_search_scanned_files.csv')
    lookup = pd.read_csv(OUT / 'locality_spatial_lookup.csv')
    unreadable = pd.read_csv(OUT / 'era5_unreadable_files.csv')
    glofas = pd.read_csv(OUT / 'phase_a_glofas_inventory.csv')
    features = pd.read_parquet(OUT / 'centre_ml_feature_table_unlabelled.parquet')
    verified = canonical[canonical.event_status.eq('VERIFIED_FLOOD_EVENT')]
    positive_divisions = verified.groupby('division').size().rename('canonical_episodes').reset_index()
    positive_divisions.to_csv(OUT / 'readiness_gate_positive_division_coverage.csv', index=False)
    distinct_localities = verified.locality_name.nunique()
    distinct_years = pd.to_datetime(verified.event_start_date).dt.year.nunique() if not verified.empty else 0
    event_rows = []
    for event in verified.itertuples(index=False):
        feature = features[(features.locality_name == event.locality_name) & (features.date == pd.Timestamp(event.event_start_date))]
        event_rows.append({
            'canonical_event_id': event.canonical_event_id, 'locality': event.locality_name,
            'event_date': event.event_start_date, 'feature_rows': len(feature),
            'complete_feature_rows': int(feature.data_completeness_flag.eq('COMPLETE').sum()),
        })
    event_check = pd.DataFrame(event_rows)
    event_check.to_csv(OUT / 'readiness_gate_event_feature_check.csv', index=False)
    dem_unavailable = lookup.dem_status.str.contains('UNAVAILABLE', na=False).all()
    failures = []
    if dem_unavailable:
        failures.append('DEM gate failed: the only current GeoTIFF is truncated, so elevation and slope are unavailable for all localities.')
    if len(verified) < 2:
        failures.append(f'Label/training gate failed: only {len(verified)} verified episode exists. At least two chronologically distinct verified episodes are required so both train and test contain a positive event.')
    if event_check.empty or event_check.complete_feature_rows.sum() != len(verified):
        failures.append('Feature-coverage gate failed: at least one verified event lacks a complete locality-day environmental feature row.')
    if not unreadable.empty:
        failures.append(f'ERA5 integrity gate failed: {len(unreadable)} unreadable files remain.')
    gap_string = str(glofas.glofas_year_gaps_vs_2015_2025.dropna().iloc[0]) if glofas.glofas_year_gaps_vs_2015_2025.notna().any() else ''
    if gap_string:
        failures.append(f'GloFAS coverage gate failed: year gaps remain: {gap_string}.')
    decision = 'FAIL — DO NOT TRAIN' if failures else 'PASS — PROCEED TO PHASE E/F'
    event_table = 'No verified events.' if event_check.empty else ('| canonical_event_id | locality | event_date | feature_rows | complete_feature_rows |\n|---|---|---|---:|---:|\n' + '\n'.join(
        f"| {row.canonical_event_id} | {row.locality} | {row.event_date} | {row.feature_rows} | {row.complete_feature_rows} |"
        for row in event_check.itertuples(index=False)
    ))
    next_required_work = (
        'Proceed with the explicitly limited Phase F pilot and Phase G knowledge-base refresh. '
        f'This is still only a {len(verified)}-episode dataset: expand the independently verified catalogue '
        'before treating any model score as operationally reliable.'
        if not failures else
        'Source-verify at least one more distinct Centre flood episode with a date/window and a locality/footprint. '
        'Do not count duplicate or update records as new events. Once there are enough independent positive episodes, '
        'create same-locality negatives and use a chronological split with a positive in each partition.'
    )
    report = f"""# Centre consolidation readiness gate

## Decision

**{decision}**

## Evidence-search result

- Files searched: {len(scanned_files):,} across `relief_web-datasets/` and `scrapers-data/`, including `apify_yaounde/` and the social exports.
- Candidate units reported: {len(audit):,}. The complete candidate-by-candidate decision table is `centre_evidence_verification_audit.csv`.
- Decisions: {audit.verification_status.value_counts().to_dict()}.
- Canonical verified episodes: {len(verified)}.
- Distinct positive localities: {distinct_localities}; distinct positive years: {distinct_years}.
- Per-division positive coverage: {positive_divisions.to_dict('records')}.

## Environmental re-check

- ERA5: 132/132 readable; unreadable files remaining: {len(unreadable)}.
- GloFAS: confirmed 2015–2025 coverage; year gap list: `{gap_string or 'none'}`.
- Spatial matches above tolerance: ERA5 {(lookup.era5_match_distance_deg > .07).sum()}/123, GloFAS {(lookup.glofas_match_distance_deg > .03).sum()}/123. These are flagged, not silently corrected.
- DEM: {lookup.dem_status.iloc[0]}.

## Verified-event feature coverage

{event_table}

## Gate failures

""" + '\n'.join(f'- {failure}' for failure in failures) + """

## Next required work

""" + next_required_work + """
"""
    (OUT / 'centre_readiness_gate.md').write_text(report, encoding='utf-8')
    print(decision)


if __name__ == '__main__':
    main()
