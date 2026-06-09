#!/usr/bin/env python3
"""
Import ancient Egyptian literary texts into classics.db.

Sources:
  Wikisource (public domain) — English translations by Budge, Barton, etc.

Texts imported:
  egy.hymn_aten       — Great Hymn to Aten (Akhenaten, c. 1350 BCE)
  egy.hymn_nile       — Hymn to the Nile (c. 2100 BCE)
  egy.love_poems      — Ancient Egyptian Love Poems (c. 1300 BCE)
  egy.ani_osiris      — Papyrus of Ani: Hymn to Osiris (c. 1240 BCE)
  egy.ani_125         — Papyrus of Ani: Chapter 125 — Negative Confession
  egy.ani_17          — Papyrus of Ani: Chapter 17 — Awakening of Osiris
  egy.misanthrope     — Dialogue of a Misanthrope with His Own Soul
  egy.megiddo         — An Account of the Battle of Megiddo (Thutmose III)
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

DB_PATH   = Path(__file__).parent / 'classics.db'
CACHE     = Path(__file__).parent / 'data' / 'egy_cache'
WS_API    = 'https://en.wikisource.org/w/api.php'


# ── Texts manifest ─────────────────────────────────────────────────────────────

TEXTS = [
    {
        'id':       'egy.hymn_aten',
        'title_en': 'Great Hymn to Aten',
        'title_pt': 'Grande Hino ao Aten',
        'corpus':   'wikisource',
        'ws_page':  'Great_Hymn_to_Aten',
        'parser':   'numbered',
        'note':     'Inscrito no túmulo de Ay, Amarna, c. 1346 a.C. Atribuído ao faraó Akhenaton. Tradução de E.A.W. Budge (1923).',
    },
    {
        'id':       'egy.hymn_nile',
        'title_en': 'Hymn to the Nile',
        'title_pt': 'Hino ao Nilo',
        'corpus':   'wikisource',
        'ws_page':  'Hymn_to_the_Nile',
        'parser':   'paragraphs',
        'note':     'Composto c. 2100 a.C. Celebra a cheia anual do Nilo. Tradução de 1907.',
    },
    {
        'id':       'egy.love_poems',
        'title_en': 'Ancient Egyptian Love Poems',
        'title_pt': 'Poemas de Amor do Antigo Egito',
        'corpus':   'wikisource',
        'ws_page':  'Ancient_Egyptian_Love_Poems',
        'parser':   'poem_sections',
        'note':     'Poemas líricos do Novo Reino (c. 1300 a.C.), Papiro Chester Beatty I e Papiro de Turino. Tradução de George A. Barton (1920).',
    },
    {
        'id':       'egy.misanthrope',
        'title_en': 'Dialogue of a Misanthrope with His Own Soul',
        'title_pt': 'Diálogo de um Misantropo com a Sua Própria Alma',
        'corpus':   'wikisource',
        'ws_page':  'The_Dialogue_of_a_Misanthrope_with_His_Own_Soul',
        'parser':   'poem_stanzas',
        'note':     'Texto do Médio Reino (c. 2000 a.C.). Um dos mais notáveis poemas filosóficos do Egito antigo.',
    },
    {
        'id':       'egy.ani_osiris',
        'title_en': 'Papyrus of Ani: Hymn to Osiris',
        'title_pt': 'Papiro de Ani: Hino a Osíris',
        'corpus':   'papyrus_ani',
        'ws_page':  'The_Papyrus_of_Ani_(1913)',
        'parser':   'ani_section',
        'section':  'HYMN TO OSIRIS',
        'section_end': 'A HYMN OF PRAISE TO RA',
        'note':     'Papiro de Ani, Livro dos Mortos egípcio, c. 1240 a.C. Tradução de E.A.W. Budge (1913).',
    },
    {
        'id':       'egy.ani_chapters',
        'title_en': 'Book of the Dead: Chapters of Coming Forth by Day',
        'title_pt': 'Livro dos Mortos: Capítulos de Sair à Luz do Dia',
        'corpus':   'papyrus_ani',
        'ws_page':  'The_Papyrus_of_Ani_(1913)',
        'parser':   'ani_section',
        'section':  'THE CHAPTERS OF COMING FORTH BY DAY',
        'section_end': 'TEXTS RELATING TO THE WEIGHING',
        'note':     'Papiro de Ani, c. 1240 a.C. Fórmulas mágicas para a viagem ao além. Tradução de E.A.W. Budge (1913).',
    },
    {
        'id':       'egy.ani_125',
        'title_en': 'Book of the Dead: The Negative Confession (Hall of Maʿat)',
        'title_pt': 'Livro dos Mortos: A Confissão Negativa (Sala de Maet)',
        'corpus':   'papyrus_ani',
        'ws_page':  'The_Papyrus_of_Ani_(1913)',
        'parser':   'negative_confession',
        'section':  'THE NEGATIVE CONFESSION',
        'section_end': 'THE CHAPTER OF THE DEIFICATION',
        'note':     'O coração de Ani é pesado contra a pena de Maet. Lista de 42 declarações de inocência perante os 42 juízes divinos. Papiro de Ani, c. 1240 a.C.',
    },
    {
        'id':       'egy.megiddo',
        'title_en': 'Annals of Thutmose III: Battle of Megiddo',
        'title_pt': 'Anais de Tutmés III: Batalha de Megido',
        'corpus':   'wikisource',
        'ws_page':  'An_Account_of_the_Battle_of_Megiddo',
        'parser':   'paragraphs',
        'note':     'Inscrição no templo de Karnak, c. 1457 a.C. A primeira batalha documentada da história. Tradução de James Henry Breasted (1906).',
    },
]


# ── schema extension ──────────────────────────────────────────────────────────

SCHEMA_EGY = """
ALTER TABLE lit_texts ADD COLUMN note TEXT;
"""


# ── downloader ────────────────────────────────────────────────────────────────

def fetch_wikisource_html(ws_page: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / f'{ws_page}.html'
    if cache_file.exists():
        return cache_file.read_text(encoding='utf-8')

    url = (f'{WS_API}?action=parse&page={ws_page}'
           f'&prop=text&format=json&disablelimitreport=1')
    req = urllib.request.Request(url, headers={'User-Agent': 'Classics-Reader/1.0'})
    try:
        import json as _json
        resp = urllib.request.urlopen(req, timeout=20)
        data = _json.loads(resp.read())
        html = data['parse']['text']['*']
    except Exception as ex:
        print(f'    ↯ download falhou: {ex}')
        return ''
    cache_file.write_text(html, encoding='utf-8')
    time.sleep(0.5)
    return html


def clean_soup(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, 'html.parser')
    for el in soup.find_all(['style', 'script']):
        el.decompose()
    for cls in ['ws-header', 'ws-noexport', 'catlinks', 'printfooter',
                'mw-indicators', 'toc', 'mw-editsection', 'reflist',
                'references', 'mw-references-wrap']:
        for el in soup.find_all(class_=cls):
            el.decompose()
    for el in soup.find_all('table'):
        el.decompose()
    return soup


def soup_to_text(element) -> str:
    txt = element.get_text(' ')
    txt = re.sub(r'\[\d+\]', '', txt)           # remove footnote refs [1]
    txt = re.sub(r'\s+', ' ', txt).strip()
    return txt


# ── parsers ───────────────────────────────────────────────────────────────────

def parse_numbered(html: str) -> list[dict]:
    """Texts with <sup>N</sup> section numbers — e.g. Great Hymn to Aten."""
    soup = clean_soup(html)
    body = soup.find(class_='mw-parser-output')
    if not body:
        return []

    # Build raw text with section markers
    raw = body.get_text('\n')
    raw = re.sub(r'\[\d+\]', '', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw)

    # Look for lines that are just a single number (section markers)
    sections = []
    current_num = None
    current_lines = []

    for line in raw.split('\n'):
        line = line.strip()
        if not line:
            continue
        if re.match(r'^\d+$', line) and int(line) <= 50:
            if current_num is not None and current_lines:
                text_en = ' '.join(current_lines).strip()
                if len(text_en) > 20:
                    sections.append({'num': current_num, 'text_en': text_en})
            current_num = int(line)
            current_lines = []
        elif current_num is not None:
            # Skip header/nav text before section 1
            current_lines.append(line)

    if current_num is not None and current_lines:
        text_en = ' '.join(current_lines).strip()
        if len(text_en) > 20:
            sections.append({'num': current_num, 'text_en': text_en})

    return sections


def parse_paragraphs(html: str) -> list[dict]:
    """Generic paragraph-based texts — split on blank lines."""
    soup = clean_soup(html)
    body = soup.find(class_='mw-parser-output')
    if not body:
        return []

    # Get paragraphs from <p> tags
    raw_paras = []
    for el in body.find_all(['p', 'div']):
        txt = soup_to_text(el)
        if len(txt) > 40:
            raw_paras.append(txt)

    # Merge very short paragraphs with the previous
    merged = []
    for p in raw_paras:
        if merged and len(p) < 80 and not re.match(r'^[A-Z\s]{3,}$', p):
            merged[-1] = merged[-1] + ' ' + p
        else:
            merged.append(p)

    return [{'num': i + 1, 'text_en': p} for i, p in enumerate(merged) if len(p) > 40]


def parse_poem_sections(html: str) -> list[dict]:
    """Texts with Roman numeral section headers like '''I.''' or '''II.'''"""
    soup = clean_soup(html)
    body = soup.find(class_='mw-parser-output')
    if not body:
        return []

    raw = body.get_text('\n')
    raw = re.sub(r'\[\d+\]', '', raw)

    # Split on Roman numeral headers
    roman_re = re.compile(r'^(I{1,3}|IV|V|VI{1,3}|IX|X{1,2}|XIV|XV|XX)\.?\s*$', re.M)
    parts = roman_re.split(raw)

    sections = []
    roman_nums = roman_re.findall(raw)
    # parts[0] = preamble, parts[1]=roman, parts[2]=content, etc.
    for i in range(0, len(parts) - 1, 1):
        if roman_re.match(parts[i].strip()):
            continue
        # Find matching roman heading
        idx = len([p for p in parts[:i] if roman_re.match(p.strip())])
        text = re.sub(r'\s+', ' ', parts[i]).strip()
        if len(text) > 30:
            sections.append({'num': len(sections) + 1, 'text_en': text})

    # Fallback: if no sections found, try simple paragraph split
    if not sections:
        return parse_paragraphs(html)
    return sections


def parse_poem_stanzas(html: str) -> list[dict]:
    """Short poem with blank-line-separated stanzas."""
    soup = clean_soup(html)
    raw = soup.get_text('\n')
    raw = re.sub(r'\[\d+\]', '', raw)
    raw = re.sub(r'\n{3,}', '\n\n', raw).strip()

    sections = []
    for block in raw.split('\n\n'):
        block = block.strip()
        if len(block) > 20 and not re.match(r'^(Death is before me|Category|Portal)', block) or \
                block.startswith('Death is before me'):
            sections.append({'num': len(sections) + 1, 'text_en': re.sub(r'\s+', ' ', block)})

    # If parsing fails, just return whole text as one section
    if not sections:
        full = re.sub(r'\s+', ' ', raw).strip()
        if full:
            sections = [{'num': 1, 'text_en': full}]
    return sections


def parse_negative_confession(html: str) -> list[dict]:
    """Split the Negative Confession into individual declarations."""
    soup = clean_soup(html)
    raw = soup.get_text('\n')
    raw = re.sub(r'\[\d+\]', '', raw)

    start = raw.find('THE NEGATIVE CONFESSION')
    end   = raw.find('THE CHAPTER OF THE DEIFICATION', start)
    if end == -1:
        end = start + 20000
    block = raw[start:end]

    # Each declaration starts with "Hail,"
    parts = re.split(r'(?=Hail,\s+\w)', block)
    sections = []
    for part in parts:
        part = re.sub(r'\s+', ' ', part).strip()
        if part.startswith('Hail,') and len(part) > 30:
            sections.append({'num': len(sections) + 1, 'text_en': part})
        elif not part.startswith('Hail,') and len(part) > 40 and len(sections) == 0:
            # Preamble / introduction before first Hail
            sections.append({'num': len(sections) + 1, 'text_en': part})
    return sections


def parse_ani_section(html: str, section_start: str, section_end: str) -> list[dict]:
    """Extract a specific chapter from the Papyrus of Ani."""
    soup = clean_soup(html)
    raw = soup.get_text('\n')
    raw = re.sub(r'\[\d+\]', '', raw)

    start_idx = raw.find(section_start)
    if start_idx == -1:
        # Try case-insensitive
        lower = raw.lower()
        start_idx = lower.find(section_start.lower())

    if start_idx == -1:
        print(f'    ↯ secção "{section_start}" não encontrada')
        return []

    end_idx = raw.find(section_end, start_idx + len(section_start))
    if end_idx == -1:
        end_idx = start_idx + 8000   # max 8000 chars per section

    section_text = raw[start_idx:end_idx].strip()

    # Remove the section header line itself but preserve blank lines
    header_stripped = section_start.strip()
    filtered = []
    for line in section_text.split('\n'):
        if line.strip() == header_stripped:
            continue
        filtered.append(line)
    section_text = '\n'.join(filtered)

    # Split into paragraphs on blank lines / paragraph breaks
    raw_blocks = re.split(r'\n{2,}', section_text)
    sections = []
    for block in raw_blocks:
        block = re.sub(r'\s+', ' ', block).strip()
        if len(block) > 40:
            sections.append({'num': len(sections) + 1, 'text_en': block})

    # If too many small blocks, merge pairs
    if len(sections) > 40:
        merged = []
        buf = ''
        for s in sections:
            buf = (buf + ' ' + s['text_en']).strip()
            if len(buf) > 200:
                merged.append({'num': len(merged) + 1, 'text_en': buf})
                buf = ''
        if buf:
            merged.append({'num': len(merged) + 1, 'text_en': buf})
        sections = merged

    return sections


# ── dispatcher ────────────────────────────────────────────────────────────────

def parse_text(text_def: dict, html: str) -> list[dict]:
    parser = text_def['parser']
    if parser == 'numbered':
        return parse_numbered(html)
    elif parser == 'paragraphs':
        return parse_paragraphs(html)
    elif parser == 'poem_sections':
        return parse_poem_sections(html)
    elif parser == 'poem_stanzas':
        return parse_poem_stanzas(html)
    elif parser == 'negative_confession':
        return parse_negative_confession(html)
    elif parser == 'ani_section':
        return parse_ani_section(html, text_def['section'], text_def['section_end'])
    return []


# ── import ────────────────────────────────────────────────────────────────────

def import_text(conn: sqlite3.Connection, text_def: dict) -> bool:
    tid      = text_def['id']
    title_en = text_def['title_en']
    title_pt = text_def['title_pt']
    corpus   = text_def['corpus']
    note     = text_def.get('note', '')
    ws_page  = text_def['ws_page']

    print(f'  Importing {tid}: {title_en}…')

    html     = fetch_wikisource_html(ws_page)
    if not html:
        print('    ✗ sem HTML — saltar')
        return False

    sections = parse_text(text_def, html)
    if not sections:
        print('    ✗ sem secções — saltar')
        return False

    # Upsert text record
    conn.execute(
        'INSERT OR REPLACE INTO lit_texts(id,title_en,title_pt,corpus,lang,note)'
        ' VALUES(?,?,?,?,?,?)',
        (tid, title_en, title_pt, corpus, 'egy', note)
    )
    conn.execute('DELETE FROM lit_lines      WHERE text_id=?', (tid,))
    conn.execute('DELETE FROM lit_paragraphs WHERE text_id=?', (tid,))

    for sec in sections:
        conn.execute(
            'INSERT INTO lit_paragraphs(text_id,line_from,line_to,text_en)'
            ' VALUES(?,?,?,?)',
            (tid, sec['num'], sec['num'], sec['text_en'])
        )

    print(f'    ✓ {len(sections)} secções importadas')
    return True


# ── schema migration ──────────────────────────────────────────────────────────

def apply_schema(conn: sqlite3.Connection):
    # Add note column if not present
    cols = [r[1] for r in conn.execute('PRAGMA table_info(lit_texts)').fetchall()]
    if 'note' not in cols:
        conn.execute('ALTER TABLE lit_texts ADD COLUMN note TEXT')
        print('  Added note column to lit_texts.')


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

    print(f'\nRebuildando FTS…')
    try:
        conn.execute("INSERT INTO lit_fts(lit_fts) VALUES('rebuild')")
    except Exception:
        pass
    conn.commit()
    conn.close()
    print(f'Concluído: {ok} textos importados, {fail} falhados.')


if __name__ == '__main__':
    main()
