#!/usr/bin/env python3
"""Reconcile the supplied 20-row Far North evidence register.

Far North region only, 2015-2025.  This script deliberately keeps a
row-level evidence audit separate from canonical episodes so that repeated
reports do not inflate the number of training labels.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_quality" / "farnorth_consolidation"
SOURCE = Path("/home/ongou/Downloads/cameroon_far_north_floods_2015_2025.csv")
CANONICAL = OUT / "canonical_flood_events_farnorth.csv"

URLS = {
    1: "https://reliefweb.int/report/cameroon/cameroon-floods-far-north-region-final-report-dref-operation-no-mdrcm029",
    3: "https://adore.ifrc.org/Download.aspx?FileId=264743",
    4: "https://www.acaps.org/en/countries/archives/detail/cameroon-floods-in-far-north-region",
    5: "https://reliefweb.int/report/cameroon/cameroon-far-north-floods-dref-operation-appeal-m" ,
    7: "https://cameroon.unfpa.org/en/publications/situation-report-n%C2%B0002floods-far-north",
    9: "https://go-api.ifrc.org/api/downloadfile/92340/MDRCM039eu3",
    13: "https://www.stopblablacam.com/society/0901-15574-cameroon-far-north-records-nearly-7-000-people-affected-by-floods-in-2025",
    15: "https://reliefweb.int/disaster/fl-2022-000349-cmr",
    16: "https://cameroon.unfpa.org/en/publications/flooding-situation-reportfar-north-and-north-cameroon",
    17: "https://www.unfpa.org/sites/default/files/resource-pdf/Cameroon%20Floods%20Flash%20Update%20%232%20%28Final%29.pdf",
    20: "https://reliefweb.int/disaster/fl-2020-000195-cmr",
}

def main():
    supplied = pd.read_csv(SOURCE)
    canonical = pd.read_csv(CANONICAL)
    canonical["supporting_evidence"] = canonical.get("supporting_evidence", "")

    # Every source was opened directly where possible. Some ReliefWeb pages
    # return an access error to automated fetches, so their matching locally
    # archived primary PDF is recorded instead of treating the supplied row as
    # self-verifying.
    verification = {
        1: ("VERIFIED_FLOOD_EVENT", "FNR-FLD-2020-002", "IFRC MDRCM029 final report: torrential rains peaked 31 August; Maroua bridge collapsed; five listed divisions affected. ReliefWeb page access-restricted, validated against local primary PDF MDRCM029dfr.pdf."),
        2: ("VERIFIED_FLOOD_EVENT", "FNR-FLD-2020-003", "IFRC MDRCM029 final report: intense continuous rainfall on 11-12 September in Mayo-Danay and Mayo-Kani, with the stated affected population."),
        3: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2019-001", "IFRC MDRCM028 EPoA directly confirms 4 October 2019 flooding in named Maga subdivision villages."),
        4: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2019-001", "ACAPS source directly confirms Logone overflow on 1 October 2019 and flooding in Zina district, Logone-et-Chari."),
        5: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2024-001", "MDRCM039 establishes the August 2024 flood series in named Logone-et-Chari and Mayo-Danay localities; direct ReliefWeb page access-restricted and corroborated by IFRC/UNFPA primary material."),
        6: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2024-001", "MDRCM039 identifies the 28 August Yagoua dike breach as the flood peak."),
        7: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2024-001", "UNFPA Situation Report No. 002 confirms 10 November 2024 dyke damage in Kousseri."),
        8: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2024-001", "UNFPA Situation Report No. 002 confirms 17 November 2024 dyke break at Biamo, Makary."),
        9: ("VERIFIED_FLOOD_EVENT", "FNR-FLD-2025-001", "IFRC MDRCM039 Operation Update #3 directly confirms 13 July flooding in named Mayo-Tsanaga localities."),
        10: ("VERIFIED_FLOOD_EVENT", "FNR-FLD-2025-001", "IFRC MDRCM039 Operation Update #3 directly confirms 5 August torrential-rain flooding across named Mayo-Danay arrondissements."),
        11: ("VERIFIED_FLOOD_EVENT", "FNR-FLD-2025-001", "IFRC MDRCM039 Operation Update #3 directly confirms 12 August heavy-rain damage in Hina subdivision, Mayo-Tsanaga."),
        12: ("VERIFIED_FLOOD_EVENT", "FNR-FLD-2025-001", "IFRC MDRCM039 Operation Update #3 directly confirms July 2025 flooding in Mayo-Danay and Logone-et-Chari."),
        13: ("VERIFIED_FLOOD_EVENT", "FNR-FLD-2025-002", "StopBlaBlaCam's report of OCHA's October sitrep states floods on 7-8 October at Hile-Alifa, Katikime and Tchika; direct page was access-error but indexed full text was reviewed."),
        14: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FNR-FLD-2025-001", "The same OCHA-reported account attributes the Kai-Kai flooding to July-August rains and Logone overflow, so it supports the July-August episode rather than creating a false October episode."),
        15: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2022-001", "ReliefWeb disaster record supports the already-audited August-November 2022 episode; direct page access-restricted."),
        16: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2022-001", "UNFPA October 2022 situation report establishes the mid-August to October window and Far North administrative footprint."),
        17: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2024-001", "UNFPA Flash Update #2 confirms floods in Logone-et-Chari, Mayo-Danay, Diamaré, Mayo-Tsanaga and Mayo-Kani."),
        18: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2024-001", "MDRCM039 corroborates July-August effects in Mokolo (Mayo-Tsanaga) and Ndoukoula (Diamaré)."),
        19: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FLD-CMR-2019-001", "IFRC MDRCM028 table directly confirms the October 2019 affected-population distribution across Maga, Kai-Kai, Yagoua and Zina."),
        20: ("ADDITIONAL_SUPPORTING_EVIDENCE", "FNR-FLD-2020-002", "OCHA/ReliefWeb August 2020 disaster record supports the 31-August 2020 wave; direct page access-restricted."),
    }
    audit = supplied.copy()
    audit["canonical_event_id"] = audit.Event_ID.map(lambda x: verification[x][1])
    audit["verification_status"] = audit.Event_ID.map(lambda x: verification[x][0])
    audit["verification_basis"] = audit.Event_ID.map(lambda x: verification[x][2])
    # Retain every submitted direct URL (including repeated URLs) for a
    # one-row-to-one-source audit trail.  The mapping above records preferred
    # landing pages only for source families with a stable canonical URL.
    audit["source_url_checked"] = audit["Source_URL"]
    audit["scope_label"] = "Far North region only, 2015-2025"
    audit.to_csv(OUT / "farnorth_evidence_2015_2025_verification_audit.csv", index=False)

    # Link supporting references to existing canonical rows.
    support = {
        "FLD-CMR-2019-001": "rows 3, 4, 19: MDRCM028 / ACAPS; exact 1-4 October 2019 evidence for Maga and Zina",
        "FLD-CMR-2020-001": "existing Phase 1 umbrella event retained unchanged",
        "FLD-CMR-2022-001": "rows 15, 16: ReliefWeb FL-2022-000349-CMR and UNFPA October 2022 situation report",
        "FLD-CMR-2024-001": "rows 5-8, 17-18: MDRCM039 and UNFPA; endpoint refined to 2024-11-17 and footprint widened",
    }
    for event_id, note in support.items():
        canonical.loc[canonical.canonical_event_id.eq(event_id), "supporting_evidence"] = note

    # Refinements to validated Phase-1 episodes (no new labels).
    # Keep the audited September-November episode window.  The exact
    # 1-4 October observations are a refinement in supporting_evidence, not
    # grounds to silently narrow an already-audited episode.
    canonical.loc[canonical.canonical_event_id.eq("FLD-CMR-2022-001"), "division"] = "Diamaré; Logone-et-Chari; Mayo-Danay; Mayo-Kani; Mayo-Sava; Mayo-Tsanaga"
    canonical.loc[canonical.canonical_event_id.eq("FLD-CMR-2024-001"), ["event_start_date", "event_end_date", "division", "locality_name"]] = [
        "2024-07", "2024-11-17", "Diamaré; Logone-et-Chari; Mayo-Danay; Mayo-Kani; Mayo-Tsanaga", "Biamo (Makary); Kousseri; Mokolo; Ndoukoula; Yagoua"
    ]

    new = pd.DataFrame([
        {"canonical_event_id":"FNR-FLD-2020-002", "event_status":"VERIFIED_FLOOD_EVENT", "event_start_date":"2020-08-31", "event_end_date":"2020-08-31", "date_precision":"DAY", "locality_name":"Maroua (bridge collapse)", "division":"Diamaré; Logone-et-Chari; Mayo-Sava; Mayo-Danay; Mayo-Kani", "region":"Far North", "latitude":None, "longitude":None, "location_precision":"ADMINISTRATIVE_FOOTPRINT", "source_document_title":"IFRC DREF MDRCM029 Final Report", "source_document_url":URLS[1], "source_event_id":"supplied-row-1", "duplicate_of":None, "evidence_summary":"Primary IFRC report describes the 31 August 2020 peak and Maroua bridge collapse.", "supporting_evidence":"row 20: OCHA/ReliefWeb August 2020 disaster record"},
        {"canonical_event_id":"FNR-FLD-2020-003", "event_status":"VERIFIED_FLOOD_EVENT", "event_start_date":"2020-09-11", "event_end_date":"2020-09-12", "date_precision":"DAY_WINDOW", "locality_name":"Mayo-Danay; Mayo-Kani", "division":"Mayo-Danay; Mayo-Kani", "region":"Far North", "latitude":None, "longitude":None, "location_precision":"ADMINISTRATIVE_FOOTPRINT", "source_document_title":"IFRC DREF MDRCM029 Final Report", "source_document_url":URLS[1], "source_event_id":"supplied-row-2", "duplicate_of":None, "evidence_summary":"Primary IFRC report states intense continuous rainfall and flooding on 11-12 September 2020.", "supporting_evidence":""},
        {"canonical_event_id":"FNR-FLD-2025-001", "event_status":"VERIFIED_FLOOD_EVENT", "event_start_date":"2025-07-13", "event_end_date":"2025-08-12", "date_precision":"DAY_WINDOW", "locality_name":"Gobo; Guéré; Hina; Kai-Kai; Kaliari; Korsamba; Maga; Mozogo; Nguetchewé; Tchatibali; Vélé; Yagoua", "division":"Logone-et-Chari; Mayo-Danay; Mayo-Tsanaga", "region":"Far North", "latitude":None, "longitude":None, "location_precision":"ADMINISTRATIVE_FOOTPRINT", "source_document_title":"IFRC Operation Update #3 MDRCM039", "source_document_url":URLS[9], "source_event_id":"supplied-rows-9-12", "duplicate_of":None, "evidence_summary":"IFRC confirms July-August 2025 flood incidents in named Mayo-Tsanaga, Mayo-Danay and Logone-et-Chari localities.", "supporting_evidence":"row 14: OCHA-reported Kai-Kai impacts are attributed to the same July-August rainfall/Logone overflow"},
        {"canonical_event_id":"FNR-FLD-2025-002", "event_status":"VERIFIED_FLOOD_EVENT", "event_start_date":"2025-10-07", "event_end_date":"2025-10-08", "date_precision":"DAY_WINDOW", "locality_name":"Hile-Alifa; Katikime; Tchika", "division":"Logone-et-Chari", "region":"Far North", "latitude":None, "longitude":None, "location_precision":"LOCALITY", "source_document_title":"OCHA October 2025 Far North situation report (reported by StopBlaBlaCam)", "source_document_url":URLS[13], "source_event_id":"supplied-row-13", "duplicate_of":None, "evidence_summary":"OCHA-reported October sitrep describes a distinct 7-8 October flood at Hile-Alifa, Katikime and Tchika.", "supporting_evidence":"Direct site fetch was access-error; the indexed full report text was reviewed."},
    ])
    canonical = pd.concat([canonical, new], ignore_index=True, sort=False)
    canonical = canonical.drop_duplicates("canonical_event_id", keep="last")
    canonical.to_csv(CANONICAL, index=False)

    # Gate report uses independent canonical episodes, not individual citations.
    divisions = {}
    for value in canonical.division.fillna(""):
        for division in [x.strip() for x in value.split(";") if x.strip()]:
            divisions[division] = divisions.get(division, 0) + 1
    years = sorted({str(v)[:4] for v in canonical.event_start_date if str(v)[:4].isdigit()})
    localities = {x.strip() for value in canonical.locality_name.fillna("") for x in str(value).split(";") if x.strip() and x.strip() != "UNKNOWN"}
    report = f"""# Far North region only, 2015-2025 — Readiness Gate after 20-row source verification

