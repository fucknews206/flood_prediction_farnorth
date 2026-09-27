"""Create conservative Phase-1 Cameroon flood-event handoff files.

The script deliberately does not infer dates, coordinates, impacts, or event
identity from document metadata.  It retains every one of the 75 extracted
candidate records in the audit CSV; only source-supported canonical episodes
are emitted to the operational CSV.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict, Counter
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
DATASET = Path("/home/ongou/Desktop/projects/end-of -year-defence/flood-event-extractor/final_dataset/master_events.json")
OUT = PROJECT / "data_quality" / "phase1"
OUT.mkdir(parents=True, exist_ok=True)

with DATASET.open(encoding="utf-8") as file:
    raw_rows = json.load(file)

by_record: dict[str, list[dict]] = defaultdict(list)
for row in raw_rows:
    by_record[row["event_id"]].append(row)


# Decisions backed by direct review of their cited source pages.  Remaining
# records are deliberately held pending that same page-level review.
DECISIONS = {
    "CMR-FLD-000001": ("EXCLUDE", "", "General flood reference; no individual event is established."),
    "CMR-FLD-000002": ("EXCLUDE", "", "IOM Round 9 reports aggregate climate-related displacement during its survey window; it does not identify an individual flood episode."),
    "CMR-FLD-000003": ("MERGE", "CMR-FLD-000002", "Duplicate evidence bundle for CMR-FLD-000002; not a separate event."),
    "CMR-FLD-000004": ("EXCLUDE", "", "IOM Round 15 reports aggregate displacement causes during its survey window; it does not identify an individual flood episode."),
    "CMR-FLD-000005": ("MERGE", "CMR-FLD-000004", "Duplicate evidence bundle for CMR-FLD-000004; not a separate event."),
    "CMR-FLD-000006": ("KEEP_AS_EVENT", "FLD-CMR-2019-001", "OCHA evidence supports a Far North flood episode; only a September–November reporting window is defensible."),
    "CMR-FLD-000007": ("KEEP_AS_EVENT", "FLD-CMR-2020-001", "OCHA evidence supports flooding since July 2020 in Far North; raw 2020-11-10 is not an event date."),
    "CMR-FLD-000008": ("EXCLUDE", "", "Survey-round aggregate prevalence, not an individual flood event."),
    "CMR-FLD-000009": ("KEEP_AS_EVENT", "FLD-CMR-2022-001", "Primary evidence for the continuing 2022 Far North episode."),
    "CMR-FLD-000010": ("MERGE", "FLD-CMR-2022-001", "September update of the continuing 2022 episode; not a new event."),
    "CMR-FLD-000011": ("MERGE", "FLD-CMR-2022-001", "OCHA 15 November update of the continuing 2022 Far North flooding episode."),
    "CMR-FLD-000012": ("EXCLUDE", "", "Evidence describes flooding in Chad and arrivals into Cameroon, not a Cameroon flood event."),
    "CMR-FLD-000013": ("EXCLUDE", "", "Evidence describes the Chad dike breach, not a separately established Cameroon flood event."),
    "CMR-FLD-000014": ("MERGE", "FLD-CMR-2024-001", "IFRC operation update confirms the 2024 Cameroon flood crisis; UNFPA and UNICEF flash updates identify the Far North episode as beginning in July 2024."),
    "CMR-FLD-000015": ("MERGE", "FLD-CMR-2024-001", "Situation-update evidence for the 2024 Far North rainy-season flood episode."),
    "CMR-FLD-000016": ("MERGE", "FLD-CMR-2024-001", "Impact update for the same 2024 Far North flood episode."),
    "CMR-FLD-000017": ("KEEP_AS_EVENT", "FLD-CMR-2024-001", "OCHA explicitly attributes Far North flooding to the July–September 2024 rainy season."),
    "CMR-FLD-000018": ("MERGE", "FLD-CMR-2024-001", "Impact-table continuation of the OCHA 2024 flood snapshot."),
    "CMR-FLD-000019": ("EXCLUDE", "", "FAO survey shock-prevalence chart, not an individual flood event."),
    "CMR-FLD-000020": ("MERGE", "FLD-CMR-2024-001", "UNICEF/OCHA update of the same 2024 Far North flood episode."),
    "CMR-FLD-000021": ("MERGE", "FLD-CMR-2024-001", "FEWS NET describes heavy rains and flooding during the ongoing 2024 rainy season; raw 2026/2024 dates are rejected."),
    "CMR-FLD-000022": ("MERGE", "FLD-CMR-2024-001", "FEWS NET describes flood-affected households in Mayo-Danay and Diamaré during the 2024 season; raw dates are rejected."),
    "CMR-FLD-000023": ("EXCLUDE", "", "Early Action Protocol for recurrent river-flooding preparedness; it does not document an observed individual flood event."),
    "CMR-FLD-000024": ("MERGE", "FLD-CMR-2024-001", "UNFPA flood-response reference is an update for affected areas in the 2024 Far North episode, not a new dated event."),
    "CMR-FLD-000025": ("KEEP_AS_EVENT", "FLD-CMR-2023-001", "OCHA documents flooding at Blangoua after the Chari overflow, affecting nearly 10,000 people; only November 2023 is defensible."),
    "CMR-FLD-000026": ("EXCLUDE", "", "Source reports villages threatened by river flooding, not a flood occurrence."),
    "CMR-FLD-000027": ("EXCLUDE", "", "FEWS NET outlook projection for 2026, not observed flood-event evidence."),
    "CMR-FLD-000028": ("MERGE", "FLD-CMR-2019-001", "UNICEF response evidence for the 2019 Logone River flooding in Zina and Kai-Kai."),
    "CMR-FLD-000029": ("EXCLUDE", "", "Cross-document generic flood references with no single identifiable event."),
    "CMR-FLD-000030": ("EXCLUDE", "", "Mixed evidence bundle: it combines 2020 Cameroon flooding, 2023 Chad flooding, 2024 response activity, and preparedness material; it is not one event."),
    "CMR-FLD-000031": ("MERGE", "FLD-CMR-2024-001", "Direct impact evidence for the 2024 Far North flooding in Mayo-Danay and Logone-et-Chari."),
    "CMR-FLD-000032": ("EXCLUDE", "", "IOM aggregate refugee displacement statistic; it does not establish an individual flood episode, date, or flood location."),
    "CMR-FLD-000033": ("MERGE", "FLD-CMR-2024-001", "OCHA flood notes identify the 2024 rainy-season event across five Far North divisions."),
    "CMR-FLD-000034": ("EXCLUDE", "", "Mixed 2018, 2022, and 2024 flood/risk statements; it is not one identifiable physical event."),
    "CMR-FLD-000035": ("MERGE", "FLD-CMR-2024-001", "September 2024 OCHA impact update for the same Far North episode."),
    "CMR-FLD-000036": ("EXCLUDE", "", "Cross-episode aggregate evidence from several years; it is not one identifiable flood event."),
    "CMR-FLD-000037": ("MERGE", "FLD-CMR-2024-001", "OCHA total affected-population update for the 2024 Far North episode."),
    "CMR-FLD-000038": ("EXCLUDE", "", "Aggregate displacement-cause statistics, not an individual flood event."),
    "CMR-FLD-000039": ("MERGE", "FLD-CMR-2019-001", "UNICEF identifies the Logone River flooding of Zina and Kai-Kai in the 2019 episode."),
    "CMR-FLD-000040": ("MERGE", "FLD-CMR-2024-001", "Source explicitly dates the 2024 torrential rainfall and seasonal flooding to since July 2024."),
    "CMR-FLD-000041": ("MERGE", "FLD-CMR-2024-001", "Affected-population figure is an update for the documented 2024 Far North episode."),
    "CMR-FLD-000042": ("MERGE", "FLD-CMR-2024-001", "Flood-impact situation analysis is supporting evidence for the 2024 episode."),
    "CMR-FLD-000043": ("EXCLUDE", "", "Response-actor map, not flood-event evidence."),
    "CMR-FLD-000044": ("EXCLUDE", "", "Flooding-risk outlook, not observed flood-event evidence."),
    "CMR-FLD-000045": ("EXCLUDE", "", "Flood-proneness/risk statement, not an observed individual event."),
    "CMR-FLD-000046": ("EXCLUDE", "", "Cross-episode response activity across several documents; not one identifiable event."),
    "CMR-FLD-000047": ("MERGE", "FLD-CMR-2024-001", "October 2024 assistance record for children affected by the same Far North floods."),
    "CMR-FLD-000048": ("MERGE", "FLD-CMR-2024-001", "Flood-affected health-district response is supporting evidence for the 2024 episode."),
    "CMR-FLD-000049": ("MERGE", "FLD-CMR-2024-001", "October 2024 response at a flooded Maga health centre supports the same episode."),
    "CMR-FLD-000050": ("EXCLUDE", "", "Cross-document response aggregate spanning multiple years and episodes; not one event."),
    "CMR-FLD-000051": ("MERGE", "FLD-CMR-2024-001", "Flood-affected schools in Mayo-Danay and Logone-et-Chari are part of the 2024 episode."),
    "CMR-FLD-000052": ("MERGE", "FLD-CMR-2024-001", "2024 UNICEF documentation of a flooded Yagoua neighbourhood supports the same episode."),
    "CMR-FLD-000053": ("EXCLUDE", "", "Flood simulation exercise, not an observed flood event."),
    "CMR-FLD-000054": ("KEEP_AS_EVENT", "FLD-CMR-2021-001", "OCHA's August 2021 humanitarian bulletin explicitly dates flooding affecting more than 2,400 people in Mayo-Sava to July 2021; the October situation report supplies Seradoumda as an affected locality."),
    "CMR-FLD-000055": ("MERGE", "FLD-CMR-2024-001", "Relocation-site evidence for people affected by the 2024 Far North floods."),
    "CMR-FLD-000056": ("EXCLUDE", "", "Forward-looking flood-risk statement, not a flood occurrence."),
    "CMR-FLD-000057": ("EXCLUDE", "", "Response-supply table without an individual flood event."),
    "CMR-FLD-000058": ("MERGE", "FLD-CMR-2024-001", "OCHA documents schools affected by the 2024 floods."),
    "CMR-FLD-000059": ("MERGE", "FLD-CMR-2020-001", "December 2020 response to the same Far North flood episode."),
    "CMR-FLD-000060": ("MERGE", "FLD-CMR-2024-001", "Flood-affected school response in the 2024 Far North episode."),
    "CMR-FLD-000061": ("MERGE", "FLD-CMR-2024-001", "September 2024 OCHA flood-response needs update."),
    "CMR-FLD-000062": ("MERGE", "FLD-CMR-2024-001", "2024 flood-response coordination update, not a separate event."),
    "CMR-FLD-000063": ("MERGE", "FLD-CMR-2020-001", "Source directly ties the impassable Maroua–Kousseri axis to flooding since July 2020."),
    "CMR-FLD-000064": ("EXCLUDE", "", "Generic 2025 reference to flood-affected populations without an identifiable event, date, or footprint."),
    "CMR-FLD-000065": ("KEEP_AS_EVENT", "FLD-CMR-2023-002", "Source explicitly identifies late-July floods and landslides in Limbe, Fako division."),
    "CMR-FLD-000066": ("KEEP_AS_EVENT", "FLD-CMR-2022-002", "OCHA situation report covers 1 August–30 September 2022 and explicitly says heavy rains caused floods in Fako during that reporting period."),
    "CMR-FLD-000067": ("EXCLUDE", "", "Early-intervention protocol for recurrent flooding, not an observed event."),
    "CMR-FLD-000068": ("EXCLUDE", "", "Situation-report overview; it identifies Chad flooding and general Far North hazards, not a Cameroon flood episode."),
    "CMR-FLD-000069": ("MERGE", "FLD-CMR-2024-001", "UNFPA flood-response coordination evidence for Makary and Blangoua in the 2024 episode."),
    "CMR-FLD-000070": ("MERGE", "FLD-CMR-2019-001", "UNICEF initial response to the 2019 Zina and Kai-Kai flooding."),
    "CMR-FLD-000071": ("EXCLUDE", "", "Human-interest/table-of-contents reference to flood victims, not flood-event evidence."),
    "CMR-FLD-000072": ("MERGE", "FLD-CMR-2024-001", "FEWS NET explicitly describes August–September 2024 seasonal flooding across Far North divisions."),
    "CMR-FLD-000073": ("MERGE", "FLD-CMR-2024-001", "Flood-related crop losses are supporting evidence for the 2024 Far North episode."),
    "CMR-FLD-000074": ("KEEP_AS_EVENT", "FLD-CMR-2017-001", "OCHA's September 2017 bulletin describes recent heavy-rain flooding in Zina subdivision, Logone-et-Chari; only September 2017 is retained, not the bulletin publication day."),
    "CMR-FLD-000075": ("MERGE", "FLD-CMR-2022-001", "Flood-ravaged plantations are supporting evidence for the 2022 Mayo-Danay/Mayo-Tsanaga episode."),
}


EVENTS = [
    {
        "event_id": "FLD-CMR-2019-001", "event_date": "2019-09", "event_end_date": "2019-11",
        "region": "Far North", "division": "Logone-et-Chari", "locality": "",
        "latitude": "", "longitude": "", "severity": "", "confidence": "MEDIUM",
        "source": "Cameroon humanitarian bulletin, OCHA (September–November 2019)",
        "source_ids": "CMR-FLD-000006", "documents": "OCHA humanitarian bulletin (September–November 2019)",
        "pages": "", "date_note": "Month-level reporting window only; no exact flood day is asserted.",
        "geo_note": "Far North and Logone-et-Chari are supported; no point coordinate is asserted.",
    },
    {
        "event_id": "FLD-CMR-2020-001", "event_date": "2020-07", "event_end_date": "",
        "region": "Far North", "division": "Logone-et-Chari", "locality": "Kousseri",
        "latitude": "", "longitude": "", "severity": "", "confidence": "MEDIUM",
        "source": "OCHA humanitarian report, updated 7 January 2021",
        "source_ids": "CMR-FLD-000007", "documents": "OCHA humanitarian report (updated 7 January 2021)",
        "pages": "", "date_note": "Source says flooding had occurred since July 2020; publication/update date is not used as the event date.",
        "geo_note": "Far North, Logone-et-Chari, and Kousseri are directly associated with the flood evidence.",
    },
    {
        "event_id": "FLD-CMR-2022-001", "event_date": "2022-08", "event_end_date": "2022-11",
        "region": "Far North", "division": "Mayo-Danay; Logone-et-Chari; Mayo-Tsanaga", "locality": "",
        "latitude": "", "longitude": "", "severity": "", "confidence": "HIGH",
        "source": "OCHA Far North flood information notes, August–November 2022",
        "source_ids": "CMR-FLD-000009; CMR-FLD-000010; CMR-FLD-000011",
        "documents": "OCHA flood updates (August 2022; September 2022; 15 November 2022)",
        "pages": "1", "date_note": "Month-level episode window reconstructed only from consecutive OCHA situation updates; no exact start or end day is asserted.",
        "geo_note": "Divisions are preserved only where named in the source updates; no point coordinate is asserted.",
    },
    {
        "event_id": "FLD-CMR-2024-001", "event_date": "2024-07", "event_end_date": "2024-09",
        "region": "Far North", "division": "Mayo-Danay; Logone-et-Chari", "locality": "Kousseri area",
        "latitude": "", "longitude": "", "severity": "", "confidence": "HIGH",
        "source": "OCHA, Cameroon: Far North flood overview, 18 October 2024",
        "source_ids": "CMR-FLD-000015; CMR-FLD-000016; CMR-FLD-000017; CMR-FLD-000018; CMR-FLD-000020",
        "documents": "CMR_Inondations_26102024.pdf; Cameroon Humanitarian Flash Update 3; Cameroon Humanitarian Flash Update 6",
        "pages": "1–2", "date_note": "OCHA explicitly identifies the July–September 2024 rainy season as causing the flooding; the October update date is not used as an event date.",
        "geo_note": "OCHA associates the episode with Far North, particularly Mayo-Danay and Logone-et-Chari; Kousseri area is specifically mentioned.",
    },
    {
        "event_id": "FLD-CMR-2023-001", "event_date": "2023-11", "event_end_date": "",
        "region": "Far North", "division": "Logone-et-Chari", "locality": "Blangoua",
        "latitude": "", "longitude": "", "severity": "", "confidence": "MEDIUM",
        "source": "OCHA Far North situation report, November 2023",
        "source_ids": "CMR-FLD-000025", "documents": "OCHA_SITREP_Extrême Nord_Novembre 2023 inputs VF.pdf",
        "pages": "1", "date_note": "Only the month of the November 2023 source is supported; no exact flood day is asserted.",
        "geo_note": "The source associates the Chari overflow with Blangoua in Logone-et-Chari, Far North.",
    },
    {
        "event_id": "FLD-CMR-2023-002", "event_date": "2023-07", "event_end_date": "",
        "region": "South-West", "division": "Fako", "locality": "Limbe",
        "latitude": "", "longitude": "", "severity": "", "confidence": "MEDIUM",
        "source": "Cameroon North-West/South-West situation report, August 2023",
        "source_ids": "CMR-FLD-000065", "documents": "SITREP_NWSW_August 2023_final.pdf",
        "pages": "4", "date_note": "Source says the flood and landslide occurred in late July; only the month is retained.",
        "geo_note": "Source directly identifies Limbe in Fako division, South-West.",
    },
    {
        "event_id": "FLD-CMR-2022-002", "event_date": "2022-08", "event_end_date": "2022-09",
        "region": "South-West", "division": "Fako", "locality": "",
        "latitude": "", "longitude": "", "severity": "", "confidence": "MEDIUM",
        "source": "OCHA Cameroon situation report, 1 November 2022",
        "source_ids": "CMR-FLD-000066", "documents": "Situation Report - Cameroon - 1 Nov 2022.pdf",
        "pages": "1; 6", "date_note": "The source covers 1 August–30 September 2022 and explicitly places the flooding in Fako during that reporting period; no day-level dates are asserted.",
        "geo_note": "Source identifies Fako division in the South-West; no locality or point coordinate is asserted.",
    },
    {
        "event_id": "FLD-CMR-2021-001", "event_date": "2021-07", "event_end_date": "",
        "region": "Far North", "division": "Mayo-Sava", "locality": "Seradoumda",
        "latitude": "", "longitude": "", "severity": "", "confidence": "MEDIUM",
        "source": "OCHA Cameroon Humanitarian Bulletin No. 23, August 2021; OCHA situation report, 7 October 2021",
        "source_ids": "CMR-FLD-000054", "documents": "Cameroon Humanitarian Bulletin Issue N°23 - August 2021.pdf; Cameroun - Rapport de situation, 7 octobre 2021.pdf",
        "pages": "1; 7", "date_note": "OCHA explicitly places the Mayo-Sava flooding in July 2021. The 7 October situation-report date is not used as the event date.",
        "geo_note": "The August bulletin identifies Mayo-Sava; the situation report identifies Seradoumda as a locality receiving assistance for flood victims.",
    },
    {
        "event_id": "FLD-CMR-2017-001", "event_date": "2017-09", "event_end_date": "",
        "region": "Far North", "division": "Logone-et-Chari", "locality": "Zina subdivision",
        "latitude": "", "longitude": "", "severity": "", "confidence": "MEDIUM",
        "source": "OCHA Cameroon Humanitarian Bulletin No. 4, September 2017",
        "source_ids": "CMR-FLD-000074", "documents": "ocha_cmr_bulletin20humanitaire_no.004_20171011.pdf",
        "pages": "1", "date_note": "The bulletin describes flooding during the recent weeks of its September 2017 reporting context; only the month is retained. The 11 October file/publication date is not used.",
        "geo_note": "The source identifies several villages in Zina subdivision, Logone-et-Chari, Far North.",
    },
]


def distinct(rows: list[dict], key: str) -> str:
    return "; ".join(sorted({str(row[key]) for row in rows if row.get(key) not in (None, "")}))


audit_header = [
    "catalogue_row_id", "event_id", "phase1_decision", "decision_reason",
    "candidate_source_record_ids", "source_documents", "evidence_pages",
    "original_event_name", "original_dates", "date_interpretation",
    "geographic_evidence", "merge_group", "verification_notes",
]

audit_rows = []
for n in range(1, 76):
    record_id = f"CMR-FLD-{n:06d}"
    records = by_record[record_id]
    decision, target, reason = DECISIONS.get(
        record_id,
        ("HOLD_FOR_EVIDENCE", "", "Cited source page has not yet undergone the required individual Phase-1 review."),
    )
    raw_dates = "; ".join(sorted({f"{r.get('start_date') or ''} to {r.get('end_date') or ''}" for r in records}))
    audit_rows.append({
        "catalogue_row_id": record_id, "event_id": target if decision in {"KEEP_AS_EVENT", "MERGE"} else "",
        "phase1_decision": decision, "decision_reason": reason,
        "candidate_source_record_ids": record_id, "source_documents": distinct(records, "filename"),
        "evidence_pages": distinct(records, "page_number"), "original_event_name": distinct(records, "event_name"),
        "original_dates": raw_dates,
        "date_interpretation": "Raw extracted date is not accepted without source-page verification." if decision == "HOLD_FOR_EVIDENCE" else reason,
        "geographic_evidence": "; ".join(filter(None, [distinct(records, "region"), distinct(records, "division"), distinct(records, "locations")])),
        "merge_group": target if decision == "MERGE" else "", "verification_notes": "All original evidence remains in master_events.json.",
    })

with (OUT / "clean_flood_events.csv").open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=["event_id", "event_date", "event_end_date", "region", "division", "locality", "latitude", "longitude", "severity", "confidence", "source"])
    writer.writeheader()
    writer.writerows([{key: event[key] for key in writer.fieldnames} for event in EVENTS])

with (OUT / "clean_flood_events_audit.csv").open("w", newline="", encoding="utf-8") as file:
    writer = csv.DictWriter(file, fieldnames=audit_header)
    writer.writeheader()
    writer.writerows(audit_rows)

counts = Counter(row["phase1_decision"] for row in audit_rows)
month_or_window = sum(len(event["event_date"]) == 7 for event in EVENTS)
exact_dates = sum(len(event["event_date"]) == 10 for event in EVENTS)
region_known = sum(bool(event["region"]) for event in EVENTS)
division_known = sum(bool(event["division"]) for event in EVENTS)
locality_known = sum(bool(event["locality"]) for event in EVENTS)
coordinates_known = sum(bool(event["latitude"] and event["longitude"]) for event in EVENTS)
confidence_counts = Counter(event["confidence"] for event in EVENTS)
held = [row["catalogue_row_id"] for row in audit_rows if row["phase1_decision"] in {"HOLD_FOR_EVIDENCE", "HOLD_FOR_DATE"}]
with (OUT / "phase2_readiness_report.md").open("w", encoding="utf-8") as report:
    report.write("# Phase 2 Readiness Report — Cameroon flood-event catalogue\n\n")
    report.write("## Final conclusion\n\n")
    if held:
        report.write("**PHASE 1 NOT COMPLETE — ADDITIONAL EVIDENCE CLEANING REQUIRED.**\n\n")
        report.write(f"The {len(EVENTS)} operational events below are conservative, source-traceable candidates. They are not authorization to start Phase 2 while {len(held)} held candidate records remain unresolved.\n\n")
    else:
        report.write("**PHASE 1 COMPLETE — READY FOR PHASE 2.**\n\n")
        report.write(f"All 75 raw candidate records have a documented final decision. The {len(EVENTS)} operational events below are source-traceable canonical episodes with month-level dates/windows and intentionally unresolved point coordinates.\n\n")
    report.write("## Counts\n\n")
    report.write("- Total raw catalogue records: **75**\n")
    for decision in ("KEEP_AS_EVENT", "MERGE", "EXCLUDE", "HOLD_FOR_DATE", "HOLD_FOR_EVIDENCE"):
        report.write(f"- {decision}: **{counts[decision]}**\n")
    report.write(f"- Canonical operational events: **{len(EVENTS)}**\n")
    report.write(f"- Events with exact day-level dates: **{exact_dates}**\n")
    report.write(f"- Events with month/window-only dates: **{month_or_window}**\n")
    report.write(f"- Region known: **{region_known}**; division known: **{division_known}**; locality known: **{locality_known}**\n")
    report.write(f"- Events with latitude/longitude already available: **{coordinates_known}**\n")
    report.write(f"- Events requiring geographic resolution: **{len(EVENTS) - coordinates_known}**\n")
    report.write(f"- High confidence: **{confidence_counts['HIGH']}**; medium confidence: **{confidence_counts['MEDIUM']}**; low confidence: **{confidence_counts['LOW']}**\n")
    report.write(f"- Records still requiring evidence verification: **{len(held)}**\n\n")
    report.write("## Merge decisions\n\n")
    for row in audit_rows:
        if row["phase1_decision"] == "MERGE":
            report.write(f"- `{row['catalogue_row_id']}` → `{row['event_id']}` — {row['decision_reason']}\n")
    report.write("\n## Excluded records\n\n")
    for row in audit_rows:
        if row["phase1_decision"] == "EXCLUDE":
            report.write(f"- `{row['catalogue_row_id']}` — {row['decision_reason']}\n")
    report.write("\n## Events provisionally ready for geographic resolution after Phase 1 is completed\n\n")
    for event in EVENTS:
        report.write(f"- `{event['event_id']}` — `{event['event_date']}` to `{event['event_end_date'] or 'ongoing/unknown'}`; {event['region']}; source: {event['source']}.\n")
    report.write("\n## Blocking unresolved records\n\n")
    if held:
        report.write(", ".join(f"`{record}`" for record in held) + "\n\n")
        report.write("Each blocking record requires source evidence sufficient to assign KEEP_AS_EVENT, MERGE, or EXCLUDE. No coordinate lookup or ERA5 matching has been performed.\n")
    else:
        report.write("None. All records have a final Phase-1 decision. No coordinate lookup or ERA5 matching has been performed.\n")

print(f"Wrote {len(EVENTS)} operational events and {len(audit_rows)} audited candidate records to {OUT}")
