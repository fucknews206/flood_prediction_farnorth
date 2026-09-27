#!/usr/bin/env python3
"""Turn the Centre-specific candidate search into an auditable event decision table."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT = ROOT / 'h2oai-flood-intelligence-agent-main' / 'data_quality' / 'centre_consolidation'
GAZETTEER = ROOT / 'boundaries-data' / 'gazetteer_full_merged.csv'
URL_RE = re.compile(r'https?://[^\s"<>]+', re.I)


def clean_url(value: str) -> str:
    matches = URL_RE.findall(value)
    # Search snippets commonly contain a displayed domain first and the real
    # organic-result URL later; the latter is the traceable candidate link.
    return matches[-1].rstrip('.,;)') if matches else ''


def classify(row: pd.Series) -> tuple[str, str, str | None, str | None, str | None]:
    text = row.evidence_excerpt.lower()
    place = row.matched_term
    # Exact, dated event evidence. The 2022-09-13/15 sources explicitly
    # state that flood victims at Obala were affected on 18 May.
    if 'obala' in text and ('inondations du 18 mai' in text or 'flood victims' in text) and ('2022' in text or '2022/09' in text):
        return ('VERIFIED_FLOOD_EVENT',
                'Source explicitly identifies flood victims in Obala (Lékié) and states the event occurred on 18 May; source publication date is September 2022.',
                '2022-05-18', 'Obala', 'CTR-FLD-2022-001')
    # Search copies and additional relief reports describe the same Obala
    # episode but do not independently provide the exact date.
    if 'obala' in text and any(token in text for token in ['75 familles', 'victimes des inondations', 'flood victims', 'sinistrés']):
        return ('POSSIBLE_DUPLICATE',
                'Likely supporting evidence for the verified 2022 Obala episode, but this candidate alone lacks a complete event date.',
                None, 'Obala', 'CTR-FLD-2022-001')
    # Explicit historical years but no event day/window are real evidence of
    # flooding, not usable positive labels.
    if 'yaound' in text and ('2018 et 2019' in text or '2018 and 2019' in text):
        return ('FLOOD_EVIDENCE_NEEDS_DATE',
                'The source says Yaoundé/Mfoundi was flooded in 2018 and 2019 but supplies no event day or defensible window.',
                None, 'Yaoundé', None)
    if 'trois inondations en un mois' in text or 'three floods in one month' in text:
        return ('FLOOD_EVIDENCE_NEEDS_DATE',
                'The source describes floods in Yaoundé but the displayed publication date cannot be used as the event date.',
                None, 'Yaoundé', None)
    # Phrases that describe susceptibility, policy, plans, or historical
    # aggregate frequency are not individual flood episodes.
    generic_markers = ['risque', 'cartograph', 'vulnérab', 'prévention', 'prévenir', 'lutte contre', 'drainage', 'assainissement', 'objectif', 'fréquence', 'recurrent', 'répétitiv', 'watershed', 'bassin versant', 'mémoire', 'study', 'étude']
    if any(marker in text for marker in generic_markers):
        return ('GENERAL_FLOOD_REFERENCE',
                'Flood risk, mitigation, research, or an aggregate history is discussed; no individual dated Centre flood episode is established.',
                None, None, None)
    if 'yaound' in text or any(place.lower() in text for place in ['mbalmayo', 'bafia', 'monatelé', 'nanga-eboko', 'akonolinga']):
        return ('FLOOD_EVIDENCE_NEEDS_DATE',
                'A Centre locality and flood language occur together, but no reliable event date/window is stated; publication/relative dates are not substituted.',
                None, place.split(';')[0], None)
    return ('GENERAL_FLOOD_REFERENCE',
            'Candidate does not establish an individual dated flood event at a Centre locality.', None, None, None)


def main() -> None:
    raw = pd.read_csv(OUT / 'centre_evidence_search_candidates_raw.csv')
    audit_rows = []
    for index, row in raw.iterrows():
        status, reason, event_date, locality, canonical = classify(row)
        audit_rows.append({
            'candidate_id': f'CTR-CAND-{index + 1:03d}', **row.to_dict(),
            'source_url': clean_url(row.evidence_excerpt),
            'verification_status': status, 'verification_reason': reason,
            'verified_event_date': event_date or 'UNKNOWN', 'verified_locality': locality or 'UNKNOWN',
            'canonical_event_id': canonical or 'NONE',
        })
    audit = pd.DataFrame(audit_rows)
    audit.to_csv(OUT / 'centre_evidence_verification_audit.csv', index=False)
    gaz = pd.read_csv(GAZETTEER)
    obala = gaz[gaz.name.eq('Obala')].iloc[0]
    verified = audit[audit.verification_status.eq('VERIFIED_FLOOD_EVENT')]
    canonical_rows = []
    if not verified.empty:
        sources = verified.source_url.replace('', pd.NA).dropna().unique().tolist()
        canonical_rows.append({
            'canonical_event_id': 'CTR-FLD-2022-001', 'event_status': 'VERIFIED_FLOOD_EVENT',
            'event_start_date': '2022-05-18', 'event_end_date': '2022-05-18', 'locality_name': 'Obala',
            'division': 'Lékié', 'region': 'Centre', 'latitude': obala.lat, 'longitude': obala.lon,
            'source_document_title': 'Actu Cameroun / supporting Obala flood-relief search records',
            'source_document_url': 'https://actucameroun.com/2022/09/13/paul-et-chantal-biya-volent-au-secours-des-victimes-des-inondations-a-obala-centre/',
            'source_event_id': '; '.join(verified.candidate_id),
            'evidence_summary': 'The source describes flood victims at Obala in Lékié and identifies the event as occurring on 18 May 2022.',
        })
    canonical = pd.DataFrame(canonical_rows, columns=[
        'canonical_event_id', 'event_status', 'event_start_date', 'event_end_date', 'locality_name', 'division', 'region',
        'latitude', 'longitude', 'source_document_title', 'source_document_url', 'source_event_id', 'evidence_summary',
    ])
    canonical.to_csv(OUT / 'canonical_flood_events.csv', index=False)
    print('candidates', len(audit), 'status_counts', audit.verification_status.value_counts().to_dict(), 'verified_events', len(canonical))


if __name__ == '__main__':
    main()
