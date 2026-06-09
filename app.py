#!/usr/bin/env python3
"""Classics reader — Flask app."""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from flask import Flask, render_template, request, g, abort, jsonify, redirect, url_for

try:
    from diogenes_api import parse_word as diogenes_parse
    _DIOGENES_OK = True
except Exception:
    _DIOGENES_OK = False
    def diogenes_parse(w, l): return {'morphology': [], 'dictionary': []}

try:
    from gemini_lat import traduzir_stream as _gemini_stream, obter_chave as gemini_obter_chave
    _GEMINI_OK = True
except Exception:
    _GEMINI_OK = False
    def _gemini_stream(t, l, m, k): return iter([])
    def gemini_obter_chave(): return ''

app = Flask(__name__)
DB  = Path(__file__).parent / 'classics.db'
LIT_PER_PAGE = 20   # paragraphs per page for literary texts


# ── database ──────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()


def all_books():
    return get_db().execute('SELECT * FROM books ORDER BY num').fetchall()


def all_lit_texts():
    return get_db().execute('SELECT * FROM lit_texts ORDER BY lang, id').fetchall()


# ── index ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', books=all_books(), lit_texts=all_lit_texts())


# ── biblical reader ───────────────────────────────────────────────────────────

@app.route('/read/<int:book_num>')
def book_root(book_num):
    return reader(book_num, 1)


@app.route('/read/<int:book_num>/<int:chapter>')
def reader(book_num, chapter):
    db   = get_db()
    book = db.execute('SELECT * FROM books WHERE num=?', (book_num,)).fetchone()
    if not book:
        abort(404)

    chapter = max(1, min(chapter, book['chapters']))

    rows = db.execute(
        'SELECT * FROM tokens WHERE book_num=? AND chapter=? ORDER BY verse, position',
        (book_num, chapter)
    ).fetchall()

    verses = {}
    for tok in rows:
        v = tok['verse']
        verses.setdefault(v, []).append(tok)

    tr_rows = db.execute(
        'SELECT verse, text_pt FROM verse_translations WHERE book_num=? AND chapter=?',
        (book_num, chapter)
    ).fetchall()
    trans = {r['verse']: r['text_pt'] for r in tr_rows}

    return render_template('reader.html',
        book=book, chapter=chapter, verses=verses, trans=trans, books=all_books())


# ── literary reader ───────────────────────────────────────────────────────────

