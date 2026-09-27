"""Freeze conservative Phase-2 geographic QA output from the Phase-1 catalogue.

No ERA5 request is made here.  Coordinates are only added where a named
locality or administrative reference has a reproducible cited source.
"""

from __future__ import annotations

import csv
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
INPUT = PROJECT / "data_quality" / "phase1" / "clean_flood_events.csv"
OUT = PROJECT / "data_quality" / "phase2"
OUT.mkdir(parents=True, exist_ok=True)

with INPUT.open(encoding="utf-8", newline="") as file:
    phase1_rows = list(csv.DictReader(file))

# Sources were checked on 2026-08-26.  A locality coordinate represents the
# named locality, never the exact point at which flooding was observed.
QA = {
    "FLD-CMR-2019-001": {
        "latitude": "12.083333", "longitude": "14.833333",
        "geographic_resolution_status": "RESOLVED_DIVISION_REFERENCE",
        "coordinate_basis": "DIVISION_REFERENCE_POINT",
        "geographic_confidence": "MEDIUM",
        "geographic_source": "Geographic Names Server administrative feature for Logone-et-Chari (via Wikidata Q576311): https://www.wikidata.org/wiki/Q576311",
        "geographic_precision": "DIVISION", "era5_extraction_method": "NEAREST_GRID_POINT",
        "geographic_qa_status": "PASSED_WITH_LOW_PRECISION", "phase2_ready_for_era5": "true",
        "geographic_qa_notes": "No event locality is supported. The GNS administrative reference is retained as a division-level proxy, not asserted to be a geometric polygon centroid.",
    },
    "FLD-CMR-2020-001": {
        "latitude": "12.08009", "longitude": "15.03236",
        "geographic_resolution_status": "RESOLVED_LOCALITY",
        "coordinate_basis": "LOCALITY_COORDINATES",
        "geographic_confidence": "HIGH",
        "geographic_source": "Mairies du Cameroun, Kousseri municipal profile: https://mairies-du-cameroun.org/index.php/en/collectivites-territoriales/carte-communale/extreme-nord/kousseri",
        "geographic_precision": "LOCALITY", "era5_extraction_method": "NEAREST_GRID_POINT",
        "geographic_qa_status": "PASSED", "phase2_ready_for_era5": "true",
        "geographic_qa_notes": "Source confirms Kousseri in Logone-et-Chari, Far North, and publishes GPS E 15.03236, N 12.08009.",
    },
    "FLD-CMR-2022-001": {
        "latitude": "", "longitude": "",
        "geographic_resolution_status": "UNRESOLVED_MULTI_DIVISION",
        "coordinate_basis": "NO_EVENT_SPECIFIC_LOCATION_OR_APPROVED_PROXY",
        "geographic_confidence": "LOW",
        "geographic_source": "Phase 1 OCHA evidence identifies Mayo-Danay; Logone-et-Chari; Mayo-Tsanaga, but no single event location.",
        "geographic_precision": "UNRESOLVED", "era5_extraction_method": "NOT_READY",
        "geographic_qa_status": "NEEDS_REVIEW", "phase2_ready_for_era5": "false",
        "geographic_qa_notes": "No arithmetic-mean or other synthetic coordinate was created. An explicit Phase-3 proxy-grid methodology is required before this multi-division episode can be used.",
    },
    "FLD-CMR-2024-001": {
        "latitude": "12.08009", "longitude": "15.03236",
        "geographic_resolution_status": "RESOLVED_LOCALITY_AREA",
        "coordinate_basis": "LOCALITY_AREA_REFERENCE_COORDINATES",
        "geographic_confidence": "MEDIUM",
        "geographic_source": "Mairies du Cameroun, Kousseri municipal profile: https://mairies-du-cameroun.org/index.php/en/collectivites-territoriales/carte-communale/extreme-nord/kousseri",
        "geographic_precision": "LOCALITY_AREA", "era5_extraction_method": "NEAREST_GRID_POINT",
        "geographic_qa_status": "PASSED_WITH_LOW_PRECISION", "phase2_ready_for_era5": "true",
        "geographic_qa_notes": "Original locality is ‘Kousseri area’. Coordinates are a Kousseri area reference, not an observed flood point or a claim that all affected divisions flooded at Kousseri.",
    },
    "FLD-CMR-2023-001": {
        "latitude": "12.775149", "longitude": "14.553282",
        "geographic_resolution_status": "RESOLVED_LOCALITY",
        "coordinate_basis": "LOCALITY_COORDINATES",
        "geographic_confidence": "MEDIUM",
        "geographic_source": "GeoNames Blangoua/Blangwa populated-place record (ID 2596834); Cameroon NIS nomenclature confirms Blangoua in Logone-et-Chari: https://stat.cm/nada/index.php/catalog/166/download/1380",
        "geographic_precision": "LOCALITY", "era5_extraction_method": "NEAREST_GRID_POINT",
        "geographic_qa_status": "PASSED", "phase2_ready_for_era5": "true",
        "geographic_qa_notes": "Administrative hierarchy confirmed as Blangoua → Logone-et-Chari → Far North. Coordinate is the named locality reference.",
    },
    "FLD-CMR-2023-002": {
        "latitude": "4.02356", "longitude": "9.20607",
        "geographic_resolution_status": "RESOLVED_LOCALITY",
        "coordinate_basis": "LOCALITY_COORDINATES",
        "geographic_confidence": "MEDIUM",
        "geographic_source": "GeoNames Limbe populated-place record (ID 2229411): https://www.geonames.org/2229411/limbe.html",
        "geographic_precision": "LOCALITY", "era5_extraction_method": "NEAREST_GRID_POINT",
        "geographic_qa_status": "PASSED", "phase2_ready_for_era5": "true",
        "geographic_qa_notes": "Limbe is retained as provided; it is the Fako administrative seat in South-West. Coordinate is a locality reference.",
    },
    "FLD-CMR-2022-002": {
        "latitude": "4.166667", "longitude": "9.166667",
        "geographic_resolution_status": "RESOLVED_DIVISION_REFERENCE",
        "coordinate_basis": "DIVISION_REFERENCE_POINT",
        "geographic_confidence": "MEDIUM",
        "geographic_source": "GeoNames Fako Division administrative record (ID 2231710): https://www.geonames.org/2231710/fako.html",
        "geographic_precision": "DIVISION", "era5_extraction_method": "NEAREST_GRID_POINT",
        "geographic_qa_status": "PASSED_WITH_LOW_PRECISION", "phase2_ready_for_era5": "true",
        "geographic_qa_notes": "No event locality is supported. The named Fako Division reference point is retained; it is not an exact flood point or a computed polygon centroid.",
    },
    "FLD-CMR-2021-001": {
        "latitude": "10.98767", "longitude": "14.19319",
        "geographic_resolution_status": "RESOLVED_LOCALITY",
        "coordinate_basis": "LOCALITY_COORDINATES",
        "geographic_confidence": "MEDIUM",
        "geographic_source": "GeoNames Sera Doumda record (ID 2222091), surfaced through Mapcarta: https://mapcarta.com/16789860; Cameroon ARMP confirms Séradoumda in Mora, Mayo-Sava: https://armp.cm/details?id_publication=54213&type_publication=AO",
        "geographic_precision": "LOCALITY", "era5_extraction_method": "NEAREST_GRID_POINT",
        "geographic_qa_status": "PASSED", "phase2_ready_for_era5": "true",
        "geographic_qa_notes": "Normalized locality to ‘Sera Doumda’; original Phase 1 spelling ‘Seradoumda’ is preserved in original_locality. Government sources place it in Mora, Mayo-Sava, Far North.",
    },
    "FLD-CMR-2017-001": {
        "latitude": "11.26235", "longitude": "14.96529",
        "geographic_resolution_status": "RESOLVED_LOCALITY",
        "coordinate_basis": "LOCALITY_COORDINATES",
        "geographic_confidence": "MEDIUM",
        "geographic_source": "DB-City Zina locality record: https://fr.db-city.com/Cameroun--Extr%C3%AAme-Nord--Logone-et-Chari--Zina; Cameroon NIS nomenclature confirms Zina in Logone-et-Chari: https://stat.cm/nada/index.php/catalog/166/download/1380",
        "geographic_precision": "LOCALITY", "era5_extraction_method": "NEAREST_GRID_POINT",
        "geographic_qa_status": "PASSED", "phase2_ready_for_era5": "true",
        "geographic_qa_notes": "Original locality ‘Zina subdivision’ normalized to Zina. The coordinate source is a locality gazetteer; NIS confirms the administrative hierarchy. No competing coordinate was substituted without a stronger locality coordinate source.",
    },
}

