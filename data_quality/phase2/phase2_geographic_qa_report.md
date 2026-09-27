# Phase 2 Geographic QA Report

## Inspection baseline

The supplied workspace contained no separate Phase-2 CSV. The input was the Phase-1 operational CSV, which had **9** events (not 8) and blank latitude/longitude fields. The instructions also enumerate those same 9 events; this QA therefore reviews all 9 without silently deleting one.

Initial findings: 9 missing latitude values; 9 missing longitude values; 3 blank localities; no pre-existing coordinate basis/source/method fields; and no coordinates available to test for out-of-Cameroon placement.

## QA outcome

- Events reviewed: **9**
- Passed: **5**
- Passed with reduced geographic precision: **3**
- Proxy-only: **0**
- Needs review: **1**
- Failed: **0**

## Coordinate validation

All populated coordinates are numeric, within global latitude/longitude bounds, and within a Cameroon plausibility envelope (latitude 1.5–13.5, longitude 8.0–16.5).

## Event decisions and modifications

- `FLD-CMR-2019-001`: **blank latitude/longitude/locality-resolution fields from Phase 1 → 12.083333, 14.833333; RESOLVED_DIVISION_REFERENCE; DIVISION**. No event locality is supported. The GNS administrative reference is retained as a division-level proxy, not asserted to be a geometric polygon centroid. Source: Geographic Names Server administrative feature for Logone-et-Chari (via Wikidata Q576311): https://www.wikidata.org/wiki/Q576311
- `FLD-CMR-2020-001`: **blank latitude/longitude/locality-resolution fields from Phase 1 → 12.08009, 15.03236; RESOLVED_LOCALITY; LOCALITY**. Source confirms Kousseri in Logone-et-Chari, Far North, and publishes GPS E 15.03236, N 12.08009. Source: Mairies du Cameroun, Kousseri municipal profile: https://mairies-du-cameroun.org/index.php/en/collectivites-territoriales/carte-communale/extreme-nord/kousseri
- `FLD-CMR-2022-001`: **blank latitude/longitude/locality-resolution fields from Phase 1 → NULL, NULL; UNRESOLVED_MULTI_DIVISION; UNRESOLVED**. No arithmetic-mean or other synthetic coordinate was created. An explicit Phase-3 proxy-grid methodology is required before this multi-division episode can be used. Source: Phase 1 OCHA evidence identifies Mayo-Danay; Logone-et-Chari; Mayo-Tsanaga, but no single event location.
- `FLD-CMR-2024-001`: **blank latitude/longitude/locality-resolution fields from Phase 1 → 12.08009, 15.03236; RESOLVED_LOCALITY_AREA; LOCALITY_AREA**. Original locality is ‘Kousseri area’. Coordinates are a Kousseri area reference, not an observed flood point or a claim that all affected divisions flooded at Kousseri. Source: Mairies du Cameroun, Kousseri municipal profile: https://mairies-du-cameroun.org/index.php/en/collectivites-territoriales/carte-communale/extreme-nord/kousseri
- `FLD-CMR-2023-001`: **blank latitude/longitude/locality-resolution fields from Phase 1 → 12.775149, 14.553282; RESOLVED_LOCALITY; LOCALITY**. Administrative hierarchy confirmed as Blangoua → Logone-et-Chari → Far North. Coordinate is the named locality reference. Source: GeoNames Blangoua/Blangwa populated-place record (ID 2596834); Cameroon NIS nomenclature confirms Blangoua in Logone-et-Chari: https://stat.cm/nada/index.php/catalog/166/download/1380
- `FLD-CMR-2023-002`: **blank latitude/longitude/locality-resolution fields from Phase 1 → 4.02356, 9.20607; RESOLVED_LOCALITY; LOCALITY**. Limbe is retained as provided; it is the Fako administrative seat in South-West. Coordinate is a locality reference. Source: GeoNames Limbe populated-place record (ID 2229411): https://www.geonames.org/2229411/limbe.html
- `FLD-CMR-2022-002`: **blank latitude/longitude/locality-resolution fields from Phase 1 → 4.166667, 9.166667; RESOLVED_DIVISION_REFERENCE; DIVISION**. No event locality is supported. The named Fako Division reference point is retained; it is not an exact flood point or a computed polygon centroid. Source: GeoNames Fako Division administrative record (ID 2231710): https://www.geonames.org/2231710/fako.html
- `FLD-CMR-2021-001`: **blank latitude/longitude/locality-resolution fields from Phase 1 → 10.98767, 14.19319; RESOLVED_LOCALITY; LOCALITY**. Normalized locality to ‘Sera Doumda’; original Phase 1 spelling ‘Seradoumda’ is preserved in original_locality. Government sources place it in Mora, Mayo-Sava, Far North. Source: GeoNames Sera Doumda record (ID 2222091), surfaced through Mapcarta: https://mapcarta.com/16789860; Cameroon ARMP confirms Séradoumda in Mora, Mayo-Sava: https://armp.cm/details?id_publication=54213&type_publication=AO
- `FLD-CMR-2017-001`: **blank latitude/longitude/locality-resolution fields from Phase 1 → 11.26235, 14.96529; RESOLVED_LOCALITY; LOCALITY**. Original locality ‘Zina subdivision’ normalized to Zina. The coordinate source is a locality gazetteer; NIS confirms the administrative hierarchy. No competing coordinate was substituted without a stronger locality coordinate source. Source: DB-City Zina locality record: https://fr.db-city.com/Cameroun--Extr%C3%AAme-Nord--Logone-et-Chari--Zina; Cameroon NIS nomenclature confirms Zina in Logone-et-Chari: https://stat.cm/nada/index.php/catalog/166/download/1380

## Geographic grouping

- LOCALITY: FLD-CMR-2020-001, FLD-CMR-2023-001, FLD-CMR-2023-002, FLD-CMR-2021-001, FLD-CMR-2017-001
- LOCALITY_AREA: FLD-CMR-2024-001
- DIVISION: FLD-CMR-2019-001, FLD-CMR-2022-002
- UNRESOLVED: FLD-CMR-2022-001

## Remaining uncertainty and ERA5 readiness

`FLD-CMR-2022-001` covers three divisions and has no event-specific point. No synthetic multi-division proxy was created because the supplied methodology does not explicitly authorize proxy extraction. It remains `NOT_READY` with blank coordinates. All other rows use a documented locality, locality-area, or division-reference coordinate and are suitable for the stated nearest-grid-point method at their declared precision.

## Recommendation

**PHASE 2 STATUS: NOT COMPLETE.** The sole blocker is `FLD-CMR-2022-001`: approve and document a Phase-3 multi-division proxy methodology, or retain the event as excluded from coordinate-dependent Phase-3 extraction. No ERA5 data was downloaded or processed.
