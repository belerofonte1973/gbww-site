#!/usr/bin/env python3
"""
Import Latin literary texts into classics.db.

Source: Perseus Digital Library — PerseusDL/canonical-latinLit (GitHub)
TEI XML editions with Latin text and English translations.

Texts:
  lat.aeneid       — Virgil, Aeneid
  lat.eclogues     — Virgil, Eclogues
  lat.catullus     — Catullus, Carmina
  lat.caesar_gall  — Caesar, De Bello Gallico
  lat.lucretius    — Lucretius, De Rerum Natura
  lat.horace_odes  — Horace, Carmina (Odes)
  lat.ovid_amores  — Ovid, Amores
"""

import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

DB_PATH  = Path(__file__).parent / 'classics.db'
CACHE    = Path(__file__).parent / 'data' / 'perseus_cache'
GH_RAW   = 'https://raw.githubusercontent.com/PerseusDL/canonical-latinLit/master/data'
TEI_NS   = 'http://www.tei-c.org/ns/1.0'

# ── Texts manifest ────────────────────────────────────────────────────────────

TEXTS = [
    {
        'id':        'lat.aeneid',
        'title_en':  'Aeneid',
        'title_pt':  'Eneida',
        'author_pt': 'Virgílio',
        'phi_author': 'phi0690',
        'phi_work':   'phi003',
        'lat_file':   'phi0690.phi003.perseus-lat2.xml',
        'eng_file':   'phi0690.phi003.perseus-eng2.xml',
        'mode':       'card',
        'note':       'Virgílio (70–19 a.C.) — Epopeia em 12 livros sobre a fundação de Roma. '
                      'Trad. Theodore C. Williams, 1910. Fonte: Perseus Digital Library.',
    },
    {
        'id':        'lat.eclogues',
        'title_en':  'Eclogues',
        'title_pt':  'Bucólicas',
        'author_pt': 'Virgílio',
        'phi_author': 'phi0690',
        'phi_work':   'phi001',
        'lat_file':   'phi0690.phi001.perseus-lat2.xml',
        'eng_file':   'phi0690.phi001.perseus-eng2.xml',
        'mode':       'poem',
        'note':       'Virgílio (70–19 a.C.) — 10 poemas pastorais (Bucólicas). '
                      'Trad. J. B. Greenough, 1895. Fonte: Perseus Digital Library.',
    },
    {
        'id':        'lat.catullus',
        'title_en':  'Carmina',
        'title_pt':  'Carmina',
        'author_pt': 'Catulo',
        'phi_author': 'phi0472',
        'phi_work':   'phi001',
        'lat_file':   'phi0472.phi001.perseus-lat2.xml',
        'eng_file':   'phi0472.phi001.perseus-eng3.xml',
        'mode':       'poem',
        'note':       'Catulo (c. 84–54 a.C.) — 116 poemas líricos: amor por Lésbia, epigramas, hinos. '
                      'Trad. Sir Richard F. Burton, 1894. Fonte: Perseus Digital Library.',
    },
    {
        'id':        'lat.caesar_gall',
        'title_en':  'De Bello Gallico',
        'title_pt':  'A Guerra das Gálias',
        'author_pt': 'César',
        'phi_author': 'phi0448',
        'phi_work':   'phi001',
        'lat_file':   'phi0448.phi001.perseus-lat2.xml',
        'eng_file':   'phi0448.phi001.perseus-eng2.xml',
        'mode':       'chapter',
        'note':       'Júlio César (100–44 a.C.) — Crónica das campanhas na Gália (58–50 a.C.), '
                      '7 livros. Trad. W. A. McDevitte & W. S. Bohn, 1869. Fonte: Perseus Digital Library.',
    },
    {
        'id':        'lat.lucretius',
        'title_en':  'De Rerum Natura',
        'title_pt':  'Da Natureza das Coisas',
        'author_pt': 'Lucrécio',
        'phi_author': 'phi0550',
        'phi_work':   'phi001',
        'lat_file':   'phi0550.phi001.perseus-lat1.xml',
        'eng_file':   'phi0550.phi001.perseus-eng1.xml',
        'mode':       'card',
        'note':       'Lucrécio (c. 99–55 a.C.) — Poema filosófico em 6 livros sobre a natureza do universo '
                      'segundo a física epicurista. Trad. William Ellery Leonard, 1916. '
                      'Fonte: Perseus Digital Library.',
    },
    {
        'id':        'lat.horace_odes',
        'title_en':  'Odes (Carmina)',
        'title_pt':  'Odes (Carmina)',
        'author_pt': 'Horácio',
        'phi_author': 'phi0893',
        'phi_work':   'phi001',
        'lat_file':   'phi0893.phi001.perseus-lat2.xml',
        'eng_file':   'phi0893.phi001.perseus-eng2.xml',
        'mode':       'poem',
        'note':       'Horácio (65–8 a.C.) — 103 odes em 4 livros: amor, amizade, carpe diem, vinho. '
                      'Trad. Paul Shorey & Gordon Laing, 1919. Fonte: Perseus Digital Library.',
    },
    {
        'id':        'lat.ovid_amores',
        'title_en':  'Amores',
        'title_pt':  'Amores',
        'author_pt': 'Ovídio',
        'phi_author': 'phi0959',
        'phi_work':   'phi001',
        'lat_file':   'phi0959.phi001.perseus-lat2.xml',
        'eng_file':   'phi0959.phi001.perseus-eng2.xml',
        'mode':       'poem',
        'note':       'Ovídio (43 a.C. – 17 d.C.) — 49 elegias de amor em 3 livros. '
                      'Trad. Grant Showerman, 1914. Fonte: Perseus Digital Library.',
    },
]


