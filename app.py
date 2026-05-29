#!/usr/bin/env python3
"""GBWW Web Application — Flask"""
import re, sqlite3
from pathlib import Path
from flask import Flask, render_template, request, g, abort, jsonify

app = Flask(__name__)
DB_PATH = Path(__file__).parent / 'gbww.db'

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()

def slugify(text):
    import unicodedata
    text = text.strip().lower().replace('&', 'and')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')

# ── helpers ───────────────────────────────────────────────────────────────────

def get_all_topics():
    db = get_db()
    return db.execute("SELECT name, slug FROM topics ORDER BY name").fetchall()

def passages_for_ref(db, vol_num, page_from, page_to):
    """Return passages covering a page range within a volume."""
    if not page_from:
        return []
    # Parse start
    m_from = re.match(r'(\d+)([a-d])', page_from)
    if not m_from:
        return []
    pn_from, col_from = int(m_from.group(1)), m_from.group(2)

    if page_to and page_to != page_from:
        m_to = re.match(r'(\d+)([a-d])', page_to)
        if m_to:
            pn_to, col_to = int(m_to.group(1)), m_to.group(2)
        else:
            pn_to, col_to = pn_from, col_from
    else:
        pn_to, col_to = pn_from, col_from

    vol = db.execute("SELECT id FROM volumes WHERE num=?", (vol_num,)).fetchone()
    if not vol:
        return []

    rows = db.execute("""
        SELECT p.id, p.marker, p.page_num, p.col, p.text
        FROM passages p
        WHERE p.volume_id=?
          AND (p.page_num > ? OR (p.page_num = ? AND p.col >= ?))
          AND (p.page_num < ? OR (p.page_num = ? AND p.col <= ?))
        ORDER BY p.page_num, p.col
        LIMIT 20
    """, (vol['id'], pn_from, pn_from, col_from, pn_to, pn_to, col_to)).fetchall()
    return rows

# ── routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    db = get_db()
    topics = db.execute(
        "SELECT name, slug, intro_text FROM topics ORDER BY name"
    ).fetchall()
    # Group by first letter
    groups = {}
    for t in topics:
        letter = t['name'][0].upper()
        groups.setdefault(letter, []).append(t)
    return render_template('index.html', groups=groups, all_topics=get_all_topics())

def _sub_depth(code):
    """Indentation level of a subtopic code: 1 → 0, 1a → 1, 1a(2) → 2."""
    if re.match(r'^\d+$', code or ''):
        return 0
    if re.match(r'^\d+[a-z]$', code or ''):
        return 1
    return 2

@app.route('/topic/<slug>')
def topic(slug):
    db = get_db()
    t = db.execute("SELECT * FROM topics WHERE slug=?", (slug,)).fetchone()
    if not t:
        abort(404)

    # Subtopics (outline order)
    subtopics = db.execute(
        "SELECT * FROM subtopics WHERE topic_id=? ORDER BY sort_order", (t['id'],)
    ).fetchall()

    # References, attributed to the outline subtopic they sit under (as in the
    # printed Syntopicon). Ordered by volume within each subtopic.
    refs = db.execute("""
        SELECT r.*, v.short_title as vol_title
        FROM refs r
        LEFT JOIN volumes v ON v.num = r.volume_num
        WHERE r.topic_id=?
        ORDER BY r.volume_num, r.author, r.work
    """, (t['id'],)).fetchall()

    refs_by_sub = {}
    for r in refs:
        refs_by_sub.setdefault(r['subtopic_id'], []).append(r)

    # Interleave outline + references in reading order.
    outline = [
        {'code': st['code'], 'description': st['description'],
         'depth': _sub_depth(st['code']), 'refs': refs_by_sub.get(st['id'], [])}
        for st in subtopics
    ]
    unassigned = refs_by_sub.get(None, [])

    # Cross-references
    xrefs = db.execute("""
        SELECT t.name, t.slug FROM cross_refs cr
        JOIN topics t ON t.id = cr.to_topic_id
        WHERE cr.from_topic_id=?
        GROUP BY t.id ORDER BY t.name
    """, (t['id'],)).fetchall()

    return render_template('topic.html',
        topic=t, outline=outline, unassigned=unassigned,
        ref_count=len(refs), xrefs=xrefs,
        all_topics=get_all_topics()
    )

