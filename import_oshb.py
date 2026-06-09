#!/usr/bin/env python3
"""Download OSHB XML + Strong's dictionary and import Hebrew OT into classics.db."""

import json
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

DB_PATH     = Path(__file__).parent / 'classics.db'
DATA_DIR    = Path(__file__).parent / 'data' / 'oshb'
OSHB_URL    = 'https://raw.githubusercontent.com/openscriptures/morphhb/master/wlc/'
STRONGS_URL = ('https://raw.githubusercontent.com/openscriptures/strongs'
               '/master/hebrew/strongs-hebrew-dictionary.js')
OSIS_NS     = 'http://www.bibletechnologies.net/2003/OSIS/namespace'

BOOKS = [
    (101, 'Gen',  'Gen.xml',  'בְּרֵאשִׁית',         'Génesis',      50),
    (102, 'Ex',   'Exod.xml', 'שְׁמוֹת',             'Êxodo',        40),
    (103, 'Lv',   'Lev.xml',  'וַיִּקְרָא',          'Levítico',     27),
    (104, 'Nm',   'Num.xml',  'בְּמִדְבַּר',         'Números',      36),
    (105, 'Dt',   'Deut.xml', 'דְּבָרִים',           'Deuteronómio', 34),
    (106, 'Jos',  'Josh.xml', 'יְהוֹשֻׁעַ',          'Josué',        24),
    (107, 'Jz',   'Judg.xml', 'שׁוֹפְטִים',          'Juízes',       21),
    (108, 'Rt',   'Ruth.xml', 'רוּת',                'Rute',          4),
    (109, '1Sm',  '1Sam.xml', 'שְׁמוּאֵל א׳',       '1 Samuel',     31),
    (110, '2Sm',  '2Sam.xml', 'שְׁמוּאֵל ב׳',       '2 Samuel',     24),
    (111, '1Rs',  '1Kgs.xml', 'מְלָכִים א׳',         '1 Reis',       22),
    (112, '2Rs',  '2Kgs.xml', 'מְלָכִים ב׳',         '2 Reis',       25),
    (113, '1Cr',  '1Chr.xml', 'דִּבְרֵי הַיָּמִים א׳', '1 Crónicas', 29),
    (114, '2Cr',  '2Chr.xml', 'דִּבְרֵי הַיָּמִים ב׳', '2 Crónicas', 36),
    (115, 'Esd',  'Ezra.xml', 'עֶזְרָא',             'Esdras',       10),
    (116, 'Ne',   'Neh.xml',  'נְחֶמְיָה',           'Neemias',      13),
    (117, 'Est',  'Esth.xml', 'אֶסְתֵּר',            'Ester',        10),
    (118, 'Job',  'Job.xml',  'אִיּוֹב',             'Jó',           42),
    (119, 'Sl',   'Ps.xml',   'תְּהִלִּים',          'Salmos',      150),
    (120, 'Pv',   'Prov.xml', 'מִשְׁלֵי',            'Provérbios',   31),
    (121, 'Ec',   'Eccl.xml', 'קֹהֶלֶת',            'Eclesiastes',  12),
    (122, 'Ct',   'Song.xml', 'שִׁיר הַשִּׁירִים',   'Cântico',       8),
    (123, 'Is',   'Isa.xml',  'יְשַׁעְיָהוּ',        'Isaías',       66),
    (124, 'Jr',   'Jer.xml',  'יִרְמְיָהוּ',         'Jeremias',     52),
    (125, 'Lm',   'Lam.xml',  'אֵיכָה',             'Lamentações',   5),
    (126, 'Ez',   'Ezek.xml', 'יְחֶזְקֵאל',         'Ezequiel',     48),
    (127, 'Dn',   'Dan.xml',  'דָּנִיֵּאל',          'Daniel',       12),
    (128, 'Os',   'Hos.xml',  'הוֹשֵׁעַ',            'Oseias',       14),
    (129, 'Jl',   'Joel.xml', 'יוֹאֵל',             'Joel',           3),
    (130, 'Am',   'Amos.xml', 'עָמוֹס',             'Amós',           9),
    (131, 'Ob',   'Obad.xml', 'עֹבַדְיָה',          'Obadias',        1),
    (132, 'Jon',  'Jonah.xml','יוֹנָה',             'Jonas',           4),
    (133, 'Mq',   'Mic.xml',  'מִיכָה',             'Miqueias',       7),
    (134, 'Na',   'Nah.xml',  'נַחוּם',             'Naum',           3),
    (135, 'Hab',  'Hab.xml',  'חֲבַקּוּק',          'Habacuque',      3),
    (136, 'Sf',   'Zeph.xml', 'צְפַנְיָה',          'Sofonias',       3),
    (137, 'Ag',   'Hag.xml',  'חַגַּי',             'Ageu',           2),
    (138, 'Zc',   'Zech.xml', 'זְכַרְיָה',          'Zacarias',      14),
    (139, 'Ml',   'Mal.xml',  'מַלְאָכִי',          'Malaquias',      4),
]

