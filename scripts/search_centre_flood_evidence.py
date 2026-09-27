#!/usr/bin/env python3
"""Search every supplied evidence file for Centre-specific flood candidates.

No bare ``centre`` match is used.  The script reports page/record-level
candidates; it does not treat a report publication date as an event date.
"""
from __future__ import annotations

import csv
import json
import re
import unicodedata
import zipfile
from pathlib import Path

import fitz
import pandas as pd

ROOT = Path('/home/ongou/Desktop/projects/end-of -year-defence')
OUT = ROOT / 'h2oai-flood-intelligence-agent-main' / 'data_quality' / 'centre_consolidation'
EVIDENCE_DIRS = [ROOT / 'relief_web-datasets', ROOT / 'scrapers-data']

DIVISIONS = [
    'Mfoundi', 'Lékié', 'Nyong-et-Mfoumou', 'Nyong-et-Kellé', 'Nyong-et-So\'o',
    'Mbam-et-Kim', 'Mbam-et-Inoubou', 'Haute-Sanaga', 'Méfou-et-Afamba', 'Méfou-et-Akono',
]
LOCALITIES = [
    'Yaoundé', 'Obala', 'Mbalmayo', 'Bafia', 'Nanga-Eboko', 'Akonolinga', 'Monatélé',
    'Soa', 'Mfou', 'Awaé', 'Ngoumou', 'Bikok', 'Mbankomo', 'Okola',
]
YAOUNDE_QUARTIERS = [
    'Nkolbisson', 'Biyem-Assi', 'Odza', 'Ekounou', 'Simbock', 'Nsam',
    'Mvog-Ada', 'Etoug-Ebe', 'Mimboman', 'Ngousso', 'Yaoundé VI',
    'Yaoundé VII',
]
FLOOD_RE = re.compile(r'\b(inondation(?:s)?|flood(?:s|ing)?|crue(?:s)?|débordement(?:s)?)\b', re.I)
DATE_RE = re.compile(r'\b(?:\d{1,2}[ /.-](?:\d{1,2}|jan(?:vier)?|févr(?:ier)?|mars|avr(?:il)?|mai|juin|juil(?:let)?|ao[uû]t|sept(?:embre)?|oct(?:obre)?|nov(?:embre)?|déc(?:embre)?)[ /.-]\d{2,4}|20\d{2}[/-]\d{1,2}[/-]\d{1,2})\b', re.I)


def normalise(value: str) -> str:
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    return value.lower().replace('’', "'")


def boundary_pattern(term: str) -> re.Pattern[str]:
    return re.compile(r'(?<!\w)' + re.escape(normalise(term)) + r'(?!\w)', re.I)


TERMS = [('Centre Region phrase', term) for term in ['Région du Centre', 'Centre Region']]
TERMS += [('Centre division', term) for term in DIVISIONS]
TERMS += [('Centre locality', term) for term in LOCALITIES]
TERMS += [('Yaoundé quartier/arrondissement', term) for term in YAOUNDE_QUARTIERS]

# Yaoundé arrondissements/quartiers only: not every Centre gazetteer name.
gaz = pd.read_csv(ROOT / 'boundaries-data' / 'gazetteer_full_merged.csv')
yaounde_terms = gaz[gaz['name'].fillna('').str.contains('Yaound', case=False)]['name'].dropna().tolist()
TERMS += [('Yaoundé gazetteer locality', term) for term in yaounde_terms]
TERM_PATTERNS = [(kind, term, boundary_pattern(term)) for kind, term in TERMS]


def find_terms(text: str) -> list[tuple[str, str, int, int]]:
    cleaned = normalise(text)
    hits = []
    for kind, term, pattern in TERM_PATTERNS:
        for match in pattern.finditer(cleaned):
            hits.append((kind, term, match.start(), match.end()))
    return hits


def snippet(text: str, offset: int, radius: int = 220) -> str:
    return re.sub(r'\s+', ' ', text[max(0, offset - radius): offset + radius]).strip()


def candidate_status(text: str, term_kind: str) -> str:
    """Conservative provisional status; manual review remains authoritative."""
    lowered = normalise(text)
    date_words = DATE_RE.search(text)
    # Publication/period wording is deliberately not upgraded to an event date.
    publication = any(marker in lowered for marker in ['rapport de situation', 'situation report', 'mise a jour', 'update', 'published', 'publication'])
    if date_words and not publication:
        return 'POSSIBLE_DUPLICATE_REVIEW_REQUIRED'
    if date_words:
        return 'FLOOD_EVIDENCE_NEEDS_DATE'
    return 'FLOOD_EVIDENCE_NEEDS_DATE'


def record_candidates(rows: list[dict], source_path: Path, source_kind: str, unit: str, text: str) -> None:
    for term_kind, term, start, _ in find_terms(text):
        context = snippet(text, start)
        # The Centre term and flood language must be locally associated.  A
        # document/CSV row that separately mentions Yaoundé and Far North
        # flooding is not a Centre flood candidate.
        if not FLOOD_RE.search(context):
            continue
        dates = '; '.join(dict.fromkeys(DATE_RE.findall(context)))
        rows.append({
            'source_file': str(source_path.relative_to(ROOT)), 'source_kind': source_kind, 'source_unit': unit,
            'matched_term_type': term_kind, 'matched_term': term, 'flood_terms': '; '.join(sorted(set(FLOOD_RE.findall(context)))),
            'date_text_in_context': dates or 'NONE_FOUND', 'source_date': 'UNKNOWN_REQUIRES_MANUAL_REVIEW',
            'event_date_or_window': 'UNKNOWN_REQUIRES_MANUAL_REVIEW',
            'provisional_status': candidate_status(context, term_kind), 'duplicate_group': 'UNASSESSED',
            'evidence_excerpt': context,
        })