@app.route('/passage/<int:vol_num>/<marker>')
def passage(vol_num, marker):
    db = get_db()
    vol = db.execute("SELECT * FROM volumes WHERE num=?", (vol_num,)).fetchone()
    if not vol:
        abort(404)
    p = db.execute(
        "SELECT * FROM passages WHERE volume_id=? AND marker=?",
        (vol['id'], marker)
    ).fetchone()
    if not p:
        abort(404)

    # Previous and next passages
    prev_p = db.execute("""
        SELECT marker FROM passages WHERE volume_id=?
          AND (page_num < ? OR (page_num=? AND col < ?))
        ORDER BY page_num DESC, col DESC LIMIT 1
    """, (vol['id'], p['page_num'], p['page_num'], p['col'])).fetchone()

    next_p = db.execute("""
        SELECT marker FROM passages WHERE volume_id=?
          AND (page_num > ? OR (page_num=? AND col > ?))
        ORDER BY page_num ASC, col ASC LIMIT 1
    """, (vol['id'], p['page_num'], p['page_num'], p['col'])).fetchone()

    # Topics that reference this passage
    ref_topics = db.execute("""
        SELECT DISTINCT t.name, t.slug FROM refs r
        JOIN topics t ON t.id = r.topic_id
        WHERE r.volume_num=?
          AND CAST(r.page_from AS INTEGER) <= ?
          AND (r.page_to='' OR CAST(r.page_to AS INTEGER) >= ?)
        LIMIT 10
    """, (vol_num, p['page_num'], p['page_num'])).fetchall()

    return render_template('passage.html',
        vol=vol, passage=p,
        prev_marker=prev_p['marker'] if prev_p else None,
        next_marker=next_p['marker'] if next_p else None,
        ref_topics=ref_topics,
        all_topics=get_all_topics()
    )

@app.route('/volume/<int:num>')
def volume(num):
    db = get_db()
    vol = db.execute("SELECT * FROM volumes WHERE num=?", (num,)).fetchone()
    if not vol:
        abort(404)
    # First 50 passages as preview
    passages = db.execute(
        "SELECT marker, page_num, col, substr(text,1,200) as snippet "
        "FROM passages WHERE volume_id=? ORDER BY page_num, col LIMIT 50",
        (vol['id'],)
    ).fetchall()
    total = db.execute(
        "SELECT COUNT(*) FROM passages WHERE volume_id=?", (vol['id'],)
    ).fetchone()[0]
    all_vols = db.execute("SELECT num, short_title FROM volumes ORDER BY num").fetchall()
    return render_template('volume.html',
        vol=vol, passages=passages, total=total,
        all_vols=all_vols, all_topics=get_all_topics()
    )

@app.route('/search')
def search():
    db = get_db()
    q = request.args.get('q', '').strip()
    stype = request.args.get('type', 'text')
    results = {'topics': [], 'passages': [], 'authors': []}

    if q:
        if stype in ('text', 'all'):
            # Full-text search on passages
            try:
                rows = db.execute("""
                    SELECT p.id, p.marker, p.volume_id, p.page_num, p.col,
                           substr(p.text,1,300) as snippet, v.num, v.short_title
                    FROM passages_fts f
                    JOIN passages p ON p.id = f.rowid
                    JOIN volumes v ON v.id = p.volume_id
                    WHERE passages_fts MATCH ?
                    ORDER BY rank LIMIT 30
                """, (q,)).fetchall()
                results['passages'] = rows
            except Exception:
                pass

        if stype in ('topic', 'all'):
            rows = db.execute("""
                SELECT name, slug, substr(intro_text,1,200) as snippet
                FROM topics WHERE name LIKE ? OR intro_text LIKE ?
                ORDER BY name LIMIT 20
            """, (f'%{q}%', f'%{q}%')).fetchall()
            results['topics'] = rows

        if stype in ('author', 'all'):
            rows = db.execute("""
                SELECT r.author, r.work, r.volume_num, r.page_from, r.page_to,
                       v.short_title, t.name as topic_name, t.slug as topic_slug
                FROM refs r
                JOIN volumes v ON v.num = r.volume_num
                JOIN topics t ON t.id = r.topic_id
                WHERE r.author LIKE ? OR r.work LIKE ?
                ORDER BY r.author, r.work LIMIT 40
            """, (f'%{q}%', f'%{q}%')).fetchall()
            results['authors'] = rows

    return render_template('search.html',
        q=q, stype=stype, results=results,
        all_topics=get_all_topics()
    )

@app.route('/api/passage/<int:vol_num>/<marker>')
def api_passage(vol_num, marker):
    db = get_db()
    vol = db.execute("SELECT * FROM volumes WHERE num=?", (vol_num,)).fetchone()
    if not vol:
        return jsonify({'error': 'Volume not found'}), 404
    p = db.execute(
        "SELECT * FROM passages WHERE volume_id=? AND marker=?",
        (vol['id'], marker)
    ).fetchone()
    if not p:
        return jsonify({'error': 'Passage not found'}), 404
    return jsonify({'marker': p['marker'], 'text': p['text'], 'volume': vol['title']})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