@app.route('/literary/<path:text_id>')
def literary(text_id):
    db   = get_db()
    text = db.execute('SELECT * FROM lit_texts WHERE id=?', (text_id,)).fetchone()
    if not text:
        abort(404)

    page        = max(1, int(request.args.get('page', 1)))
    total_paras = db.execute(
        'SELECT COUNT(*) FROM lit_paragraphs WHERE text_id=?', (text_id,)
    ).fetchone()[0]
    total_pages = max(1, (total_paras + LIT_PER_PAGE - 1) // LIT_PER_PAGE)
    page        = min(page, total_pages)

    paras = db.execute(
        'SELECT * FROM lit_paragraphs WHERE text_id=? ORDER BY line_from LIMIT ? OFFSET ?',
        (text_id, LIT_PER_PAGE, (page - 1) * LIT_PER_PAGE)
    ).fetchall()

    if paras:
        line_min = paras[0]['line_from']
        line_max = paras[-1]['line_to']
        raw_lines = db.execute(
            'SELECT * FROM lit_lines WHERE text_id=? AND line_num BETWEEN ? AND ? ORDER BY line_num',
            (text_id, line_min, line_max)
        ).fetchall()
    else:
        raw_lines = []

    # Group lines by para_id
    para_lines = defaultdict(list)
    for ln in raw_lines:
        para_lines[ln['para_id']].append(ln)

    # Decode words JSON once
    sections = []
    for para in paras:
        lines_out = []
        for ln in para_lines.get(para['id'], []):
            words = json.loads(ln['words_json']) if ln['words_json'] else []
            lines_out.append({'num': ln['line_num'], 'translit': ln['translit'], 'words': words})
        sections.append({'para': dict(para), 'lines': lines_out})

    # Sidebar: texts of same language
    lang_texts = db.execute(
        'SELECT id, title_pt FROM lit_texts WHERE lang=? ORDER BY id',
        (text['lang'],)
    ).fetchall()

    return render_template('literary.html',
        text=text,
        sections=sections,
        page=page,
        total_pages=total_pages,
        all_texts=lang_texts,
        gemini_ok=_GEMINI_OK,
        gemini_key_set=bool(gemini_obter_chave()) if _GEMINI_OK else False,
    )


# ── API: Diogenes / LSJ ───────────────────────────────────────────────────────

@app.route('/api/lsj/<path:lemma>')
def api_lsj(lemma):
    try:
        result = diogenes_parse(lemma, 'grk')
        return jsonify(result)
    except Exception as exc:
        return jsonify({'error': str(exc), 'morphology': [], 'dictionary': []}), 200


@app.route('/api/lewis/<path:word>')
def api_lewis(word):
    try:
        result = diogenes_parse(word, 'lat')
        return jsonify(result)
    except Exception as exc:
        return jsonify({'error': str(exc), 'morphology': [], 'dictionary': []}), 200


# ── API: Strong's Hebrew ──────────────────────────────────────────────────────

@app.route('/api/strongs/<strong_num>')
def api_strongs(strong_num):
    db  = get_db()
    row = db.execute('SELECT * FROM strongs_heb WHERE num=?', (strong_num.upper(),)).fetchone()
    if not row:
        return jsonify({'error': f'Sem entrada para {strong_num}'}), 200
    return jsonify({'num': row['num'], 'lemma_heb': row['lemma_heb'],
                    'xlit': row['xlit'], 'definition': row['definition']})


# ── API: traduzir via Gemini (SSE) ────────────────────────────────────────────

from flask import Response, stream_with_context

def sse(event, data):
    import json as _json
    return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


@app.route('/api/traduzir_pt', methods=['POST'])
def api_traduzir_pt():
    """Translate English paragraph to Portuguese via Gemini (SSE)."""
    data   = request.get_json(force=True, silent=True) or {}
    texto  = (data.get('texto') or '').strip()
    modelo = data.get('modelo') or None

    def generate():
        if not texto:
            yield sse('erro', {'msg': 'Texto vazio'}); return
        if not _GEMINI_OK:
            yield sse('erro', {'msg': 'Gemini não disponível'}); return
        chave = gemini_obter_chave()
        if not chave:
            yield sse('erro', {'msg': 'Chave Gemini não configurada'}); return
        try:
            for frag in _gemini_stream(texto, 'en', modelo or 'gemini-2.0-flash', chave):
                if frag.startswith('\x01retry:'):
                    yield sse('status', {'msg': frag[7:]})
                else:
                    yield sse('chunk', {'text': frag})
        except Exception as ex:
            yield sse('erro', {'msg': str(ex)})
        yield sse('done', {})

    return Response(stream_with_context(generate()),
                    content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ── search ────────────────────────────────────────────────────────────────────

@app.route('/search')
def search():
    db   = get_db()
    q    = request.args.get('q', '').strip()
    rows = []
    if q:
        try:
            rows = db.execute(
                '''SELECT t.id, t.book_num, t.chapter, t.verse, t.text,
                          t.lemma, t.desc_pt, b.name_pt, b.code
                   FROM tokens_fts f
                   JOIN tokens t ON t.id = f.rowid
                   JOIN books  b ON b.num = t.book_num
                   WHERE tokens_fts MATCH ?
                   ORDER BY t.book_num, t.chapter, t.verse, t.position
                   LIMIT 200''', (q,)
            ).fetchall()
        except Exception:
            pass
    return render_template('search.html', q=q, rows=rows, books=all_books())


@app.route('/api/gemini_chave', methods=['POST'])
def api_gemini_chave():
    if not _GEMINI_OK:
        return jsonify({'ok': False, 'msg': 'Gemini não disponível'})
    try:
        from gemini_lat import guardar_chave as gemini_guardar_chave
    except Exception:
        return jsonify({'ok': False, 'msg': 'gemini_lat.py não encontrado'})
    chave = ((request.get_json(force=True, silent=True) or {}).get('chave') or '').strip()
    if not chave:
        return jsonify({'ok': False, 'msg': 'Chave vazia'})
    gemini_guardar_chave(chave)
    return jsonify({'ok': True})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
