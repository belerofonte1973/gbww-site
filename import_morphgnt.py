#!/usr/bin/env python3
"""Download MorphGNT SBLGNT files and import into classics.db."""

import sqlite3
import urllib.request
from pathlib import Path

DB_PATH   = Path(__file__).parent / 'classics.db'
DATA_DIR  = Path(__file__).parent / 'data' / 'morphgnt'
BASE_URL  = 'https://raw.githubusercontent.com/morphgnt/sblgnt/master/'

BOOKS = [
    (1,  'Mt',  '61-Mt-morphgnt.txt',  'Κατὰ Μαθθαῖον',          'Mateus',            28),
    (2,  'Mk',  '62-Mk-morphgnt.txt',  'Κατὰ Μάρκον',             'Marcos',            16),
    (3,  'Lk',  '63-Lk-morphgnt.txt',  'Κατὰ Λουκᾶν',             'Lucas',             24),
    (4,  'Jn',  '64-Jn-morphgnt.txt',  'Κατὰ Ἰωάννην',            'João',              21),
    (5,  'Ac',  '65-Ac-morphgnt.txt',  'Πράξεις',                 'Actos',             28),
    (6,  'Ro',  '66-Ro-morphgnt.txt',  'Πρὸς Ῥωμαίους',           'Romanos',           16),
    (7,  '1Co', '67-1Co-morphgnt.txt', 'Πρὸς Κορινθίους Αʹ',      '1 Coríntios',       16),
    (8,  '2Co', '68-2Co-morphgnt.txt', 'Πρὸς Κορινθίους Βʹ',      '2 Coríntios',       13),
    (9,  'Ga',  '69-Ga-morphgnt.txt',  'Πρὸς Γαλάτας',            'Gálatas',            6),
    (10, 'Ep',  '70-Eph-morphgnt.txt', 'Πρὸς Ἐφεσίους',           'Efésios',            6),
    (11, 'Ph',  '71-Php-morphgnt.txt', 'Πρὸς Φιλιππησίους',       'Filipenses',         4),
    (12, 'Col', '72-Col-morphgnt.txt', 'Πρὸς Κολοσσαεῖς',         'Colossenses',        4),
    (13, '1Th', '73-1Th-morphgnt.txt', 'Πρὸς Θεσσαλονικεῖς Αʹ',  '1 Tessalonicenses',  5),
    (14, '2Th', '74-2Th-morphgnt.txt', 'Πρὸς Θεσσαλονικεῖς Βʹ',  '2 Tessalonicenses',  3),
    (15, '1Ti', '75-1Ti-morphgnt.txt', 'Πρὸς Τιμόθεον Αʹ',        '1 Timóteo',          6),
    (16, '2Ti', '76-2Ti-morphgnt.txt', 'Πρὸς Τιμόθεον Βʹ',        '2 Timóteo',          4),
    (17, 'Tit', '77-Tit-morphgnt.txt', 'Πρὸς Τίτον',              'Tito',               3),
    (18, 'Phm', '78-Phm-morphgnt.txt', 'Πρὸς Φιλήμονα',           'Filemon',            1),
    (19, 'Heb', '79-Heb-morphgnt.txt', 'Πρὸς Ἑβραίους',           'Hebreus',           13),
    (20, 'Jas', '80-Jas-morphgnt.txt', 'Ἰακώβου',                  'Tiago',              5),
    (21, '1Pe', '81-1Pe-morphgnt.txt', 'Πέτρου Αʹ',               '1 Pedro',            5),
    (22, '2Pe', '82-2Pe-morphgnt.txt', 'Πέτρου Βʹ',               '2 Pedro',            3),
    (23, '1Jn', '83-1Jn-morphgnt.txt', 'Ἰωάννου Αʹ',              '1 João',             5),
    (24, '2Jn', '84-2Jn-morphgnt.txt', 'Ἰωάννου Βʹ',              '2 João',             1),
    (25, '3Jn', '85-3Jn-morphgnt.txt', 'Ἰωάννου Γʹ',              '3 João',             1),
    (26, 'Jud', '86-Jud-morphgnt.txt', 'Ἰούδα',                    'Judas',              1),
    (27, 'Re',  '87-Re-morphgnt.txt',  'Ἀποκάλυψις',              'Apocalipse',        22),
]

# ── parsing label maps ─────────────────────────────────────────────────────────

PERSON = {'1': '1ª', '2': '2ª', '3': '3ª', '-': ''}
TENSE  = {
    'P': 'pres.', 'I': 'imperf.', 'F': 'fut.',
    'A': 'aor.', 'X': 'perf.', 'Y': 'mais-que-perf.', '-': ''
}
VOICE  = {'A': 'act.', 'M': 'méd.', 'P': 'pass.', '-': ''}
MOOD   = {
    'I': 'ind.', 'D': 'imp.', 'S': 'subj.',
    'O': 'opt.', 'N': 'inf.', 'P': 'part.', '-': ''
}
CASE   = {'N': 'nom.', 'G': 'gen.', 'D': 'dat.', 'A': 'ac.', 'V': 'voc.', '-': ''}
NUMBER = {'S': 'sg.', 'P': 'pl.', '-': ''}
GENDER = {'M': 'masc.', 'F': 'fem.', 'N': 'neutro', '-': ''}
DEGREE = {'C': 'comp.', 'S': 'superl.', '-': ''}

