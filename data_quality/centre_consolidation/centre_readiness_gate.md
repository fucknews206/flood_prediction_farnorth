# Centre consolidation readiness gate

## Decision

**PASS — PROCEED TO PHASE E/F**

## Evidence-search result

- Files searched: 123 across `relief_web-datasets/` and `scrapers-data/`, including `apify_yaounde/` and the social exports.
- Candidate units reported: 400. The complete candidate-by-candidate decision table is `centre_evidence_verification_audit.csv`.
- Decisions: {'FLOOD_EVIDENCE_NEEDS_DATE': 229, 'GENERAL_FLOOD_REFERENCE': 127, 'POSSIBLE_DUPLICATE': 23, 'VERIFIED_FLOOD_EVENT': 15, 'FLOOD_EVIDENCE_NEEDS_LOCATION': 6}.
- Canonical verified episodes: 4.
- Distinct positive localities: 4; distinct positive years: 4.
- Per-division positive coverage: [{'division': 'Lékié', 'canonical_episodes': 1}, {'division': 'Mfoundi', 'canonical_episodes': 3}].

## Environmental re-check

- ERA5: 132/132 readable; unreadable files remaining: 0.
- GloFAS: confirmed 2015–2025 coverage; year gap list: `none`.
- Spatial matches above tolerance: ERA5 9/123, GloFAS 12/123. These are flagged, not silently corrected.
- DEM: COMPLETE_GEE_COPERNICUS_DEM_GLO30_LOCALITY_SAMPLE.

## Verified-event feature coverage

| canonical_event_id | locality | event_date | feature_rows | complete_feature_rows |
|---|---|---|---:|---:|
| CTR-FLD-2017-001 | Nkolbisson | 2017-09-12 | 1 | 1 |
| CTR-FLD-2021-001 | Yaoundé VII | 2021-06-07 | 1 | 1 |
| CTR-FLD-2022-001 | Obala | 2022-05-18 | 1 | 1 |
| CTR-FLD-2024-001 | Yaoundé VI | 2024-10-07 | 1 | 1 |

## Gate failures



## Next required work

Proceed with the explicitly limited Phase F pilot and Phase G knowledge-base refresh. This is still only a 4-episode dataset: expand the independently verified catalogue before treating any model score as operationally reliable.