# ── downloader ────────────────────────────────────────────────────────────────

def fetch_xml(phi_author: str, phi_work: str, filename: str) -> bytes | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / filename
    if cache_file.exists():
        return cache_file.read_bytes()
    url = f'{GH_RAW}/{phi_author}/{phi_work}/{filename}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Classics-Reader/1.0'})
    try:
        data = urllib.request.urlopen(req, timeout=30).read()
    except Exception as ex:
        print(f'    ↯ download falhou ({filename}): {ex}')
        return None
    cache_file.write_bytes(data)
    time.sleep(0.6)
    return data


# ── TEI XML helpers ───────────────────────────────────────────────────────────

def tei(tag: str) -> str:
    return f'{{{TEI_NS}}}{tag}'


def el_text(el) -> str:
    """Get all text content of an element (including child text)."""
    return re.sub(r'\s+', ' ', ''.join(el.itertext())).strip()


def tokenize(text: str) -> list[dict]:
    """Split Latin text into word tokens for clickable lookup."""
    tokens = []
    for part in re.split(r'\s+', text):
        form = re.sub(r"^[^a-zA-ZāēīōūÀ-ÿ']+|[^a-zA-ZāēīōūÀ-ÿ']+$", '', part)
        if form and len(form) > 0:
            tokens.append({'form': form})
    return tokens


# ── Latin text parsers ────────────────────────────────────────────────────────

def parse_lat_poem(xml: bytes) -> dict:
    """Poetry with per-poem structure (Catullus, Horace, Eclogues).
    Returns: {poem_key: {'lines': [(num, text)], 'title': str}}
    poem_key = (book_n, poem_n) or poem_n for flat collections."""
    root = ET.fromstring(xml)
    body = root.find(f'.//{tei("body")}')
    result = {}

    def collect_poems(parent, book_n=None):
        for child in parent:
            tag = child.tag.split('}')[-1]
            subtype = child.get('subtype', '')
            n = child.get('n', '')

            if tag != 'div':
                continue
            if subtype == 'book':
                collect_poems(child, book_n=n)
            elif subtype in ('poem', 'ode', 'eclogue', 'section'):
                poem_n = n
                title_el = child.find(tei('head'))
                title = el_text(title_el) if title_el is not None else ''
                lines = []
                for l in child.iter(tei('l')):
                    line_n = l.get('n', str(len(lines) + 1))
                    lines.append((int(line_n) if line_n.isdigit() else len(lines) + 1, el_text(l)))
                if lines:
                    key = (book_n or '0', poem_n)
                    result[key] = {'lines': lines, 'title': title}
            else:
                # edition/translation/textpart wrapper — recurse transparently
                collect_poems(child, book_n=book_n)

    collect_poems(body)
    return result