POS_LABEL = {
    'A-': 'adj.', 'C-': 'conj.', 'D-': 'adv.',
    'I-': 'interj.', 'N-': 'subst.', 'P-': 'prep.',
    'RA': 'artigo', 'RD': 'pron. dem.', 'RI': 'pron. indef.',
    'RP': 'pron. pess.', 'RR': 'pron. rel.', 'V-': 'verb.', 'X-': 'part.',
}


def parse_desc(pos: str, parsing: str) -> str:
    """Return Portuguese morphological description for a MorphGNT token."""
    if len(parsing) != 8:
        return POS_LABEL.get(pos, pos)
    p0, p1, p2, p3, p4, p5, p6, p7 = list(parsing)
    label = POS_LABEL.get(pos, pos)
    parts = [label] if label else []

    if pos == 'V-':
        if p3 == 'P':   # particípio
            for x in (TENSE[p1], VOICE[p2], 'part.', CASE[p4], NUMBER[p5], GENDER[p6]):
                if x: parts.append(x)
        elif p3 == 'N': # infinitivo
            for x in (TENSE[p1], VOICE[p2], 'inf.'):
                if x: parts.append(x)
        else:           # forma finita
            for x in (TENSE[p1], VOICE[p2], MOOD[p3]):
                if x: parts.append(x)
            if p0 != '-':
                parts.append(f'{PERSON[p0]} {NUMBER[p5]}')
            elif p5 != '-':
                parts.append(NUMBER[p5])
    else:
        for x in (CASE[p4], NUMBER[p5], GENDER[p6], DEGREE[p7]):
            if x: parts.append(x)

    return ' '.join(parts)


# ── schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    num       INTEGER PRIMARY KEY,
    code      TEXT UNIQUE NOT NULL,
    name_gk   TEXT NOT NULL,
    name_pt   TEXT NOT NULL,
    chapters  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
    id        INTEGER PRIMARY KEY,
    book_num  INTEGER NOT NULL,
    chapter   INTEGER NOT NULL,
    verse     INTEGER NOT NULL,
    position  INTEGER NOT NULL,
    text      TEXT NOT NULL,
    word      TEXT NOT NULL,
    lemma     TEXT NOT NULL,
    pos       TEXT NOT NULL,
    parsing   TEXT NOT NULL,
    desc_pt   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tok_bcv   ON tokens(book_num, chapter, verse);
CREATE INDEX IF NOT EXISTS idx_tok_lemma ON tokens(lemma);

CREATE VIRTUAL TABLE IF NOT EXISTS tokens_fts USING fts5(
    lemma, word,
    content='tokens', content_rowid='id'
);
"""

# ── helpers ───────────────────────────────────────────────────────────────────

def download_files():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for _, _, filename, *_ in BOOKS:
        path = DATA_DIR / filename
        if not path.exists():
            url = BASE_URL + filename
            print(f'  ↓ {filename}')
            urllib.request.urlretrieve(url, path)
        else:
            print(f'  ✓ {filename}')


def parse_line(line: str):
    """Return (book, chapter, verse, pos, parsing, text, word, lemma) or None."""
    parts = line.strip().split()
    if len(parts) < 7:
        return None
    bcv      = parts[0]
    book     = int(bcv[:2])
    chapter  = int(bcv[2:4])
    verse    = int(bcv[4:6])
    pos      = parts[1]
    parsing  = parts[2]
    text     = parts[3]
    word     = parts[4]
    lemma    = parts[6]
    return book, chapter, verse, pos, parsing, text, word, lemma


def import_book(conn, num, code, filename, name_gk, name_pt, chapters):
    path = DATA_DIR / filename
    if not path.exists():
        print(f'  FALTA {filename}')
        return

    conn.execute('INSERT OR REPLACE INTO books VALUES (?,?,?,?,?)',
                 (num, code, name_gk, name_pt, chapters))
    conn.execute('DELETE FROM tokens WHERE book_num=?', (num,))

    pos_in_verse: dict = {}
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            parsed = parse_line(line)
            if not parsed:
                continue
            book, chapter, verse, pos, parsing, text, word, lemma = parsed
            key = (chapter, verse)
            pos_in_verse[key] = pos_in_verse.get(key, 0) + 1
            desc = parse_desc(pos, parsing)
            rows.append((book, chapter, verse, pos_in_verse[key],
                         text, word, lemma, pos, parsing, desc))

    conn.executemany(
        'INSERT INTO tokens'
        '(book_num,chapter,verse,position,text,word,lemma,pos,parsing,desc_pt)'
        ' VALUES (?,?,?,?,?,?,?,?,?,?)',
        rows
    )
    print(f'  {code}: {len(rows)} tokens')


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print('Downloading MorphGNT…')
    download_files()

    print('Creating database…')
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    print('Importing books…')
    for book_data in BOOKS:
        import_book(conn, *book_data)

    print('Building FTS index…')
    conn.execute("INSERT INTO tokens_fts(tokens_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