**FAIL — DO NOT TRAIN A CLASSIFIER**

## Reconciled, verified catalogue

- Supplied evidence rows reviewed: 20/20.
- New independent verified episodes: 4 (two 2020 waves and two 2025 episodes).
- Supporting-evidence rows/refinements: 13; they do not create additional labels.
- Total independent verified episodes: {len(canonical)}.
- Distinct named localities: {len(localities)}.
- Distinct years: {len(years)} ({', '.join(years)}).
- Per-division episode coverage: {divisions}.
- Gap to the 30-episode minimum: {max(0, 30-len(canonical))}.

## Important reconciliation decisions

- The 2024 episode now covers Diamaré and Mayo-Kani and has an evidence-supported endpoint of 17 November 2024.
- The October 2025 Logone-et-Chari event is a distinct 7-8 October episode.
- The alleged October 2025 Mayo-Danay item is *not* a separate October event: its source attributes it to July-August rainfall and Logone overflow, so it is supporting evidence for the July-August 2025 episode.
- The 2019, 2022 and 2024 source rows are retained as supporting evidence for already-audited episodes.

The environmental layers may support an interim rules-based susceptibility/threshold warning product, but {len(canonical)} positive episodes are not enough for a defensible supervised classifier.
"""
    (OUT / "farnorth_build_summary.md").write_text(report, encoding="utf-8")

if __name__ == "__main__":
    main()
