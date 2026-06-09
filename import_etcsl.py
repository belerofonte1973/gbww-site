#!/usr/bin/env python3
"""
Download and import ETCSL Sumerian literary texts into classics.db.

Source: Electronic Text Corpus of Sumerian Literature (Oxford/ETCSL)
        https://etcsl.orinst.ox.ac.uk/

Each text:
  - Transliteration: https://etcsl.orinst.ox.ac.uk/cgi-bin/etcsl.cgi?text=c.{id}&charenc=gclm
  - Translation:     https://etcsl.orinst.ox.ac.uk/cgi-bin/etcsl.cgi?text=t.{id}&charenc=gclm
"""

import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("beautifulsoup4 não instalado — pip install beautifulsoup4")

DB_PATH  = Path(__file__).parent / 'classics.db'
CACHE    = Path(__file__).parent / 'data' / 'etcsl_cache'
BASE_URL = 'https://etcsl.orinst.ox.ac.uk/cgi-bin/etcsl.cgi'

# ── curated list of key texts ─────────────────────────────────────────────────
# Format: (etcsl_id, title_pt, title_en)
TEXTS = [
    # Cosmológico / Criação
    ('1.1.3',   'Enki e a Ordem do Mundo',                    'Enki and the world order'),
    ('1.1.4',   'Enki e Ninhursaja',                          'Enki and Ninhursaja'),
    ('1.1.2',   'Inana e Enki',                               'Inana and Enki'),
    ('1.2.1',   'Enlil e Ninlil',                             'Enlil and Ninlil'),
    ('1.2.2',   'Enlil e Sud',                                'Enlil and Sud'),
    # Inana / Dumuzi
    ('1.1.1',   'A Descida de Inana ao Mundo Inferior',       "Inana's descent to the nether world"),
    ('1.3.3',   'Inana e Sukaletuda',                         'Inana and Sukaletuda'),
    ('1.3.2',   'Inana e Bilulu',                             'Inana and Bilulu'),
    ('1.3.1',   'O Casamento de Martu',                       'The marriage of Martu'),
    ('1.4.1',   "A Viagem de Nanna-Suen a Nippur",            "Nanna-Suen's journey to Nippur"),
    ('1.5.1',   'O Sonho de Dumuzi',                          "Dumuzid's dream"),
    # Ninurta
    ('1.6.1',   'As Façanhas de Ninurta (Lugal-e)',           "Ninurta's exploits"),
    ('1.6.2',   'Ninurta e a Tartaruga',                      'Ninurta and the turtle'),
    # Gilgamesh sumérico
    ('1.7.1',   'A História do Dilúvio (Ziusudra)',           'The flood story'),
    ('1.7.4',   'Gilgames e Huwawa (A)',                      'Gilgamesh and Huwawa (version A)'),
    ('1.7.5',   'Gilgames e Huwawa (B)',                      'Gilgamesh and Huwawa (version B)'),
    ('1.7.6',   'Gilgames e o Touro do Céu',                  'Gilgamesh and the bull of heaven'),
    ('1.7.7',   'Gilgames, Enkidu e o Mundo Inferior',        'Gilgamesh, Enkidu and the netherworld'),
    ('1.8.1.5', 'A Morte de Gilgames',                        'The death of Gilgamesh'),
    # Heróis de Uruk
    ('1.8.1.1', 'Lugalbanda na Caverna da Montanha',          'Lugalbanda in the mountain cave'),
    ('1.8.1.2', 'Lugalbanda e o Pássaro Anzud',               'Lugalbanda and the Anzud bird'),
    ('1.8.2.1', 'Enmerkar e o Senhor de Aratta',              'Enmerkar and the lord of Aratta'),
    ('1.8.2.2', 'Enmerkar e En-suhgir-ana',                   'Enmerkar and En-suhgir-ana'),
    # Lamentos
    ('2.2.2',   'O Lamento por Sumer e Urim',                 'The lament for Sumer and Urim'),
    ('2.2.3',   'O Lamento por Nippur',                       'The lament for Nippur'),
    ('2.2.4',   'O Lamento por Uruk',                         'The lament for Uruk'),
    ('2.2.5',   'O Lamento por Eridu',                        'The lament for Eridu'),
    # Hinos
    ('4.07.2',  'Hino a Ninkasi (Hino da Cerveja)',           'Hymn to Ninkasi'),
    ('4.08.01', 'Hino a Inana (Iddin-Dagan A)',               'Hymn to Inana (Iddin-Dagan A)'),
    ('4.13.01', 'Hino a Utu',                                 'Hymn to Utu'),
    # Literatura sapiencial / debate
    ('5.3.1',   'As Instruções do Agricultor',                "The farmer's instructions"),
    ('5.4.2',   'O Debate entre o Inverno e o Verão',         'The debate between Winter and Summer'),
    ('5.4.1',   'O Debate entre a Enxada e o Arado',         'The debate between the hoe and the plough'),
    ('5.5.4',   'O Debate entre Madeira e Cana',              'The debate between the tree and the reed'),
    # Textos escolares
    ('5.1.3',   'A Escola de Nippur (Edubba A)',               'Edubba A'),
    ('5.1.1',   'Um Dia na Escola (Eduba)',                    'Schooldays'),
]


# ── schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS lit_texts (
    id       TEXT PRIMARY KEY,
    title_en TEXT NOT NULL,
    title_pt TEXT,
    corpus   TEXT NOT NULL DEFAULT 'etcsl',
    lang     TEXT NOT NULL DEFAULT 'sux'
);

CREATE TABLE IF NOT EXISTS lit_lines (
    id          INTEGER PRIMARY KEY,
    text_id     TEXT NOT NULL,
    line_num    INTEGER NOT NULL,
    translit    TEXT NOT NULL,
    words_json  TEXT,
    para_id     INTEGER,
    UNIQUE(text_id, line_num)
);

CREATE TABLE IF NOT EXISTS lit_paragraphs (
    id        INTEGER PRIMARY KEY,
    text_id   TEXT NOT NULL,
    line_from INTEGER NOT NULL,
    line_to   INTEGER NOT NULL,
    text_en   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lit_lines_text  ON lit_lines(text_id);
CREATE INDEX IF NOT EXISTS idx_lit_para_text   ON lit_paragraphs(text_id);

CREATE VIRTUAL TABLE IF NOT EXISTS lit_fts USING fts5(
    translit,
    content='lit_lines', content_rowid='id'
);
"""


# ── downloader ────────────────────────────────────────────────────────────────

def fetch_html(etcsl_id: str, mode: str) -> str:
    """mode: 'c' = transliteration, 't' = translation."""
    cache_path = CACHE / f'{mode}.{etcsl_id}.html'
    if cache_path.exists():
        return cache_path.read_text(encoding='utf-8', errors='replace')
    url = f'{BASE_URL}?text={mode}.{etcsl_id}&charenc=gclm'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        html = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
    except Exception as ex:
        print(f'    ↯ download falhou: {ex}')
        return ''
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(html, encoding='utf-8')
    time.sleep(0.4)   # polite delay
    return html


# ── transliteration parser ───────────────────────────────────────────────────

_TOOLTIP_RE = re.compile(r"doTooltip\(event,\s*'([^']+)'\)", re.S)
_GLOSS_RE   = re.compile(r'^(.+?)\s+\((\w+[-/\w]*)\)\s+(.+)$')
_SUBNUM_RE  = re.compile(r'<sub>(\d+)</sub>', re.I)
_SUPNUM_RE  = re.compile(r'<sup>(\d+)</sup>', re.I)
_HTML_RE    = re.compile(r'<[^>]+>')


def clean_translit(raw_html: str) -> str:
    """Remove HTML tags, preserve subscript numbers as Unicode subscripts."""
    s = _SUBNUM_RE.sub(lambda m: '₀₁₂₃₄₅₆₇₈₉'[int(m.group(1))]
                       if int(m.group(1)) < 10 else m.group(1), raw_html)
    s = _SUPNUM_RE.sub(r'\1', s)
    s = _HTML_RE.sub('', s)
    return re.sub(r'\s+', ' ', s).strip()


def parse_words(td) -> list[dict]:
    words = []
    for span in td.find_all('span', onmouseover=True):
        form_raw = str(span)
        form_txt = clean_translit(str(span.decode_contents()))
        if not form_txt or form_txt.startswith('('):
            continue
        m = _TOOLTIP_RE.search(span.get('onmouseover', ''))
        if not m:
            continue
        gloss_raw = m.group(1)
        gm = _GLOSS_RE.match(gloss_raw)
        if gm:
            lemma, pos, gloss = gm.groups()
            # Clean subscripts in lemma too
            lemma = re.sub(r'<sub>(\d+)</sub>', lambda x: '₀₁₂₃₄₅₆₇₈₉'[int(x.group(1))]
                           if int(x.group(1)) < 10 else x.group(1), lemma)
            lemma = _HTML_RE.sub('', lemma)
        else:
            lemma, pos, gloss = gloss_raw, '', ''
        words.append({'form': form_txt, 'lemma': lemma, 'pos': pos, 'gloss': gloss})
    return words


def parse_transliteration(html: str) -> dict[int, dict]:
    """Return {line_num: {translit, words}}."""
    if not html or 'transliteration' not in html:
        return {}
    soup = BeautifulSoup(html, 'html.parser')
    result = {}
    for row in soup.find_all('tr'):
        tds = row.find_all('td')
        if len(tds) < 2:
            continue
        num_a = tds[0].find('a')
        if not num_a:
            continue
        try:
            line_num = int(num_a.get_text().strip().rstrip('.'))
        except ValueError:
            continue
        words   = parse_words(tds[1])
        translit = clean_translit(str(tds[1].decode_contents()))
        # Remove note text in parentheses at end
        translit = re.sub(r'\s*\(Cited in[^)]*\)', '', translit)
        translit = re.sub(r'\s*\([^)]*\)\s*$', '', translit).strip()
        result[line_num] = {'translit': translit, 'words': words}
    return result


# ── translation parser ────────────────────────────────────────────────────────

_LINEREF_RE = re.compile(r'^(\d+)(?:-(\d+))?\.?$')


def parse_translation(html: str) -> list[dict]:
    """Return [{line_from, line_to, text_en}]."""
    if not html or '<p>' not in html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    blocks = []
    for p in soup.find_all('p'):
        a = p.find('a')
        if not a:
            continue
        ref_text = a.get_text().strip().rstrip('.')
        m = _LINEREF_RE.match(ref_text)
        if not m:
            continue
        line_from = int(m.group(1))
        line_to   = int(m.group(2)) if m.group(2) else line_from
        # Full paragraph text, clean up
        text = p.get_text(separator=' ').strip()
        # Remove leading "N-M." reference
        text = re.sub(r'^\d+[-–]\d+\.\s*', '', text)
        text = re.sub(r'^\d+\.\s*', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            blocks.append({'line_from': line_from, 'line_to': line_to, 'text_en': text})
    return blocks


# ── import one text ───────────────────────────────────────────────────────────

def import_text(conn, etcsl_id: str, title_en: str, title_pt: str) -> bool:
    print(f'  Importing {etcsl_id}: {title_en}…')

    translit_html = fetch_html(etcsl_id, 'c')
    trans_html    = fetch_html(etcsl_id, 't')

    lines_data = parse_transliteration(translit_html)
    para_data  = parse_translation(trans_html)

    if not lines_data and not para_data:
        print(f'    ✗ sem dados — saltar')
        return False

    conn.execute('INSERT OR REPLACE INTO lit_texts(id,title_en,title_pt,corpus,lang) VALUES(?,?,?,?,?)',
                 (etcsl_id, title_en, title_pt, 'etcsl', 'sux'))
    conn.execute('DELETE FROM lit_lines      WHERE text_id=?', (etcsl_id,))
    conn.execute('DELETE FROM lit_paragraphs WHERE text_id=?', (etcsl_id,))

    # Insert paragraphs first, collect id by line range
    para_rows = []
    for p in para_data:
        conn.execute(
            'INSERT INTO lit_paragraphs(text_id,line_from,line_to,text_en) VALUES(?,?,?,?)',
            (etcsl_id, p['line_from'], p['line_to'], p['text_en'])
        )
        pid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        para_rows.append((p['line_from'], p['line_to'], pid))

    def find_para(line_num: int) -> int | None:
        for lf, lt, pid in para_rows:
            if lf <= line_num <= lt:
                return pid
        return None

    # Insert lines
    for line_num in sorted(lines_data):
        d     = lines_data[line_num]
        pid   = find_para(line_num)
        conn.execute(
            'INSERT OR REPLACE INTO lit_lines(text_id,line_num,translit,words_json,para_id)'
            ' VALUES(?,?,?,?,?)',
            (etcsl_id, line_num, d['translit'],
             json.dumps(d['words'], ensure_ascii=False) if d['words'] else None,
             pid)
        )

    print(f'    ✓ {len(lines_data)} linhas, {len(para_data)} parágrafos')
    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    ok = fail = 0
    for etcsl_id, title_pt, title_en in TEXTS:
        if import_text(conn, etcsl_id, title_en, title_pt):
            ok += 1
        else:
            fail += 1
        conn.commit()

    print('\nRebuilding FTS…')
    conn.execute("INSERT INTO lit_fts(lit_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()
    print(f'Concluído: {ok} textos importados, {fail} falhados.')


if __name__ == '__main__':
    main()