def parse_lat_card(xml: bytes) -> dict:
    """Epic/philosophical poetry with numbered lines (Aeneid, Lucretius).
    Returns: {book_n: [(line_num, text), ...]}"""
    root = ET.fromstring(xml)
    body = root.find(f'.//{tei("body")}')
    result = {}

    for book_div in body.iter():
        if book_div.tag != tei('div'):
            continue
        if book_div.get('subtype') != 'book':
            continue
        book_n = book_div.get('n', '?')
        lines = []
        for l in book_div.iter(tei('l')):
            ln = l.get('n', '')
            if ln.isdigit():
                text = el_text(l)
                if text:
                    lines.append((int(ln), text))
        if lines:
            result[book_n] = sorted(lines, key=lambda x: x[0])

    return result


def parse_lat_chapter(xml: bytes) -> dict:
    """Prose with book/chapter structure (Caesar, Cicero).
    Returns: {(book_n, chapter_n): [sentence_text, ...]}"""
    root = ET.fromstring(xml)
    body = root.find(f'.//{tei("body")}')
    result = {}

    for book_div in body.iter():
        if book_div.tag != tei('div') or book_div.get('subtype') != 'book':
            continue
        book_n = book_div.get('n', '?')
        for ch_div in book_div:
            if ch_div.tag != tei('div') or ch_div.get('subtype') != 'chapter':
                continue
            ch_n = ch_div.get('n', '?')
            sentences = []
            for p in ch_div.iter(tei('p')):
                text = el_text(p)
                if text and len(text) > 10:
                    sentences.append(text)
            if not sentences:
                text = el_text(ch_div)
                if text and len(text) > 10:
                    sentences = [text]
            if sentences:
                result[(book_n, ch_n)] = sentences

    return result


# ── English text parsers ──────────────────────────────────────────────────────

def parse_eng_poem(xml: bytes) -> dict:
    """English translations of poem collections.
    Returns: {(book_n, poem_n): {'text_en': str, 'title': str}}"""
    root = ET.fromstring(xml)
    body = root.find(f'.//{tei("body")}')
    result = {}

    def collect(parent, book_n=None):
        for child in parent:
            tag = child.tag.split('}')[-1]
            subtype = child.get('subtype', '')
            n = child.get('n', '')

            if tag != 'div':
                continue
            if subtype == 'book':
                collect(child, book_n=n)
            elif subtype in ('poem', 'ode', 'eclogue', 'section'):
                title_el = child.find(tei('head'))
                title = el_text(title_el) if title_el is not None else ''
                lines = [el_text(l) for l in child.iter(tei('l')) if el_text(l)]
                text_en = ' '.join(lines).strip()
                if text_en:
                    key = (book_n or '0', n)
                    result[key] = {'text_en': text_en, 'title': title}
            else:
                collect(child, book_n=book_n)

    collect(body)
    return result


def parse_eng_card(xml: bytes) -> dict:
    """English translations grouped by 'card' (line ranges).
    Returns: {book_n: [{line_from, line_to, text_en}, ...]}"""
    root = ET.fromstring(xml)
    body = root.find(f'.//{tei("body")}')
    result = {}

    for book_div in body.iter():
        if book_div.tag != tei('div') or book_div.get('subtype') != 'book':
            continue
        book_n = book_div.get('n', '?')
        cards = []

        for card_div in book_div:
            if card_div.tag != tei('div') or card_div.get('subtype') != 'card':
                continue
            card_start = card_div.get('n', '0')
            lines = [(l.get('n', '0'), el_text(l)) for l in card_div.iter(tei('l'))]
            lines = [(n, t) for n, t in lines if t]
            if not lines:
                continue
            # Determine line range: card_start to last line in card
            try:
                line_from = int(card_start)
            except ValueError:
                line_from = 1
            try:
                line_to = max(int(n) for n, _ in lines if n.isdigit())
            except (ValueError, TypeError):
                line_to = line_from
            text_en = ' '.join(t for _, t in lines)
            if text_en:
                cards.append({'line_from': line_from, 'line_to': line_to, 'text_en': text_en})

        if cards:
            result[book_n] = cards

    return result