# ── Hebrew morphology → Portuguese ───────────────────────────────────────────

_STEM = {
    'q': 'Qal', 'N': 'Nifal', 'p': 'Piel', 'P': 'Pual',
    'h': 'Hifil', 'H': 'Hofal', 't': 'Hitpael', 'o': 'Polel',
    'O': 'Polal', 'r': 'Hitpolel', 'm': 'Poel', 'M': 'Poal',
    'k': 'Palel', 'K': 'Pulal', 'Q': 'Qal pass.', 'l': 'Pilel',
    'f': 'Piel', 'D': 'Piel', 'e': 'Poel', 'j': 'Peal', 'i': 'Peil',
    'u': 'Hitpeel', 'v': 'Afel', 'V': 'Shafel', 'w': 'Shafel',
    'a': 'Afel', 'A': 'Hafel', 'z': 'Hafel',
}
_ASPECT = {
    'p': 'pf.', 'q': 'pf.', 'i': 'impf.', 'w': 'wayyiqtol',
    'h': 'cort.', 'j': 'juss.', 'v': 'imp.',
    'r': 'part. act.', 's': 'part. pass.',
    'a': 'inf. abs.', 'c': 'inf. constr.',
}
_PERSON = {'1': '1ª', '2': '2ª', '3': '3ª', 'x': ''}
_GENDER = {'m': 'masc.', 'f': 'fem.', 'c': 'com.', 'b': 'masc./fem.'}
_NUMBER = {'s': 'sg.', 'p': 'pl.', 'd': 'dual'}
_STATE  = {'a': 'abs.', 'c': 'constr.', 'd': 'det.'}
_NTYPE  = {'c': 'subst.', 'g': 'gent.', 'p': 'nome próprio'}
_PTYPE  = {
    'd': 'pron. dem.', 'f': 'pron. indef.', 'i': 'pron. int.',
    'p': 'pron. pess.', 'r': 'pron. rel.', 'x': 'pron.',
}
_ATYPE  = {'a': 'adj.', 'g': 'adj. gent.', 'o': 'numeral ord.'}
_TTYPE  = {
    'a': 'art.', 'd': 'art.', 'e': 'exort.', 'i': 'interrog.',
    'j': 'juss.', 'm': 'dem.', 'n': 'neg.', 'o': 'marca ac.',
    'r': 'rel.', 'x': 'part.',
}
_POS_LABEL = {
    'A': 'adj.', 'C': 'conj.', 'D': 'adv.', 'N': 'subst.',
    'P': 'prep.', 'R': 'pron.', 'S': 'suf.', 'T': 'part.', 'V': 'verb.',
}