fieldnames = [
    "event_id", "event_date", "event_end_date", "region", "division", "locality", "original_locality",
    "latitude", "longitude", "severity", "confidence", "source", "geographic_resolution_status",
    "coordinate_basis", "geographic_confidence", "geographic_source", "geographic_precision",
    "era5_extraction_method", "geographic_qa_status", "geographic_qa_notes", "phase2_ready_for_era5",
]

final_rows = []
for original in phase1_rows:
    row = dict(original)
    event_id = row["event_id"]
    details = QA[event_id]
    row["original_locality"] = row["locality"]
    if event_id == "FLD-CMR-2021-001":
        row["locality"] = "Sera Doumda"
    if event_id == "FLD-CMR-2017-001":
        row["locality"] = "Zina"
    row.update(details)
    final_rows.append({field: row.get(field, "") for field in fieldnames})

with (OUT / "clean_flood_events_phase2_final.csv").open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(final_rows)

by_status = {status: sum(row["geographic_qa_status"] == status for row in final_rows) for status in ("PASSED", "PASSED_WITH_LOW_PRECISION", "PROXY_ONLY", "NEEDS_REVIEW", "FAILED")}
with (OUT / "phase2_geographic_qa_report.md").open("w", encoding="utf-8") as report:
    report.write("# Phase 2 Geographic QA Report\n\n")
    report.write("## Inspection baseline\n\n")
    report.write("The supplied workspace contained no separate Phase-2 CSV. The input was the Phase-1 operational CSV, which had **9** events (not 8) and blank latitude/longitude fields. The instructions also enumerate those same 9 events; this QA therefore reviews all 9 without silently deleting one.\n\n")
    report.write("Initial findings: 9 missing latitude values; 9 missing longitude values; 3 blank localities; no pre-existing coordinate basis/source/method fields; and no coordinates available to test for out-of-Cameroon placement.\n\n")
    report.write("## QA outcome\n\n")
    report.write(f"- Events reviewed: **{len(final_rows)}**\n")
    report.write(f"- Passed: **{by_status['PASSED']}**\n")
    report.write(f"- Passed with reduced geographic precision: **{by_status['PASSED_WITH_LOW_PRECISION']}**\n")
    report.write(f"- Proxy-only: **{by_status['PROXY_ONLY']}**\n")
    report.write(f"- Needs review: **{by_status['NEEDS_REVIEW']}**\n")
    report.write(f"- Failed: **{by_status['FAILED']}**\n\n")
    report.write("## Coordinate validation\n\n")
    for row in final_rows:
        if row["latitude"] and row["longitude"]:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            valid = -90 <= lat <= 90 and -180 <= lon <= 180 and 1.5 <= lat <= 13.5 and 8.0 <= lon <= 16.5
            assert valid, f"coordinate outside expected Cameroon range: {row['event_id']}"
    report.write("All populated coordinates are numeric, within global latitude/longitude bounds, and within a Cameroon plausibility envelope (latitude 1.5–13.5, longitude 8.0–16.5).\n\n")
    report.write("## Event decisions and modifications\n\n")
    for row in final_rows:
        old = "blank latitude/longitude/locality-resolution fields from Phase 1"
        new = f"{row['latitude'] or 'NULL'}, {row['longitude'] or 'NULL'}; {row['geographic_resolution_status']}; {row['geographic_precision']}"
        report.write(f"- `{row['event_id']}`: **{old} → {new}**. {row['geographic_qa_notes']} Source: {row['geographic_source']}\n")
    report.write("\n## Geographic grouping\n\n")
    for label in ("LOCALITY", "LOCALITY_AREA", "DIVISION", "UNRESOLVED"):
        members = [r["event_id"] for r in final_rows if r["geographic_precision"] == label]
        report.write(f"- {label}: {', '.join(members) if members else 'None'}\n")
    report.write("\n## Remaining uncertainty and ERA5 readiness\n\n")
    report.write("`FLD-CMR-2022-001` covers three divisions and has no event-specific point. No synthetic multi-division proxy was created because the supplied methodology does not explicitly authorize proxy extraction. It remains `NOT_READY` with blank coordinates. All other rows use a documented locality, locality-area, or division-reference coordinate and are suitable for the stated nearest-grid-point method at their declared precision.\n\n")
    report.write("## Recommendation\n\n")
    report.write("**PHASE 2 STATUS: NOT COMPLETE.** The sole blocker is `FLD-CMR-2022-001`: approve and document a Phase-3 multi-division proxy methodology, or retain the event as excluded from coordinate-dependent Phase-3 extraction. No ERA5 data was downloaded or processed.\n")

print(f"Wrote {len(final_rows)} rows to {OUT}")