def parse_eng_chapter(xml: bytes) -> dict:
    """English translations of prose chapters.
    Returns: {(book_n, chapter_n): text_en}"""
    root = ET.fromstring(xml)
    body = root.find(f'.//{tei("body")}')
    result = {}

    for book_div in body.iter():
        if book_div.tag != tei('div') or book_div.get('subtype') != 'book':
            continue
        book_n = book_div.get('n', '?')
        for ch_div in book_div:
            if ch_div.tag != tei('div') or ch_div.get('subtype') != 'chapter':
                continue
            ch_n = ch_div.get('n', '?')
            text = el_text(ch_div)
            if text and len(text) > 20:
                result[(book_n, ch_n)] = text

    return result


# ── import driver ─────────────────────────────────────────────────────────────

def import_poem_mode(conn, tid: str, lat: dict, eng: dict):
    """Import poem-based texts: each poem = one lit_paragraph."""
    line_counter = 0
    ok = 0

    for key, lat_data in sorted(lat.items()):
        eng_data = eng.get(key) or eng.get(('0', key[1])) or {}
        text_en = eng_data.get('text_en', '')
        title_en = eng_data.get('title', lat_data.get('title', ''))

        if not lat_data['lines']:
            continue

        # Insert paragraph
        conn.execute(
            'INSERT INTO lit_paragraphs(text_id,line_from,line_to,text_en)'
            ' VALUES(?,?,?,?)',
            (tid, line_counter + 1,
             line_counter + len(lat_data['lines']),
             text_en or '[Tradução não disponível]')
        )
        para_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

        # Insert lines
        for seq, (_, line_text) in enumerate(lat_data['lines']):
            line_counter += 1
            words = tokenize(line_text)
            conn.execute(
                'INSERT OR REPLACE INTO lit_lines(text_id,line_num,translit,words_json,para_id)'
                ' VALUES(?,?,?,?,?)',
                (tid, line_counter, line_text,
                 json.dumps(words, ensure_ascii=False), para_id)
            )
        ok += 1

    return ok


def import_card_mode(conn, tid: str, lat: dict, eng: dict):
    """Import line-based poetry with English 'cards'."""
    line_counter = 0
    ok = 0

    for book_n in sorted(lat.keys()):
        lat_lines = {num: text for num, text in lat[book_n]}
        eng_cards = eng.get(book_n, [])

        if not eng_cards:
            # No English: create one paragraph per 20 Latin lines
            lat_sorted = sorted(lat_lines.items())
            for i in range(0, len(lat_sorted), 20):
                chunk = lat_sorted[i:i+20]
                conn.execute(
                    'INSERT INTO lit_paragraphs(text_id,line_from,line_to,text_en)'
                    ' VALUES(?,?,?,?)',
                    (tid, line_counter + 1, line_counter + len(chunk),
                     '[Tradução não disponível]')
                )
                para_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
                for _, (line_n, line_text) in zip(range(len(chunk)), chunk):
                    line_counter += 1
                    words = tokenize(line_text)
                    conn.execute(
                        'INSERT OR REPLACE INTO lit_lines(text_id,line_num,translit,words_json,para_id)'
                        ' VALUES(?,?,?,?,?)',
                        (tid, line_counter, line_text,
                         json.dumps(words, ensure_ascii=False), para_id)
                    )
                ok += 1
            continue

        # Match Latin lines to English cards by line number
        for card in eng_cards:
            lf, lt, text_en = card['line_from'], card['line_to'], card['text_en']
            card_lat_lines = [(n, t) for n, t in lat[book_n] if lf <= n <= lt]
            if not card_lat_lines:
                # Try extending range slightly
                card_lat_lines = [(n, t) for n, t in lat[book_n]
                                  if abs(n - lf) <= 5][:5]

            if not card_lat_lines:
                continue

            conn.execute(
                'INSERT INTO lit_paragraphs(text_id,line_from,line_to,text_en)'
                ' VALUES(?,?,?,?)',
                (tid, line_counter + 1, line_counter + len(card_lat_lines), text_en)
            )
            para_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            for _, (line_n, line_text) in enumerate(card_lat_lines):
                line_counter += 1
                words = tokenize(line_text)
                conn.execute(
                    'INSERT OR REPLACE INTO lit_lines(text_id,line_num,translit,words_json,para_id)'
                    ' VALUES(?,?,?,?,?)',
                    (tid, line_counter, line_text,
                     json.dumps(words, ensure_ascii=False), para_id)
                )
            ok += 1

    return ok