def _root_desc(code: str) -> str:
    if not code:
        return ''
    pos, rest = code[0], code[1:]
    if pos == 'V':
        parts = ['verb.']
        if rest:     parts.append(_STEM.get(rest[0], ''))
        if len(rest) > 1: parts.append(_ASPECT.get(rest[1], ''))
        pgn = []
        p = _PERSON.get(rest[2], '') if len(rest) > 2 else ''
        g = _GENDER.get(rest[3], '') if len(rest) > 3 else ''
        n = _NUMBER.get(rest[4], '') if len(rest) > 4 else ''
        if p: pgn.append(p)
        if g: pgn.append(g)
        if n: pgn.append(n)
        if pgn: parts.append(' '.join(pgn))
        return ' '.join(x for x in parts if x)
    elif pos == 'N':
        parts = [_NTYPE.get(rest[0], 'subst.') if rest else 'subst.']
        for c, m in zip(rest[1:4], [_GENDER, _NUMBER, _STATE]):
            v = m.get(c, '')
            if v: parts.append(v)
        return ' '.join(parts)
    elif pos == 'A':
        parts = [_ATYPE.get(rest[0], 'adj.') if rest else 'adj.']
        for c, m in zip(rest[1:4], [_GENDER, _NUMBER, _STATE]):
            v = m.get(c, '')
            if v: parts.append(v)
        return ' '.join(parts)
    elif pos == 'R':
        parts = [_PTYPE.get(rest[0], 'pron.') if rest else 'pron.']
        pgn = []
        p = _PERSON.get(rest[1], '') if len(rest) > 1 else ''
        g = _GENDER.get(rest[2], '') if len(rest) > 2 else ''
        n = _NUMBER.get(rest[3], '') if len(rest) > 3 else ''
        if p: pgn.append(p)
        if g: pgn.append(g)
        if n: pgn.append(n)
        if pgn: parts.append(' '.join(pgn))
        return ' '.join(parts)
    elif pos == 'T':
        return _TTYPE.get(rest[0], 'part.') if rest else 'part.'
    elif pos == 'S':
        parts = ['suf.']
        pgn = []
        p = _PERSON.get(rest[0], '') if rest else ''
        g = _GENDER.get(rest[1], '') if len(rest) > 1 else ''
        n = _NUMBER.get(rest[2], '') if len(rest) > 2 else ''
        if p: pgn.append(p)
        if g: pgn.append(g)
        if n: pgn.append(n)
        if pgn: parts.append(' '.join(pgn))
        return ' '.join(parts)
    return _POS_LABEL.get(pos, pos)


def _prefix_desc(seg: str) -> str:
    if seg == 'C':    return 'conj.'
    if seg == 'P':    return 'prep.'
    if seg == 'R':    return 'prep.'
    if seg == 'Td':   return 'art.'
    if seg.startswith('T'): return _TTYPE.get(seg[1:], 'part.')
    return ''


def parse_heb_desc(morph: str) -> str:
    """Convert OSHB morph code (e.g. 'HC/Vqw3ms') to Portuguese description."""
    if not morph or len(morph) < 2:
        return ''
    code = morph[1:]               # strip H/A language prefix
    segments = code.split('/')
    prefix_parts = [_prefix_desc(s) for s in segments[:-1] if _prefix_desc(s)]
    root = _root_desc(segments[-1])
    parts = prefix_parts + ([root] if root else [])
    return ' + '.join(parts) if parts else ''


def extract_strong(lemma: str) -> str:
    """Return main Strong's number from OSHB lemma (e.g. 'b/7225' → 'H7225')."""
    last = lemma.split('/')[-1].strip()
    parts = last.split()
    if parts and parts[0].isdigit():
        suffix = parts[1] if len(parts) > 1 else ''
        return f'H{parts[0]}{suffix}'
    return ''


# ── Strong's dictionary ───────────────────────────────────────────────────────

def load_strongs_js(path: Path) -> dict:
    """Parse the JS wrapper around the Strong's Hebrew JSON dict."""
    text = path.read_text(encoding='utf-8')
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return {}
    return json.loads(m.group(0))


# ── XML parser ────────────────────────────────────────────────────────────────

W_TAG    = f'{{{OSIS_NS}}}w'
VERSE_TAG = f'{{{OSIS_NS}}}verse'


def parse_oshb_book(path: Path):
    """Yield (chapter, verse, position, text, lemma_raw, strong_num, morph, desc_pt)."""
    tree = ET.parse(path)
    position = 0
    cur_ch = cur_v = None

    for elem in tree.iter():
        tag = elem.tag

        if tag == VERSE_TAG:
            osisID = elem.get('osisID', '')
            parts  = osisID.split('.')
            if len(parts) == 3:
                cur_ch = int(parts[1])
                cur_v  = int(parts[2])
                position = 0
            # OSHB sometimes uses container verses → iterate children separately
            pos_in_verse = 0
            for w in elem.iter(W_TAG):
                pos_in_verse += 1
                raw  = ''.join(w.itertext()).replace('/', '').strip()
                if not raw:
                    continue
                lemma_raw = w.get('lemma', '')
                morph     = w.get('morph', '')
                strong    = extract_strong(lemma_raw)
                desc      = parse_heb_desc(morph)
                yield (cur_ch, cur_v, pos_in_verse, raw, lemma_raw, strong, morph, desc)


