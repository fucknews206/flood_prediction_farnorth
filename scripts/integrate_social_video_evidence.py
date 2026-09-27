#!/usr/bin/env python3
"""Audit the supplied Facebook/YouTube exports without lowering evidence rules.

Only a video that supplies an event date and a Centre footprint (or independently
cross-confirms an existing canonical episode) can be verified.  Upload time is
retained as metadata, never silently substituted for an event date.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT = ROOT / 'h2oai-flood-intelligence-agent-main' / 'data_quality' / 'centre_consolidation'
SOURCE_DIR = ROOT / 'scrapers-data' / 'face and yout'
GAZ = ROOT / 'boundaries-data' / 'gazetteer_full_merged.csv'
YOUTUBE = SOURCE_DIR / 'dataset_youtube-scraper_2026-09-01_07-20-44-785.csv'
FACEBOOK = SOURCE_DIR / 'dataset_facebook-posts-scraper_2026-09-01_10-23-25-965.csv'

FLOOD_RE = re.compile(r'\b(?:inondation|inondations|flood|flooding|crue)\b', re.I)
LOCAL_RE = re.compile(
    r'yaound[eé]|nkolbisson|biyem[ -]assi|mfoundi|obala|mbalmayo|bafia|nanga[ -]eboko|'
    r'akonolinga|monat[eé]l[eé]|\bsoa\b|\bmfou\b|awa[eé]|ngoumou|bikok|mbankomo|okola|'
    r'odza|ekounou|simbock|nsam|mvog[ -]ada|etoug[ -]ebe|mimboman|ngousso|oyomabang|'
    r'mbankolo|mvan|essos|emah|mokolo|kennedy|melen|elig[ -]edzoa|poste centrale', re.I)

# Full text, not a search-result snippet, gives the event date and locality.
# Biyem-Assi is explicitly placed in Yaounde VI by the description.  The
# canonical sample uses the existing Yaounde VI administrative footprint rather
# than inventing a Biyem-Assi point that is absent from the project gazetteer.
NEW_VERIFIED = {
    'https://www.youtube.com/watch?v=33U08G_SbC4': {
        'canonical_event_id': 'CTR-FLD-2024-001',
        'event_date': '2024-10-07',
        'feature_locality': 'Yaoundé VI',
        'reported_locality': 'Biyem-Assi, Yaoundé VI',
        'division': 'Mfoundi',
        'title': 'Yaoundé : des canalisations sèment la mort au quartier Biyem-Assi',
        'reason': ('Full YouTube description states that Biyem-Assi is in Yaoundé VI and that a 13-year-old was carried away '
                   'by rainwater on 7 October 2024. The Yaoundé VI gazetteer footprint is used; no Biyem-Assi point is invented.'),
    },
}
EXISTING_CONFIRMED = {
    'https://www.youtube.com/watch?v=RtlupLSMGCk': {
        'canonical_event_id': 'CTR-FLD-2017-001',
        'event_date': '2017-09-12',
        'locality': 'Nkolbisson',
        'reason': ('The full description independently names Nkolbisson, Centre Region and recounts the 12 September 2017 '
                   'flooding/damage described by the existing canonical event; retained as corroborating evidence, not a new episode.'),
    },
}
EXACT_DATE_NO_GAZETTEER_POINT = {
    'https://www.youtube.com/watch?v=v9k5VHZ8Efw': ('2013-03-01', 'Palais des Sports, Yaoundé'),
    'https://www.youtube.com/watch?v=CRvm-VyO04U': ('2013-03-01', 'Carrefour MEEC / Melen, Yaoundé'),
    'https://www.youtube.com/watch?v=6qmC3iNyMVo': ('2019-03-07', 'Poste Centrale, Yaoundé'),
    'https://www.youtube.com/watch?v=M1A26O3uoic': ('2019-09-20', 'Avenue Kennedy / Emah Basile, Yaoundé'),
}
POSSIBLE_DUPLICATES = {
    'https://www.youtube.com/watch?v=wI_UDiCRl-I': 'A 13 September 2017 Yaoundé-wide report may concern the 12 September Nkolbisson episode, but it does not name Nkolbisson; do not merge without viewing/transcript confirmation.',
    'https://www.youtube.com/watch?v=YR_VWQNCeQw': 'The 19 June 2021 Yaoundé VII upload may be follow-up coverage of the 7 June 2021 canonical event, but the metadata/text does not state that event date.',
}
GENERIC_MARKERS = re.compile(r'prévention|prevention|plan anti|cause[s]? des inondations|risque|pollution|déchets|field trip|keep yaounde clean|épargnées|menace', re.I)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def content(row: pd.Series) -> str:
    return '\n'.join(str(row.get(column, '') or '') for column in ['title', 'text', 'aiVideoDescription', 'aiVideoSummary'])


def matched_terms(text: str) -> str:
    return '; '.join(dict.fromkeys(match.group(0) for match in LOCAL_RE.finditer(text)))


def classify(row: pd.Series) -> dict[str, str]:
    text = content(row)
    url = str(row['url'])
    title = str(row.get('title', ''))
    upload = str(row.get('date', ''))
    if url in NEW_VERIFIED:
        rule = NEW_VERIFIED[url]
        return {'status': 'VERIFIED_FLOOD_EVENT', 'event_date': rule['event_date'], 'locality': rule['reported_locality'],
                'canonical': rule['canonical_event_id'], 'reason': rule['reason'], 'transcript': 'NO'}
    if url in EXISTING_CONFIRMED:
        rule = EXISTING_CONFIRMED[url]
        return {'status': 'VERIFIED_FLOOD_EVENT', 'event_date': rule['event_date'], 'locality': rule['locality'],
                'canonical': rule['canonical_event_id'], 'reason': rule['reason'], 'transcript': 'NO'}
    if url in EXACT_DATE_NO_GAZETTEER_POINT:
        date, locality = EXACT_DATE_NO_GAZETTEER_POINT[url]
        return {'status': 'FLOOD_EVIDENCE_NEEDS_LOCATION', 'event_date': date, 'locality': locality, 'canonical': 'NONE',
                'reason': ('The video text gives a specific flood date and Yaoundé locality, but that locality has no defensible '
                           'project-gazetteer feature/coordinate. Held rather than assigning a made-up point.'), 'transcript': 'YES'}
    if url in POSSIBLE_DUPLICATES:
        return {'status': 'POSSIBLE_DUPLICATE', 'event_date': 'UNKNOWN', 'locality': 'Yaoundé', 'canonical': 'NONE',
                'reason': POSSIBLE_DUPLICATES[url], 'transcript': 'YES'}
    if GENERIC_MARKERS.search(text):
        return {'status': 'GENERAL_FLOOD_REFERENCE', 'event_date': 'UNKNOWN', 'locality': 'UNKNOWN', 'canonical': 'NONE',
                'reason': 'Video discusses causes, prevention, risk, mitigation, or general/recurrent flooding rather than a dated individual event.', 'transcript': 'NO'}
    return {'status': 'FLOOD_EVIDENCE_NEEDS_DATE', 'event_date': 'UNKNOWN', 'locality': matched_terms(text) or 'Yaoundé', 'canonical': 'NONE',
            'reason': ('Flood content and a Centre locality are present, but the uploaded-at timestamp is not accepted as the event date. '
                       'A transcript or the full video is needed to establish the event date/window.'), 'transcript': 'YES'}


def main() -> None:
    if not FACEBOOK.exists() or not YOUTUBE.exists():
        raise FileNotFoundError('Expected social exports are not visible in scrapers-data/face and yout/.')
    facebook = pd.read_csv(FACEBOOK)
    youtube = pd.read_csv(YOUTUBE)
    social_files = pd.DataFrame([
        {'source_file': rel(FACEBOOK), 'size_bytes': FACEBOOK.stat().st_size, 'suffix': '.csv'},
        {'source_file': rel(YOUTUBE), 'size_bytes': YOUTUBE.stat().st_size, 'suffix': '.csv'},
    ])
    prior_scanned = pd.read_csv(OUT / 'centre_evidence_search_scanned_files.csv')
    pd.concat([prior_scanned, social_files], ignore_index=True).drop_duplicates('source_file', keep='last').to_csv(
        OUT / 'centre_evidence_search_scanned_files.csv', index=False)
    # Facebook has only scraper error rows: there is no post text/date/page data to audit.
    facebook_note = (f'Facebook export has {len(facebook)} rows and columns {list(facebook.columns)}. '
                     f'All rows are scraper errors/no-items; accessible posts with text, date and page: 0.')
    rows = []
    source_file = rel(YOUTUBE)
    for idx, row in youtube.iterrows():
        text = content(row)
        # The Biyem-Assi item is the sole controlled semantic exception: its
        # full description does not use the word "inondation", but expressly
        # describes a child swept away by rainwater at a named place and date.
        # It is kept auditable rather than treated as a keyword hit.
        if not ((FLOOD_RE.search(text) or str(row.get('url')) in NEW_VERIFIED) and LOCAL_RE.search(text)):
            continue
        decision = classify(row)
        upload = pd.to_datetime(row.get('date'), errors='coerce')
        excerpt = f"TITLE: {row.get('title', '')}\nCHANNEL: {row.get('channelName', '')}\nUPLOAD_DATE: {row.get('date', '')}\nDESCRIPTION: {row.get('text', '')}"
        rows.append({
            'source_file': source_file, 'source_kind': 'youtube_video_metadata', 'source_unit': f'row {idx + 2}',
            'matched_term_type': 'centre_locality_or_division', 'matched_term': matched_terms(text),
            'flood_terms': '; '.join(dict.fromkeys(m.group(0) for m in FLOOD_RE.finditer(text))),
            'date_text_in_context': str(row.get('date', '')), 'source_date': upload.date().isoformat() if pd.notna(upload) else 'UNKNOWN',
            'event_date_or_window': decision['event_date'], 'provisional_status': decision['status'],
            'duplicate_group': decision['canonical'] if decision['canonical'] != 'NONE' else '', 'evidence_excerpt': excerpt,
            'source_url': str(row['url']), 'verification_status': decision['status'],
            'verification_reason': decision['reason'], 'verified_event_date': decision['event_date'],
            'verified_locality': decision['locality'], 'canonical_event_id': decision['canonical'],
            'channel_name': str(row.get('channelName', '')), 'video_title': str(row.get('title', '')),
            'upload_date': upload.date().isoformat() if pd.notna(upload) else 'UNKNOWN',
            'transcript_follow_up_required': decision['transcript'],
        })
    social = pd.DataFrame(rows)
    social.to_csv(OUT / 'social_video_evidence_verification_audit.csv', index=False)
    social[social.transcript_follow_up_required.eq('YES')].to_csv(OUT / 'youtube_transcript_follow_up_candidates.csv', index=False)
    raw_columns = pd.read_csv(OUT / 'centre_evidence_search_candidates_raw.csv').columns.tolist()
    old_raw = pd.read_csv(OUT / 'centre_evidence_search_candidates_raw.csv')
    combined_raw = pd.concat([old_raw, social[raw_columns]], ignore_index=True).drop_duplicates(['source_file', 'source_unit'], keep='last')
    combined_raw.to_csv(OUT / 'centre_evidence_search_candidates_raw.csv', index=False)
    old_audit = pd.read_csv(OUT / 'centre_evidence_verification_audit.csv')
    start = old_audit.candidate_id.str.extract(r'(\d+)$')[0].dropna().astype(int).max() + 1
    social.insert(0, 'candidate_id', [f'CTR-CAND-{number:03d}' for number in range(start, start + len(social))])
    audit_columns = old_audit.columns.tolist()
    combined_audit = pd.concat([old_audit, social.reindex(columns=audit_columns)], ignore_index=True)
    combined_audit = combined_audit.drop_duplicates(['source_file', 'source_unit'], keep='last')
    combined_audit.to_csv(OUT / 'centre_evidence_verification_audit.csv', index=False)
    canonical = pd.read_csv(OUT / 'canonical_flood_events.csv')
    additions = []
    for url, rule in NEW_VERIFIED.items():
        loc = pd.read_csv(GAZ)
        loc = loc[(loc.name.eq(rule['feature_locality'])) & (loc.region.eq('Centre')) & (loc.division.eq(rule['division']))]
        if len(loc) != 1:
            raise ValueError(f"Expected one Centre gazetteer record for {rule['feature_locality']}; found {len(loc)}")
        place = loc.iloc[0]
        source_ids = '; '.join(social.loc[social.canonical_event_id.eq(rule['canonical_event_id']), 'candidate_id'])
        additions.append({
            'canonical_event_id': rule['canonical_event_id'], 'event_status': 'VERIFIED_FLOOD_EVENT',
            'event_start_date': rule['event_date'], 'event_end_date': rule['event_date'],
            'locality_name': rule['feature_locality'], 'division': rule['division'], 'region': 'Centre',
            'latitude': place.lat, 'longitude': place.lon, 'source_document_title': rule['title'],
            'source_document_url': url, 'source_event_id': source_ids, 'evidence_summary': rule['reason'],
        })
    # Do not change the three pre-existing episodes. Replace only this
    # script's own canonical row on reruns so its source candidate ID stays
    # traceable after the audit is regenerated.
    new_ids = {item['canonical_event_id'] for item in additions}
    canonical = pd.concat([canonical[~canonical.canonical_event_id.isin(new_ids)], pd.DataFrame(additions)], ignore_index=True)
    canonical.sort_values('event_start_date').to_csv(OUT / 'canonical_flood_events.csv', index=False)
    (OUT / 'social_source_discovery_report.md').write_text(
        '# Social-source Phase 0 discovery\n\n'
        f'- Requested `face/` and `yout/` directories were not present separately; both exports were found in `{SOURCE_DIR}`.\n'
        f'- Facebook: `{FACEBOOK.name}`, {len(facebook)} rows. {facebook_note}\n'
        f'- YouTube: `{YOUTUBE.name}`, {len(youtube)} rows; {len(social)} flood-and-Centre matching videos audited.\n'
        '- The World Bank/AFD source was intentionally not searched or substituted.\n', encoding='utf-8')
    print({'facebook_accessible_posts': 0, 'youtube_rows': len(youtube), 'youtube_candidates': len(social),
           'social_statuses': social.verification_status.value_counts().to_dict(),
           'transcript_follow_ups': int(social.transcript_follow_up_required.eq('YES').sum()),
           'canonical_events': len(canonical)})


if __name__ == '__main__':
    main()