def import_chapter_mode(conn, tid: str, lat: dict, eng: dict):
    """Import prose texts: each chapter = one lit_paragraph."""
    line_counter = 0
    ok = 0

    for key in sorted(lat.keys()):
        sentences = lat[key]
        text_en = eng.get(key, '')
        if not sentences:
            continue

        conn.execute(
            'INSERT INTO lit_paragraphs(text_id,line_from,line_to,text_en)'
            ' VALUES(?,?,?,?)',
            (tid, line_counter + 1, line_counter + len(sentences),
             text_en or '[Tradução não disponível]')
        )
        para_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

        for sent in sentences:
            line_counter += 1
            words = tokenize(sent)
            conn.execute(
                'INSERT OR REPLACE INTO lit_lines(text_id,line_num,translit,words_json,para_id)'
                ' VALUES(?,?,?,?,?)',
                (tid, line_counter, sent,
                 json.dumps(words, ensure_ascii=False), para_id)
            )
        ok += 1

    return ok


def import_text(conn: sqlite3.Connection, text_def: dict) -> bool:
    tid      = text_def['id']
    title_en = text_def['title_en']
    title_pt = f'{text_def["author_pt"]}, {text_def["title_pt"]}'
    corpus   = text_def.get('corpus', 'perseus')
    note     = text_def.get('note', '')
    mode     = text_def['mode']

    print(f'  Importing {tid}: {title_pt}…')

    lat_xml = fetch_xml(text_def['phi_author'], text_def['phi_work'], text_def['lat_file'])
    eng_xml = fetch_xml(text_def['phi_author'], text_def['phi_work'], text_def['eng_file'])

    if lat_xml is None:
        print(f'    ✗ sem XML latino — saltar')
        return False

    # Parse
    if mode == 'poem':
        lat = parse_lat_poem(lat_xml)
        eng = parse_eng_poem(eng_xml) if eng_xml else {}
    elif mode == 'card':
        lat = parse_lat_card(lat_xml)
        eng = parse_eng_card(eng_xml) if eng_xml else {}
    elif mode == 'chapter':
        lat = parse_lat_chapter(lat_xml)
        eng = parse_eng_chapter(eng_xml) if eng_xml else {}
    else:
        print(f'    ✗ mode desconhecido: {mode}')
        return False

    if not lat:
        print(f'    ✗ sem linhas latinas extraídas')
        return False

    # Upsert text record
    conn.execute(
        'INSERT OR REPLACE INTO lit_texts(id,title_en,title_pt,corpus,lang,note)'
        ' VALUES(?,?,?,?,?,?)',
        (tid, title_en, title_pt, corpus, 'lat', note)
    )
    conn.execute('DELETE FROM lit_lines      WHERE text_id=?', (tid,))
    conn.execute('DELETE FROM lit_paragraphs WHERE text_id=?', (tid,))

    # Import sections
    if mode == 'poem':
        ok = import_poem_mode(conn, tid, lat, eng)
    elif mode == 'card':
        ok = import_card_mode(conn, tid, lat, eng)
    else:
        ok = import_chapter_mode(conn, tid, lat, eng)

    n_lines  = conn.execute('SELECT COUNT(*) FROM lit_lines WHERE text_id=?', (tid,)).fetchone()[0]
    n_paras  = conn.execute('SELECT COUNT(*) FROM lit_paragraphs WHERE text_id=?', (tid,)).fetchone()[0]
    print(f'    ✓ {n_paras} secções, {n_lines} linhas')
    return True


# ── schema migration ──────────────────────────────────────────────────────────

def apply_schema(conn: sqlite3.Connection):
    cols = [r[1] for r in conn.execute('PRAGMA table_info(lit_texts)').fetchall()]
    if 'note' not in cols:
        conn.execute('ALTER TABLE lit_texts ADD COLUMN note TEXT')
        print('  Adicionada coluna note.')


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    apply_schema(conn)

    ok = fail = 0
    for text_def in TEXTS:
        if import_text(conn, text_def):
            ok += 1
        else:
            fail += 1
        conn.commit()

    print('\nRebuildando FTS…')
    try:
        conn.execute("INSERT INTO lit_fts(lit_fts) VALUES('rebuild')")
    except Exception:
        pass
    conn.commit()
    conn.close()
    print(f'Concluído: {ok} textos importados, {fail} falhados.')


if __name__ == '__main__':
    main()