# ── schema migration ──────────────────────────────────────────────────────────

MIGRATION = """
ALTER TABLE books ADD COLUMN lang TEXT DEFAULT 'grc';
ALTER TABLE tokens ADD COLUMN strong_num TEXT DEFAULT '';

CREATE TABLE IF NOT EXISTS strongs_heb (
    num         TEXT PRIMARY KEY,
    lemma_heb   TEXT,
    xlit        TEXT,
    definition  TEXT
);
"""


def migrate_schema(conn):
    existing = {r[1] for r in conn.execute("PRAGMA table_info(books)").fetchall()}
    if 'lang' not in existing:
        conn.execute("ALTER TABLE books ADD COLUMN lang TEXT DEFAULT 'grc'")
    existing_tok = {r[1] for r in conn.execute("PRAGMA table_info(tokens)").fetchall()}
    if 'strong_num' not in existing_tok:
        conn.execute("ALTER TABLE tokens ADD COLUMN strong_num TEXT DEFAULT ''")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strongs_heb (
            num        TEXT PRIMARY KEY,
            lemma_heb  TEXT,
            xlit       TEXT,
            definition TEXT
        )
    """)


# ── download helpers ──────────────────────────────────────────────────────────

def download(url: str, dest: Path):
    if not dest.exists():
        print(f'  ↓ {dest.name}')
        urllib.request.urlretrieve(url, dest)
    else:
        print(f'  ✓ {dest.name}')


# ── import ────────────────────────────────────────────────────────────────────

def import_strongs(conn, path: Path):
    print('Importing Strong\'s Hebrew dictionary…')
    data = load_strongs_js(path)
    rows = []
    for key, val in data.items():
        rows.append((
            key,
            val.get('lemma', ''),
            val.get('xlit', ''),
            val.get('strongs_def', '') or val.get('kjv_def', ''),
        ))
    conn.execute('DELETE FROM strongs_heb')
    conn.executemany(
        'INSERT OR REPLACE INTO strongs_heb(num, lemma_heb, xlit, definition) VALUES(?,?,?,?)',
        rows
    )
    print(f'  {len(rows)} entries')


def import_book(conn, num, code, filename, name_hk, name_pt, chapters):
    path = DATA_DIR / filename
    if not path.exists():
        print(f'  FALTA {filename}')
        return

    conn.execute('INSERT OR REPLACE INTO books(num,code,name_gk,name_pt,chapters,lang) VALUES(?,?,?,?,?,?)',
                 (num, code, name_hk, name_pt, chapters, 'heb'))
    conn.execute('DELETE FROM tokens WHERE book_num=?', (num,))

    rows = []
    for ch, v, pos, text, lemma_raw, strong, morph, desc in parse_oshb_book(path):
        rows.append((num, ch, v, pos, text, text, strong, pos, morph, desc, strong))
    #           (book_num, chapter, verse, position, text, word, lemma, pos, parsing, desc_pt, strong_num)

    conn.executemany(
        'INSERT INTO tokens(book_num,chapter,verse,position,text,word,lemma,pos,parsing,desc_pt,strong_num)'
        ' VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        rows
    )
    print(f'  {code}: {len(rows)} tokens')


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print('Downloading OSHB files…')
    for _, _, filename, *_ in BOOKS:
        download(OSHB_URL + filename, DATA_DIR / filename)

    strongs_path = DATA_DIR / 'strongs-hebrew-dictionary.js'
    download(STRONGS_URL, strongs_path)

    print('\nMigrating schema…')
    conn = sqlite3.connect(DB_PATH)
    migrate_schema(conn)

    import_strongs(conn, strongs_path)

    print('\nImporting Hebrew books…')
    for book_data in BOOKS:
        import_book(conn, *book_data)

    print('\nRebuilding FTS index…')
    conn.execute("INSERT INTO tokens_fts(tokens_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    print('Done.')


if __name__ == '__main__':
    main()