def scan_pdf(path: Path, rows: list[dict], failures: list[dict]) -> None:
    try:
        with fitz.open(path) as document:
            for page_number, page in enumerate(document, start=1):
                # A page can contain unrelated country-wide/Far North floods
                # and a Yaoundé office reference. Paragraph granularity avoids
                # treating that coincidence as an event.
                text = page.get_text('text')
                passages = [piece for piece in re.split(r'\n\s*\n', text) if piece.strip()]
                for passage_number, passage in enumerate(passages, start=1):
                    record_candidates(rows, path, 'PDF', f'page {page_number}, passage {passage_number}', passage)
    except Exception as exc:
        failures.append({'source_file': str(path.relative_to(ROOT)), 'reason': f'{type(exc).__name__}: {exc}'})


def scan_csv(path: Path, rows: list[dict], failures: list[dict]) -> None:
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        for index, values in frame.iterrows():
            # Apify Google-search exports store each result in a set of
            # organicResults/N fields. Keep each result separate; combining a
            # whole SERP creates false links between unrelated search results.
            prefixes = sorted({match.group(1) for col in frame.columns if (match := re.match(r'(organicResults/\d+)/', col))})
            if prefixes:
                for prefix in prefixes:
                    cols = [col for col in frame.columns if col.startswith(prefix + '/')]
                    text = ' '.join(values[col] for col in cols if values[col])
                    record_candidates(rows, path, 'GOOGLE_SEARCH_RESULT', f'row {index + 2}, {prefix}', text)
            else:
                record_candidates(rows, path, 'CSV', f'row {index + 2}', ' '.join(values.astype(str).tolist()))
    except Exception as exc:
        failures.append({'source_file': str(path.relative_to(ROOT)), 'reason': f'{type(exc).__name__}: {exc}'})


def scan_json(path: Path, rows: list[dict], failures: list[dict]) -> None:
    try:
        record_candidates(rows, path, 'JSON', 'entire file', path.read_text(encoding='utf-8', errors='replace'))
    except Exception as exc:
        failures.append({'source_file': str(path.relative_to(ROOT)), 'reason': f'{type(exc).__name__}: {exc}'})


def scan_xlsx(path: Path, rows: list[dict], failures: list[dict]) -> None:
    try:
        with zipfile.ZipFile(path) as workbook:
            text = ' '.join(workbook.read(name).decode('utf-8', errors='replace') for name in workbook.namelist() if name.endswith('.xml'))
        record_candidates(rows, path, 'XLSX_XML', 'workbook text', text)
    except Exception as exc:
        failures.append({'source_file': str(path.relative_to(ROOT)), 'reason': f'{type(exc).__name__}: {exc}'})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []; failures: list[dict] = []; scanned = []
    for directory in EVIDENCE_DIRS:
        for path in sorted(directory.rglob('*')):
            if not path.is_file():
                continue
            scanned.append({'source_file': str(path.relative_to(ROOT)), 'size_bytes': path.stat().st_size, 'suffix': path.suffix.lower()})
            suffix = path.suffix.lower()
            if suffix == '.pdf': scan_pdf(path, rows, failures)
            elif suffix == '.csv': scan_csv(path, rows, failures)
            elif suffix == '.json': scan_json(path, rows, failures)
            elif suffix == '.xlsx': scan_xlsx(path, rows, failures)
            else: failures.append({'source_file': str(path.relative_to(ROOT)), 'reason': f'Unsupported type {suffix}'})
    candidates = pd.DataFrame(rows)
    if candidates.empty:
        candidates = pd.DataFrame(columns=['source_file', 'source_kind', 'source_unit', 'matched_term_type', 'matched_term', 'flood_terms', 'date_text_in_context', 'source_date', 'event_date_or_window', 'provisional_status', 'duplicate_group', 'evidence_excerpt'])
    # Repeated term matches from a single passage/result are one candidate,
    # retaining all matched Centre terms in that unit for manual review.
    if not candidates.empty:
        grouped = candidates.groupby(['source_file', 'source_kind', 'source_unit'], as_index=False).agg(
            matched_term_type=('matched_term_type', lambda v: '; '.join(dict.fromkeys(v))),
            matched_term=('matched_term', lambda v: '; '.join(dict.fromkeys(v))),
            flood_terms=('flood_terms', 'first'), date_text_in_context=('date_text_in_context', 'first'),
            source_date=('source_date', 'first'), event_date_or_window=('event_date_or_window', 'first'),
            provisional_status=('provisional_status', 'first'), duplicate_group=('duplicate_group', 'first'),
            evidence_excerpt=('evidence_excerpt', lambda values: max(values, key=len)),
        )
        candidates = grouped[[
            'source_file', 'source_kind', 'source_unit', 'matched_term_type', 'matched_term', 'flood_terms',
            'date_text_in_context', 'source_date', 'event_date_or_window', 'provisional_status', 'duplicate_group', 'evidence_excerpt',
        ]]
    candidates.to_csv(OUT / 'centre_evidence_search_candidates_raw.csv', index=False)
    pd.DataFrame(scanned).to_csv(OUT / 'centre_evidence_search_scanned_files.csv', index=False)
    pd.DataFrame(failures).to_csv(OUT / 'centre_evidence_search_failures.csv', index=False)
    print(f'scanned={len(scanned)} candidates={len(candidates)} failures={len(failures)}')


if __name__ == '__main__':
    main()
