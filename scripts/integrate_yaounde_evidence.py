#!/usr/bin/env python3
"""Audit new Yaoundé search results and merge only full-article-verified events."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT = ROOT / 'h2oai-flood-intelligence-agent-main' / 'data_quality' / 'centre_consolidation'
GAZ = ROOT / 'boundaries-data' / 'gazetteer_full_merged.csv'

FULL_ARTICLE_VERIFIED = {
    'actucameroun.com/2017/09/12/cameroun-yaounde-les-inondations-persistent-au-quartier-nkolbisson/': {
        'status': 'VERIFIED_FLOOD_EVENT', 'date': '2017-09-12', 'locality': 'Nkolbisson',
        'canonical': 'CTR-FLD-2017-001', 'division': 'Mfoundi',
        'title': 'Cameroun – Yaoundé: Les inondations persistent au quartier Nkolbisson',
        'reason': 'Full article read: it is dated 12 September 2017, identifies Nkolbisson in Yaoundé/Centre, and describes active recurrent flooding and damage after rain.',
    },
    'actucameroun.com/2021/06/10/apres-les-inondations-la-mairie-de-yaounde-7-fermee/': {
        'status': 'VERIFIED_FLOOD_EVENT', 'date': '2021-06-07', 'locality': 'Yaoundé VII',
        'canonical': 'CTR-FLD-2021-001', 'division': 'Mfoundi',
        'title': 'Après les inondations, la mairie de Yaoundé 7 fermée',
        'reason': 'Full article read: it identifies Yaoundé VII and states that heavy rain on 7 June 2021 caused flooding, collapse of the structure, and loss of archives.',
    },
}
CITY_WIDE_FULL_ARTICLE = {
    'datacameroon.com/yaounde-lutte-contre-les-inondations-158/': 'Full article confirms a flood on 30 June 2022 at Avenue Kennedy/Yaoundé, but does not provide a defensible gazetteer locality coordinate; held rather than assigning an invented point.',
    'actucameroun.com/2023/03/23/alerte-inondations-a-yaounde-le-pire-annonce-pour-les-habitants-du-21-au-30-mars-2023/': 'Full article confirms serious flooding in several Yaoundé neighbourhoods on 21 March 2023, but does not identify a defensible locality footprint; held rather than assigning an invented point.',
}


def extract_url(text: str) -> str:
    urls = re.findall(r'https?://[^\s"<>]+', text)
    return urls[-1].rstrip('.,;)') if urls else ''


def normal_url(url: str) -> str:
    return re.sub(r'^https?://(?:www\.)?', '', url).rstrip('/')


def generic(text: str) -> bool:
    low = text.lower()
    markers = ['risque', 'prévenir', 'prévention', 'cartograph', 'mémoire', 'étude', 'vulnérab', 'projet', 'drainage', 'assainissement', 'fréquence', 'récurrent', 'recurrent']
    return any(marker in low for marker in markers)


def main() -> None:
    raw = pd.read_csv(OUT / 'centre_evidence_search_candidates_raw.csv')
    existing = pd.read_csv(OUT / 'centre_evidence_verification_audit.csv')
    new = raw[raw.source_file.str.contains('scrapers-data/apify_yaounde/', regex=False)].copy()
    start = existing.candidate_id.str.extract(r'(\d+)$')[0].astype(int).max() + 1
    rows = []
    for offset, item in enumerate(new.itertuples(index=False), start=start):
        url = extract_url(item.evidence_excerpt); normalized = normal_url(url)
        verified_by_url = {normal_url('https://' + key): value for key, value in FULL_ARTICLE_VERIFIED.items()}
        held_by_url = {normal_url('https://' + key): value for key, value in CITY_WIDE_FULL_ARTICLE.items()}
        if normalized in verified_by_url:
            review = verified_by_url[normalized]
            status, date, locality, canonical, reason = review['status'], review['date'], review['locality'], review['canonical'], review['reason']
        elif normalized in held_by_url:
            status, date, locality, canonical, reason = 'FLOOD_EVIDENCE_NEEDS_LOCATION', 'UNKNOWN', 'Yaoundé', 'NONE', held_by_url[normalized]
        elif generic(item.evidence_excerpt):
            status, date, locality, canonical, reason = 'GENERAL_FLOOD_REFERENCE', 'UNKNOWN', 'UNKNOWN', 'NONE', 'Search snippet concerns risk, research, mitigation, or aggregate history rather than a verified individual event.'
        else:
            status, date, locality, canonical, reason = 'FLOOD_EVIDENCE_NEEDS_DATE', 'UNKNOWN', item.matched_term.split(';')[0], 'NONE', 'A snippet appears to describe flooding, but its linked article was not read; date/locality are not verified from a snippet alone.'
        rows.append({
            'candidate_id': f'CTR-CAND-{offset:03d}', **item._asdict(), 'source_url': url,
            'verification_status': status, 'verification_reason': reason, 'verified_event_date': date,
            'verified_locality': locality, 'canonical_event_id': canonical,
        })
    new_audit = pd.DataFrame(rows)
    combined = pd.concat([existing, new_audit], ignore_index=True)
    # Re-runs are idempotent at the candidate-unit level and retain reviewed
    # full-article decisions for every repeated search result.
    combined = combined.drop_duplicates(['source_file', 'source_unit'], keep='last')
    combined.to_csv(OUT / 'centre_evidence_verification_audit.csv', index=False)
    canonical = pd.read_csv(OUT / 'canonical_flood_events.csv')
    gaz = pd.read_csv(GAZ)
    additions = []
    for event_id, review in [('CTR-FLD-2017-001', FULL_ARTICLE_VERIFIED[list(FULL_ARTICLE_VERIFIED)[0]]), ('CTR-FLD-2021-001', FULL_ARTICLE_VERIFIED[list(FULL_ARTICLE_VERIFIED)[1]])]:
        loc = gaz[gaz.name.eq(review['locality'])]
        if len(loc) != 1:
            raise ValueError(f"Expected one gazetteer match for {review['locality']}, found {len(loc)}")
        loc = loc.iloc[0]
        additions.append({
            'canonical_event_id': event_id, 'event_status': 'VERIFIED_FLOOD_EVENT', 'event_start_date': review['date'], 'event_end_date': review['date'],
            'locality_name': review['locality'], 'division': review['division'], 'region': 'Centre', 'latitude': loc.lat, 'longitude': loc.lon,
            'source_document_title': review['title'], 'source_document_url': 'https://' + next(key for key, value in FULL_ARTICLE_VERIFIED.items() if value['canonical'] == event_id),
            'source_event_id': '; '.join(new_audit.loc[new_audit.canonical_event_id.eq(event_id), 'candidate_id']), 'evidence_summary': review['reason'],
        })
    canonical = pd.concat([canonical, pd.DataFrame(additions)], ignore_index=True)
    canonical = canonical.drop_duplicates('canonical_event_id', keep='first').sort_values('event_start_date')
    canonical.to_csv(OUT / 'canonical_flood_events.csv', index=False)
    print({'new_candidates': len(new_audit), 'all_candidates': len(combined), 'new_statuses': new_audit.verification_status.value_counts().to_dict(), 'canonical_events': len(canonical)})


if __name__ == '__main__':
    main()
