# Far North region only — Phase 0, Phase A, and Readiness Gate

## Decision

**PASS — PROCEED TO PHASE B**

## Exact supplied-path discovery

- ERA5-Land: 132 files visible in `ERA5-datasets/Far_North/`.
- GloFAS: 22 files opened. By actual bounds, 11 are Far North (latitude 9.525–13.175), while 11 are Centre-only (latitude 3.525–4.975) and excluded.
- CHIRPS: 2 files visible in `CHIRPS-datasets/far-north/`.
- Gazetteer: 3860 locality rows; 3860 unique name/coordinate rows.
- DEM/slope: 3860 rows.
- HydroBasins/HydroRIVERS, ReliefWeb, and scrapers directories are visible but were not processed after the environmental prerequisite failure.

## File identity/readability

- ERA5 readable: 132/132.
- Far North GloFAS readable: 11/11; annual coverage [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]; missing years none.
- CHIRPS rainfall columns: ['first', 'first'].
- DEM elevation nulls: 0/3860; slope nulls: 0/3860.

## Readiness Gate result

- Total positive rows: **0 (not constructible)**.
- Distinct localities: **0 (not constructible)**.
- Distinct years: **0 (not constructible)**.
- Positives per division: **none; label join was not run**.

## Blocking failures



The supplied CHIRPS and DEM files must be corrected before Phase B standardization, Phase C spatial join, Phase D features, Phase E labels, or the exhaustive flood-evidence pass can produce a valid Far North training dataset. No model, predictions, or sample results were produced. This is **Far North region only**.
