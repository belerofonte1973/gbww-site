#!/usr/bin/env python3
"""Build the GBWW SQLite database from source files."""
import re, os, sqlite3, unicodedata
from pathlib import Path

BASE      = Path('/home/rodrigo/gbww')
TXTS      = BASE / 'txts'
SYNT      = BASE / 'syntopicon_v18'
MAPA      = BASE / 'Mapa de referências do Syntopicon'
DB_PATH   = Path('/home/rodrigo/gbww_site/gbww.db')

# ── helpers ──────────────────────────────────────────────────────────────────

def slugify(text):
    text = text.strip().lower()
    text = text.replace('&', 'and')
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text

def norm(text):
    """Collapse multiple spaces/tabs to one."""
    return re.sub(r'[ \t]{2,}', ' ', text)

# ── schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS volumes (
    id INTEGER PRIMARY KEY, num INTEGER UNIQUE,
    title TEXT, short_title TEXT, filepath TEXT
);
CREATE TABLE IF NOT EXISTS passages (
    id INTEGER PRIMARY KEY, volume_id INTEGER,
    marker TEXT, page_num INTEGER, col TEXT, text TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts
    USING fts5(text, content='passages', content_rowid='id');
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE, slug TEXT UNIQUE,
    chapter_num INTEGER, intro_text TEXT, outline_text TEXT
);
CREATE TABLE IF NOT EXISTS subtopics (
    id INTEGER PRIMARY KEY, topic_id INTEGER,
    code TEXT, description TEXT, sort_order INTEGER
);
CREATE TABLE IF NOT EXISTS refs (
    id INTEGER PRIMARY KEY, topic_id INTEGER, subtopic_id INTEGER,
    volume_num INTEGER, author TEXT, work TEXT,
    location TEXT, page_from TEXT, page_to TEXT, raw_text TEXT,
    UNIQUE(topic_id, volume_num, author, work, page_from)
);
CREATE TABLE IF NOT EXISTS cross_refs (
    id INTEGER PRIMARY KEY, from_topic_id INTEGER,
    to_topic_id INTEGER, context TEXT
);
CREATE TABLE IF NOT EXISTS translations (
    id INTEGER PRIMARY KEY, passage_id INTEGER,
    language TEXT DEFAULT 'pt', text TEXT, source TEXT
);
CREATE INDEX IF NOT EXISTS idx_passages_vol   ON passages(volume_id);
CREATE INDEX IF NOT EXISTS idx_passages_marker ON passages(volume_id, marker);
CREATE INDEX IF NOT EXISTS idx_refs_topic      ON refs(topic_id);
CREATE INDEX IF NOT EXISTS idx_refs_vol        ON refs(volume_num);
"""

# ── volumes ───────────────────────────────────────────────────────────────────

def index_volumes(cur):
    print("Indexando volumes...")
    vol_pat = re.compile(r'Volume (\d+) - (.+)\.txt$')
    for f in sorted(TXTS.iterdir()):
        m = vol_pat.search(f.name)
        if not m:
            continue
        num, title = int(m.group(1)), m.group(2)
        # short_title: remove Roman numerals suffix like " I", " II"
        short = re.sub(r'\s+[IV]+$', '', title)
        cur.execute(
            "INSERT OR IGNORE INTO volumes(num,title,short_title,filepath) VALUES(?,?,?,?)",
            (num, title, short, str(f))
        )
    print(f"  {cur.rowcount or 'OK'} volumes")

# ── passages ──────────────────────────────────────────────────────────────────

def index_passages(cur, con):
    print("Indexando trechos dos Great Books (pode demorar ~10 min)...")
    total = 0
    marker_re = re.compile(r'^\[(\d+)([a-d])\]$')
    for f in sorted(TXTS.iterdir()):
        m = re.search(r'Volume (\d+)', f.name)
        if not m:
            continue
        vol_num = int(m.group(1))
        row = cur.execute("SELECT id FROM volumes WHERE num=?", (vol_num,)).fetchone()
        if not row:
            continue
        vol_id = row[0]

        text = f.read_text(encoding='utf-8', errors='replace')
        lines = text.splitlines()

        current_marker = None
        current_page = None
        current_col = None
        buf = []

        def flush():
            nonlocal total
            if current_marker and buf:
                t = '\n'.join(buf).strip()
                if t and t != '[página ilustrada]':
                    cur.execute(
                        "INSERT INTO passages(volume_id,marker,page_num,col,text) VALUES(?,?,?,?,?)",
                        (vol_id, current_marker, current_page, current_col, t)
                    )
                    total += 1

        for line in lines:
            mk = marker_re.match(line.strip())
            if mk:
                flush()
                current_marker = f"{mk.group(1)}{mk.group(2)}"
                current_page = int(mk.group(1))
                current_col = mk.group(2)
                buf = []
            else:
                if current_marker:
                    buf.append(line)

        flush()
        print(f"  Vol {vol_num:2d}: {f.name[55:75]}...")

    con.commit()
    print(f"  Total: {total} trechos indexados")
    print("  Construindo índice FTS5...")
    cur.execute("INSERT INTO passages_fts(passages_fts) VALUES('rebuild')")
    con.commit()
    print("  FTS5 pronto.")

# ── topics (syntopicon_v18) ───────────────────────────────────────────────────

def parse_topics(cur):
    print("Parseando tópicos do Syntopicon...")
    count = 0
    subtopic_re = re.compile(r'^\s{0,4}(\d+[a-z]?\.)\s+(.+)')

    for f in sorted(SYNT.glob('*.txt')):
        if f.name.startswith('#'):
            continue
        name = f.stem  # e.g. "Angels" or "Good & Evil"
        slug = slugify(name)
        text = f.read_text(encoding='utf-8', errors='replace')

        # Split sections
        outline_start = text.find('OUTLINE OF TOPICS')
        crossref_start = text.find('CROSS-REFERENCES')
        addread_start  = text.find('ADDITIONAL READINGS')

        if outline_start == -1:
            intro = text.strip()
            outline = ''
        else:
            intro   = text[:outline_start].strip()
            end_of_outline = crossref_start if crossref_start != -1 else len(text)
            outline = text[outline_start:end_of_outline].strip()

        if crossref_start != -1:
            end_of_crossref = addread_start if addread_start != -1 else len(text)
            crossref_raw = text[crossref_start:end_of_crossref].strip()
        else:
            crossref_raw = ''

        # Clean intro: remove header/section label lines
        intro_lines = intro.splitlines()
        clean_lines = []
        for line in intro_lines:
            # Skip "Chapter N:", "CHAPTER: NAME", "INTRODUCTION" header lines
            if re.match(r'^Chapter\s*[\w:.\-]*\s*$', line, re.I):
                continue
            if re.match(r'^CHAPTER\s*[:\-]?\s*\w*\s*$', line, re.I):
                continue
            if re.match(r'^INTRODUCTION\s*$', line, re.I):
                continue
            clean_lines.append(line)
        intro = '\n'.join(clean_lines).strip()

        # Extract chapter number from outline
        chap_m = re.search(r'CHAPTER\s+(\d+)', text, re.I)
        chapter_num = int(chap_m.group(1)) if chap_m else None

        cur.execute(
            "INSERT OR REPLACE INTO topics(name,slug,chapter_num,intro_text,outline_text) VALUES(?,?,?,?,?)",
            (name, slug, chapter_num, intro, outline)
        )
        topic_id = cur.lastrowid

        # Parse subtopics from outline
        order = 0
        for line in outline.splitlines():
            m = subtopic_re.match(line)
            if m:
                code = m.group(1).rstrip('.')
                desc = m.group(2).strip()
                cur.execute(
                    "INSERT INTO subtopics(topic_id,code,description,sort_order) VALUES(?,?,?,?)",
                    (topic_id, code, desc, order)
                )
                order += 1

        # Parse cross-references (extract topic names in ALL CAPS)
        if crossref_raw:
            for m in re.finditer(r'\b([A-Z]{2,}(?:\s+[A-Z&]+)*)\b', crossref_raw):
                target_name = m.group(1).title().replace(' And ', ' & ')
                if target_name.lower() != name.lower() and len(target_name) > 2:
                    cur.execute(
                        "INSERT INTO cross_refs(from_topic_id,to_topic_id,context) "
                        "SELECT ?, t.id, ? FROM topics t WHERE t.name=? LIMIT 1",
                        (topic_id, crossref_raw[:200], target_name)
                    )

        count += 1

    print(f"  {count} tópicos importados")

# ── references (Mapa files) ───────────────────────────────────────────────────

PAGE_RE  = re.compile(r'(\d+)([a-d])')

def parse_page(s):
    """Parse '310a' → ('310a', 310, 'a')"""
    m = PAGE_RE.fullmatch(s.strip())
    if m:
        return s.strip(), int(m.group(1)), m.group(2)
    return s.strip(), None, None

def parse_page_range(raw):
    """Parse '310a-328d' or '31a-b' or '452b' → (from, to)"""
    raw = raw.strip()
    # Range like 310a-328d
    m = re.match(r'(\d+[a-d])-(\d+[a-d])', raw)
    if m:
        return m.group(1), m.group(2)
    # Range like 31a-b (same page, different col)
    m = re.match(r'(\d+)([a-d])-([a-d])', raw)
    if m:
        return f"{m.group(1)}{m.group(2)}", f"{m.group(1)}{m.group(3)}"
    # Single page
    m = re.match(r'(\d+[a-d])', raw)
    if m:
        return m.group(1), m.group(1)
    return raw, raw

def parse_mapa_refs(cur):
    print("Parseando referências dos ficheiros Mapa...")

    # Build topic slug → id map
    topic_map = {row[0]: row[1] for row in cur.execute("SELECT slug, id FROM topics")}
    # Also map uppercase name → id (both plural and singular forms)
    name_map  = {}
    for row in cur.execute("SELECT name, id FROM topics"):
        n = row[0].upper()
        name_map[n] = row[1]
        # Add singular form (strip trailing S)
        if n.endswith('S') and len(n) > 3:
            name_map[n[:-1]] = row[1]
        # Add without " AND " → " & " variant
        name_map[n.replace(' & ', ' AND ')] = row[1]
        name_map[n.replace(' AND ', ' & ')] = row[1]

    def find_topic(chap_name):
        """Try several normalizations to find a topic ID for a chapter heading."""
        # Truncate at first word not in ALL_CAPS (extra text from long headings)
        clean = re.match(r'([A-Z][A-Z &]+?)(?:\s+(?:INTRODUCTION|REFERENCES|[0-9]|[a-z]).*)?$', chap_name)
        name = clean.group(1).strip().rstrip() if clean else chap_name
        # Trim trailing standalone letters (e.g., "ELEMENT S" → "ELEMENT")
        name = re.sub(r'\s+[A-Z]$', '', name).strip()
        candidates = [
            name,
            name + 'S',          # singular → plural
            name.rstrip('S'),    # plural → singular
            name.replace(' AND ', ' & '),
            name.replace(' & ', ' AND '),
        ]
        for c in candidates:
            tid = name_map.get(c)
            if tid:
                return tid
        # Try slug match
        title = name.title().replace(' And ', ' & ')
        return topic_map.get(slugify(title))

    total_refs = 0

    for mapa_file in sorted(MAPA.glob('*.txt')):
        print(f"  {mapa_file.name[:60]}...")
        raw = mapa_file.read_text(encoding='utf-8', errors='replace')
        # Normalize spaces
        raw = norm(raw)
        # Strip the running header "THE GREAT IDEAS" (merged mid-line with the
        # body during extraction) plus its adjacent page-number token, so it
        # does not leak into ref work/location/raw_text fields.
        raw = re.sub(r'\b\d{1,4}\s+THE\s+GREAT\s+IDEAS\b', ' ', raw)
        raw = re.sub(r'\bTHE\s+GREAT\s+IDEAS\s+\d{1,4}\b', ' ', raw)
        raw = re.sub(r'\bTHE\s+GREAT\s+IDEAS\b', ' ', raw)
        # Remove page markers [Xa] – they break parsing
        raw = re.sub(r'\[\d+[a-d]\]', '', raw)

        # Split by chapter headings: "Chapter N: TOPICNAME" (possibly with extra text)
        chap_split = re.split(r'(Chapter\s+\d+\s*:\s*[A-Z][A-Z &]+)', raw)

        # Merge chunks belonging to the same chapter (same chapter num)
        chapters = {}  # canonical_name → combined body
        i = 1
        while i < len(chap_split):
            heading = chap_split[i].strip()
            body    = chap_split[i+1] if i+1 < len(chap_split) else ''
            m = re.match(r'Chapter\s+\d+\s*:\s*([A-Z][A-Z &]+)', heading)
            if m:
                raw_name = m.group(1).strip()
                # On a running-header page the section keyword that follows the
                # chapter name can be swallowed into the split delimiter (e.g.
                # "JUSTICE REFERENCES"), which would file that body under a bogus
                # key and lose it. Peel the keyword back off and return it to the
                # body so the section search below still finds it.
                secm = re.search(r'\b(REFERENCES|INTRODUCTION|OUTLINE|CROSS|ADDITIONAL)\b', raw_name)
                if secm:
                    body = secm.group(1) + ' ' + body
                    raw_name = raw_name[:secm.start()].strip()
                # Normalize chapter name: take first word-run, drop trailing junk
                canonical = re.match(r'([A-Z][A-Z &]+?)(?:\s+[0-9a-z].*)?$', raw_name)
                key = canonical.group(1).strip() if canonical else raw_name
                key = re.sub(r'\s+[A-Z]$', '', key).strip()
                if key:
                    # Append body (multiple pages = multiple splits per chapter)
                    chapters[key] = chapters.get(key, '') + body
            i += 2

        for chap_name, body in chapters.items():
            # Match to topic
            topic_id = find_topic(chap_name)
            if not topic_id:
                continue

            # Locate where the references list starts. Normally the "REFERENCES"
            # heading marks it (not the one inside "CROSS-REFERENCES", hence the
            # lookbehind), but OCR drops that heading in some chapters — there
            # the list is simply the first run of "<vol> <Author>:" entries, a
            # format the introduction and outline never use.
            refm = re.search(r'(?<![-\w])REFERENCES\b', body)
            if refm:
                start = refm.start()
            else:
                em = re.search(r'(?<!\d)\d{1,2}\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?:\s', body)
                start = em.start() if em else None
            if start is None:
                continue
            ref_body = body[start:]
            # Close the references list at the earliest following section, so we
            # never absorb cross-references, additional-reading lists, or the
            # next chapter's introduction/outline (CROSS-REFERENCES is sometimes
            # missing/garbled, so we bound on several markers).
            cut = len(ref_body)
            for marker in ('CROSS-REFERENCES', 'ADDITIONAL READING',
                           'INTRODUCTION', 'OUTLINE OF TOPICS'):
                p = ref_body.find(marker, 1)
                if p != -1:
                    cut = min(cut, p)
            ref_body = ref_body[:cut]
            # Skip the standard boilerplate preamble that follows REFERENCES
            # ("To find the passages cited ... consult the Preface."); its
            # worked examples (4 Homer, 7 Plato, 53 James) and the Bible-style
            # note would otherwise parse as fake references.
            pref = re.search(r'consult\s+the\s+Pref\w*\s*\.?', ref_body, re.I)
            if pref:
                ref_body = ref_body[pref.end():]

            # Normalize the ref body
            ref_body = re.sub(r'\s+', ' ', ref_body)

            # Extract reference entries: "N Author: ..."
            # Split on pattern that starts a new ref entry
            entry_pat = re.compile(r'(?<!\d)(\d{1,2})\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?):\s+')
            parts = entry_pat.split(ref_body)

            # parts = [pre, vol, author, text, vol, author, text, ...]
            j = 1
            while j + 2 < len(parts):
                vol_num = int(parts[j])
                author  = parts[j+1].strip()
                entry   = parts[j+2].strip() if j+2 < len(parts) else ''
                # Stop at next entry start
                j += 3

                if vol_num < 1 or vol_num > 54:
                    continue

                # Defensive: never let one entry run into prose or another
                # section if a boundary marker slipped through above.
                entry = re.split(
                    r'\b(?:INTRODUCTION|OUTLINE OF TOPICS|CROSS-REFERENCES|ADDITIONAL READING)\b',
                    entry)[0]
                # Split works by " / "
                works_raw = re.split(r'\s*/\s*', entry)
                for work_raw in works_raw:
                    work_raw = work_raw.strip()
                    if not work_raw:
                        continue
                    # Extract work title: everything before the first page reference
                    # Page refs look like digits followed by a-d
                    page_pos = re.search(r'\b\d+[a-d]\b', work_raw)
                    if page_pos:
                        work_title_raw = work_raw[:page_pos.start()].strip().rstrip(',').strip()
                        pages_raw = work_raw[page_pos.start():]
                    else:
                        work_title_raw = work_raw
                        pages_raw = ''

                    # Clean work title: separate location (bk, ch, sect, part) from title
                    loc_m = re.search(r',?\s*(bk|ch|sect|part|q|tr|vol)\s', work_title_raw, re.I)
                    if loc_m:
                        work_title = work_title_raw[:loc_m.start()].strip().rstrip(',')
                        location   = work_title_raw[loc_m.start():].strip().lstrip(',').strip()
                    else:
                        work_title = work_title_raw
                        location   = ''

                    # A real work title is short; a 100+ char "title" means the
                    # page-ref search found nothing early, i.e. this is prose
                    # that slipped through — drop it rather than store a paragraph.
                    if len(work_title) > 100:
                        continue

                    # Get first page range
                    first_range = re.search(r'(\d+[a-d])(?:-(\d+)?([a-d]))?', pages_raw)
                    if first_range:
                        p_from = first_range.group(1)
                        if first_range.group(2) and first_range.group(3):
                            p_to = first_range.group(2) + first_range.group(3)
                        elif first_range.group(3):
                            p_to = re.match(r'\d+', p_from).group() + first_range.group(3)
                        else:
                            p_to = p_from
                    else:
                        p_from = p_to = ''

                    cur.execute(
                        "INSERT OR IGNORE INTO refs(topic_id,volume_num,author,work,location,page_from,page_to,raw_text) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (topic_id, vol_num, author, work_title, location,
                         p_from, p_to, work_raw[:300])
                    )
                    total_refs += 1

    print(f"  Total: {total_refs} referências indexadas")

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(SCHEMA)
    con.commit()

    index_volumes(cur); con.commit()
    index_passages(cur, con)
    parse_topics(cur);  con.commit()
    parse_mapa_refs(cur); con.commit()
    con.close()
    print(f"\nBase de dados criada: {DB_PATH} ({DB_PATH.stat().st_size // 1024 // 1024} MB)")

if __name__ == '__main__':
    main()
