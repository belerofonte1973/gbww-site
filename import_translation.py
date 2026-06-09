#!/usr/bin/env python3
"""
Download Almeida Revisada (AA) from thiagobodruk/biblia and import
verse-by-verse Portuguese translations into classics.db.
"""

import json
import sqlite3
import urllib.request
from pathlib import Path

DB_PATH  = Path(__file__).parent / 'classics.db'
DATA_DIR = Path(__file__).parent / 'data'
AA_URL   = ('https://raw.githubusercontent.com/thiagobodruk/biblia'
            '/master/json/aa.json')
AA_PATH  = DATA_DIR / 'aa.json'

# Positional mapping: JSON index → book_num in classics.db
# Positions 0-38 = OT (book_num 101-139), 39-65 = NT (book_num 1-27)
BOOK_NUM = (
    # OT
    101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
    111, 112, 113, 114, 115, 116, 117, 118, 119, 120,
    121, 122, 123, 124, 125, 126, 127, 128, 129, 130,
    131, 132, 133, 134, 135, 136, 137, 138, 139,
    # NT
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
    21, 22, 23, 24, 25, 26, 27,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS verse_translations (
    book_num INTEGER NOT NULL,
    chapter  INTEGER NOT NULL,
    verse    INTEGER NOT NULL,
    text_pt  TEXT    NOT NULL,
    source   TEXT    NOT NULL DEFAULT 'aa',
    PRIMARY KEY (book_num, chapter, verse)
);
"""


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not AA_PATH.exists():
        print('Downloading aa.json (Almeida Revisada)…')
        urllib.request.urlretrieve(AA_URL, AA_PATH)
    else:
        print('aa.json já existe, a reutilizar.')

    print('Parsing…')
    raw  = AA_PATH.read_bytes()
    data = json.loads(raw.decode('utf-8-sig'))

    if len(data) != 66:
        raise ValueError(f'Esperava 66 livros, encontrei {len(data)}')

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("DELETE FROM verse_translations WHERE source='aa'")

    rows = []
    for idx, book in enumerate(data):
        book_num = BOOK_NUM[idx]
        chapters = book.get('chapters', [])
        for ch_idx, chapter in enumerate(chapters):
            for vs_idx, text in enumerate(chapter):
                text = text.strip()
                if text:
                    rows.append((book_num, ch_idx + 1, vs_idx + 1, text, 'aa'))

    conn.executemany(
        'INSERT OR REPLACE INTO verse_translations'
        '(book_num, chapter, verse, text_pt, source) VALUES (?,?,?,?,?)',
        rows
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM verse_translations").fetchone()[0]
    conn.close()
    print(f'Importados {len(rows)} versículos ({total} total na tabela).')


if __name__ == '__main__':
    main()
