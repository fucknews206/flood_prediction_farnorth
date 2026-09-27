# Far North region only — GloFAS event join report

The GloFAS loader now normalizes each `valid_time` by subtracting one day (the files use 02 January through 01 January hydrological-year coordinates) before looking up event dates and lags. The inspectable output is `farnorth_event_discharge_features.csv`.

Of 33 catalogue events in 2005–2025, 29 have non-null discharge, lag1, lag3 and lag7 values. Four cannot be joined because their catalogue footprint has no exact locality in `gazetteer_farnorth.csv`, not because of a GloFAS date gap:

* FNR-FLD-2013-002 — Dougui / Kai-Kai description
* FNR-FLD-2021-001 — Seradoumda; Mora and Makary roads
* FNR-FLD-2021-002 — division-level UNKNOWN footprint
* FNR-FLD-2025-005 — truncated arrondissement-level UNKNOWN footprint

The confirmed full-feature count is therefore **29**, below the 30-event training threshold. Classifier training is not started; the rules-based susceptibility/threshold system remains the operational deliverable. Resolve the four locality footprints (or explicitly exclude them) before another training attempt.
