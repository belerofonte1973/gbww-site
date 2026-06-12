#!/usr/bin/env python3
"""Classics reader — Flask app."""

import json
import re
import sqlite3
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from flask import Flask, render_template, request, g, abort, jsonify, send_file, Response, stream_with_context

# ── optional imports ──────────────────────────────────────────────────────────

try:
    from diogenes_api import parse_word as diogenes_parse
    _DIOGENES_OK = True
except Exception:
    _DIOGENES_OK = False
    def diogenes_parse(w, l): return {'morphology': [], 'dictionary': []}

try:
    from gemini_lat import (traduzir_stream as _gemini_stream,
                             obter_chave as gemini_obter_chave,
                             guardar_chave as gemini_guardar_chave,
                             MODELOS_GEMINI, MODELO_DEFAULT as GEMINI_DEFAULT)
    _GEMINI_OK = True
except Exception:
    _GEMINI_OK = False
    MODELOS_GEMINI = []
    GEMINI_DEFAULT = 'gemini-2.5-flash'
    def _gemini_stream(t, l, m, k): return iter([])
    def gemini_obter_chave(): return ''
    def gemini_guardar_chave(_): pass

try:
    from claude_lat import (traduzir_stream as _claude_stream,
                             obter_chave as claude_obter_chave,
                             guardar_chave as claude_guardar_chave,
                             MODELOS_CLAUDE, MODELO_DEFAULT as CLAUDE_DEFAULT)
    _CLAUDE_OK = True
except Exception:
    _CLAUDE_OK = False
    MODELOS_CLAUDE = []
    CLAUDE_DEFAULT = 'claude-haiku-4-5-20251001'
    def _claude_stream(t, l, m, k): return iter([])
    def claude_obter_chave(): return ''
    def claude_guardar_chave(_): pass

try:
    from ollama_lat import traduzir_stream as _ollama_stream, comentario as _ollama_comentario, listar_modelos as _ollama_modelos
    _OLLAMA_OK = True
except Exception:
    _OLLAMA_OK = False
    def _ollama_modelos(): return []

try:
    from busca_latina import build_pattern, read_latin_lib, read_perseus_xml, label_ll, label_perseus, first_line_title, LATIN_LIB, PERSEUS
    _BUSCA_OK = True
except Exception:
    _BUSCA_OK = False

try:
    import traduzir_lat_grc as _trad
    _TRAD_OK = True
except Exception:
    _TRAD_OK = False

try:
    import pronunciar_latim as _pron
    _PRON_OK = True
except Exception:
    _PRON_OK = False
    class _pron:
        VOZES = []

try:
    import perseus_api as _papi
    _PERSEUS_OK = True
except Exception:
    _PERSEUS_OK = False

try:
    import sefaria_api as _sapi
    _SEFARIA_OK = True
except Exception:
    _SEFARIA_OK = False

try:
    import apibible_api as _abapi
    _APIBIBLE_OK = True
except Exception:
    _APIBIBLE_OK = False

try:
    import cdli_api as _cdli
    _CDLI_OK = True
except Exception:
    _CDLI_OK = False

try:
    import ll_online_api as _llonline
    _LLONLINE_OK = True
except Exception:
    _LLONLINE_OK = False

try:
    import phi_api as _phi
    _PHI_OK = True
except Exception:
    _PHI_OK = False

try:
    import morph_api as _morph
    _MORPH_OK = True
except Exception:
    _MORPH_OK = False

import csv as _csv

# ── OGL metadata ─────────────────────────────────────────────────────────────

OGL_GREGO = Path.home() / 'cltk_data/grc/text/first1kgreek'
_OGL_META: dict | None = None

def _carregar_meta_ogl() -> dict:
    global _OGL_META
    if _OGL_META is not None:
        return _OGL_META
    csv_path = OGL_GREGO / 'data' / 'edition_metadata.csv'
    meta = {}
    if csv_path.exists():
        try:
            with open(csv_path, newline='', encoding='utf-8') as fh:
                for row in _csv.DictReader(fh, delimiter='\t'):
                    stem = Path(row.get('Filename', '')).stem
                    meta[stem] = {
                        'author': (row.get('Author', '') or '').strip(),
                        'title':  (row.get('Title',  '') or '').strip(),
                    }
        except Exception:
            pass
    _OGL_META = meta
    return meta

def label_ogl(path: Path) -> tuple:
    info = _carregar_meta_ogl().get(path.stem, {})
    return (info.get('author') or path.parts[-2],
            info.get('title')  or path.stem)

# ── app ───────────────────────────────────────────────────────────────────────

app = Flask(__name__)
DB  = Path(__file__).parent / 'classics.db'
LIT_PER_PAGE = 20

def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

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


# ── Busca Greco-Latina ────────────────────────────────────────────────────────

@app.route('/')
@app.route('/busca')
def busca():
    return render_template(
        'busca.html',
        pron_ok=_PRON_OK,
        vozes=_pron.VOZES if _PRON_OK else [],
        cdli_ok=_CDLI_OK,
        cdli_langs=_cdli.LANG_LABELS if _CDLI_OK else {},
        apibible_ok=_APIBIBLE_OK,
        apibible_key_set=bool(_abapi.obter_chave()) if _APIBIBLE_OK else False,
        gemini_ok=_GEMINI_OK,
        gemini_key_set=bool(gemini_obter_chave()) if _GEMINI_OK else False,
        gemini_models=MODELOS_GEMINI,
        claude_ok=_CLAUDE_OK,
        claude_key_set=bool(claude_obter_chave()) if _CLAUDE_OK else False,
        claude_models=MODELOS_CLAUDE,
        ollama_ok=_OLLAMA_OK,
        ollama_models=_ollama_modelos() if _OLLAMA_OK else [],
        trad_ok=_TRAD_OK,
    )


@app.route('/api/buscar')
def api_buscar():
    q         = request.args.get('q', '').strip()
    ignore    = request.args.get('ignore', '1') == '1'
    ctx       = max(0, min(10, int(request.args.get('ctx', 2))))
    max_res   = max(0, int(request.args.get('max', 100)))
    corpus_id = int(request.args.get('corpus', 0))

    def generate():
        if not q:
            yield sse('erro', {'msg': 'Termo vazio'}); return
        if not _BUSCA_OK:
            yield sse('erro', {'msg': 'busca_latina.py não disponível'}); return
        try:
            pattern = build_pattern(q, ignore)
        except re.error as e:
            yield sse('erro', {'msg': f'Regex inválida: {e}'}); return

        total  = 0
        do_ll  = corpus_id in (0, 1)
        do_per = corpus_id in (0, 2)
        do_ogl = corpus_id == 3

        if do_ll and LATIN_LIB.exists():
            for path in sorted(LATIN_LIB.rglob('*.txt')):
                yield sse('status', {'msg': f'Latin Library: {path.name}…'})
                lines  = read_latin_lib(path)
                author, work = label_ll(path)
                title = first_line_title(path)
                if title and title.lower() not in work.lower():
                    work = f'{work} [{title[:50]}]'
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        s = max(0, i - ctx); e = min(len(lines), i + ctx + 1)
                        yield sse('result', {
                            'corpus': 'Latin Library', 'author': author, 'work': work,
                            'lines': [lines[j].rstrip() for j in range(s, e)],
                            'match_offset': i - s,
                        })
                        total += 1
                        if max_res and total >= max_res:
                            yield sse('done', {'total': total, 'truncated': True}); return

        if do_per and PERSEUS.exists():
            for path in sorted(PERSEUS.rglob('*_lat.xml')):
                yield sse('status', {'msg': f'Perseus: {path.name}…'})
                lines  = read_perseus_xml(path)
                author, work = label_perseus(path)
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        s = max(0, i - ctx); e = min(len(lines), i + ctx + 1)
                        yield sse('result', {
                            'corpus': 'Perseus', 'author': author, 'work': work,
                            'lines': [lines[j].rstrip() for j in range(s, e)],
                            'match_offset': i - s,
                        })
                        total += 1
                        if max_res and total >= max_res:
                            yield sse('done', {'total': total, 'truncated': True}); return

        if do_ogl and OGL_GREGO.exists():
            ogl_files = sorted(
                p for p in OGL_GREGO.rglob('*.xml')
                if not any(s in p.stem for s in ('_eng', '_intro', 'textcrit', 'appcrit', 'index'))
            )
            for path in ogl_files:
                yield sse('status', {'msg': f'OGL: {path.name}…'})
                lines  = read_perseus_xml(path)
                author, work = label_ogl(path)
                for i, line in enumerate(lines):
                    if pattern.search(line):
                        s = max(0, i - ctx); e = min(len(lines), i + ctx + 1)
                        yield sse('result', {
                            'corpus': 'Open Greek & Latin', 'author': author, 'work': work,
                            'lines': [lines[j].rstrip() for j in range(s, e)],
                            'match_offset': i - s,
                        })
                        total += 1
                        if max_res and total >= max_res:
                            yield sse('done', {'total': total, 'truncated': True}); return

        yield sse('done', {'total': total, 'truncated': False})

    return Response(stream_with_context(generate()),
                    content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ── tradução (Gemini + Ollama) — SSE ─────────────────────────────────────────

@app.route('/api/traduzir', methods=['POST'])
def api_traduzir():
    data   = request.get_json(force=True, silent=True) or {}
    texto  = (data.get('texto') or '').strip()
    lingua = data.get('lingua', 'la')
    motor  = data.get('motor', 'gemini')
    modelo = data.get('modelo') or None

    def generate():
        if not texto:
            yield sse('erro', {'msg': 'Texto vazio'}); return

        if motor in ('ollama', 'comentario'):
            if not _OLLAMA_OK:
                yield sse('erro', {'msg': 'Ollama não disponível'}); return
            fn = _ollama_comentario if motor == 'comentario' else _ollama_stream
            try:
                for frag in fn(texto, *([modelo] if modelo else [])):
                    yield sse('chunk', {'text': frag})
            except Exception as ex:
                yield sse('erro', {'msg': str(ex)})

        elif motor == 'claude':
            if not _CLAUDE_OK:
                yield sse('erro', {'msg': 'claude_lat.py não disponível'}); return
            chave = claude_obter_chave()
            if not chave:
                yield sse('erro', {'msg': 'Chave Claude não configurada — clique em 🔑'}); return
            try:
                for frag in _claude_stream(texto, lingua, modelo or CLAUDE_DEFAULT, chave):
                    yield sse('chunk', {'text': frag})
            except Exception as ex:
                yield sse('erro', {'msg': str(ex)})

        else:  # gemini (default)
            if not _GEMINI_OK:
                yield sse('erro', {'msg': 'Gemini não disponível'}); return
            chave = gemini_obter_chave()
            if not chave:
                yield sse('erro', {'msg': 'Chave Gemini não configurada — clique em 🔑'}); return
            try:
                for frag in _gemini_stream(texto, lingua, modelo or GEMINI_DEFAULT, chave):
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


# ── Claude chave ──────────────────────────────────────────────────────────────

@app.route('/api/claude_chave', methods=['POST'])
def api_claude_chave():
    if not _CLAUDE_OK:
        return jsonify({'ok': False, 'msg': 'claude_lat.py não disponível'})
    chave = ((request.get_json(force=True, silent=True) or {}).get('chave') or '').strip()
    if not chave:
        return jsonify({'ok': False, 'msg': 'Chave vazia'})
    claude_guardar_chave(chave)
    return jsonify({'ok': True})


# ── Tradução Interlinear (offline — dicionários locais) ───────────────────────

@app.route('/api/traduzir/interlinear', methods=['POST'])
def api_traduzir_interlinear():
    data   = request.get_json(force=True, silent=True) or {}
    texto  = (data.get('texto') or '').strip()
    lingua = data.get('lingua', 'la')

    if not texto:
        return jsonify({'erro': 'Texto vazio'}), 400
    if not _TRAD_OK:
        return jsonify({'erro': 'traduzir_lat_grc.py não disponível'}), 503

    import re as _re
    tokens = _re.findall(r"[\wͰ-Ͽἀ-῿א-ת]+|[^\w\s]", texto)
    linhas = []

    for tok in tokens:
        if not tok.isalpha():
            linhas.append({'palavra': tok, 'glosa': ''})
            continue
        glosa = ''
        try:
            if lingua == 'la':
                glosa = _trad.lookup_collatinus_pt(tok)
                if not glosa or glosa.startswith('(não encontrado)'):
                    glosa = _trad.lookup_ls(tok, traduzir_pt=False) or ''
                    if glosa:
                        glosa = glosa[:120]
            elif lingua == 'grc':
                glosa = _trad.lookup_lsj(tok, traduzir_pt=False) or ''
                if glosa:
                    glosa = glosa[:120]
        except Exception:
            pass
        linhas.append({'palavra': tok, 'glosa': glosa.strip()})

    return jsonify({'linhas': linhas, 'lingua': lingua})


# ── traduzir_pt (compatibilidade com literary.html) ───────────────────────────

@app.route('/api/traduzir_pt', methods=['POST'])
def api_traduzir_pt():
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
            for frag in _gemini_stream(texto, 'en', modelo or GEMINI_DEFAULT, chave):
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


# ── dicionários ───────────────────────────────────────────────────────────────

@app.route('/api/dict/<fonte>')
def api_dict(fonte):
    palavra = request.args.get('q', '').strip()
    if not palavra:
        return jsonify({'erro': 'Palavra em falta'}), 400
    if not _TRAD_OK:
        return jsonify({'erro': 'traduzir_lat_grc.py não disponível'}), 503
    try:
        if fonte == 'ls':
            return jsonify({'resultado': _trad.lookup_ls(palavra, traduzir_pt=False)})
        elif fonte == 'lsj':
            return jsonify({'resultado': _trad.lookup_lsj(palavra, traduzir_pt=False)})
        elif fonte == 'collatinus_pt':
            return jsonify({'resultado': _trad.lookup_collatinus_pt(palavra)})
        elif fonte == 'wikt_pt':
            return jsonify({'resultado': _trad.lookup_wikt_pt(palavra)})
        else:
            return jsonify({'erro': f'Fonte desconhecida: {fonte}'}), 400
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


# ── pronúncia ─────────────────────────────────────────────────────────────────

@app.route('/api/pronunciar', methods=['POST'])
def api_pronunciar():
    if not _PRON_OK:
        return jsonify({'erro': 'pronunciar_latim.py não disponível'}), 503
    data       = request.get_json(force=True, silent=True) or {}
    texto      = (data.get('texto') or '').strip()
    voz        = data.get('voz', 'it-IT-DiegoNeural')
    variante   = data.get('variante', 'classico')
    velocidade = int(float(data.get('velocidade', 0)))
    if not texto:
        return jsonify({'erro': 'Texto vazio'}), 400
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
            tmp_path = Path(tmp.name)
        fmt = _pron.pronunciar(texto, voz=voz, variante=variante,
                               velocidade=velocidade, saida=str(tmp_path))
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            return jsonify({'erro': 'Falha ao gerar áudio'}), 500
        mime = 'audio/wav' if fmt == 'wav' else 'audio/mpeg'
        ext  = 'wav' if fmt == 'wav' else 'mp3'
        return send_file(tmp_path, mimetype=mime,
                         as_attachment=False, download_name=f'audio.{ext}')
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/pronunciar/vozes')
def api_vozes():
    if not _PRON_OK:
        return jsonify([])
    return jsonify([{'id': v[0], 'label': v[1], 'motor': v[2], 'lingua': v[3]}
                    for v in _pron.VOZES])


# ── Gemini chave ──────────────────────────────────────────────────────────────

@app.route('/api/gemini_chave', methods=['POST'])
def api_gemini_chave():
    if not _GEMINI_OK:
        return jsonify({'ok': False, 'msg': 'Gemini não disponível'})
    chave = ((request.get_json(force=True, silent=True) or {}).get('chave') or '').strip()
    if not chave:
        return jsonify({'ok': False, 'msg': 'Chave vazia'})
    gemini_guardar_chave(chave)
    return jsonify({'ok': True})


# ── Ollama modelos ────────────────────────────────────────────────────────────

@app.route('/api/modelos_ollama')
def api_modelos_ollama():
    return jsonify(_ollama_modelos() if _OLLAMA_OK else [])


# ── Perseus API ───────────────────────────────────────────────────────────────

@app.route('/api/perseus/catalogo')
def api_perseus_catalogo():
    if not _PERSEUS_OK:
        return jsonify({'erro': 'perseus_api.py não disponível'})
    lingua = request.args.get('lingua', 'grc')
    forcar = request.args.get('forcar', '0') == '1'
    try:
        return jsonify(_papi.obter_catalogo(lingua, forcar=forcar))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/perseus/refs')
def api_perseus_refs():
    if not _PERSEUS_OK:
        return jsonify({'erro': 'perseus_api.py não disponível'})
    urn = request.args.get('urn', '')
    if not urn:
        return jsonify({'erro': 'URN em falta'}), 400
    try:
        return jsonify(_papi.obter_referencias(urn, nivel=1))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/perseus/passagem')
def api_perseus_passagem():
    if not _PERSEUS_OK:
        return jsonify({'erro': 'perseus_api.py não disponível'})
    urn = request.args.get('urn', '')
    if not urn:
        return jsonify({'erro': 'URN em falta'}), 400
    try:
        return jsonify({'texto': _papi.obter_passagem(urn)})
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/perseus/obra')
def api_perseus_obra():
    if not _PERSEUS_OK:
        return Response(sse('erro', {'msg': 'perseus_api.py não disponível'}),
                        content_type='text/event-stream')
    urn = request.args.get('urn', '')

    def generate():
        if not urn:
            yield sse('erro', {'msg': 'URN em falta'}); return
        try:
            refs  = _papi.obter_referencias(urn, nivel=1)
            total = len(refs)
            yield sse('status', {'msg': f'0/{total} secções…'})
            resultados = [None] * total
            with ThreadPoolExecutor(max_workers=5) as exe:
                futuros = {exe.submit(_papi.obter_passagem, ref): i
                           for i, ref in enumerate(refs)}
                concluidos = 0
                for fut in as_completed(futuros):
                    i = futuros[fut]
                    try:
                        resultados[i] = fut.result()
                    except Exception as ex:
                        resultados[i] = f'[Erro: {ex}]'
                    concluidos += 1
                    yield sse('progress', {'atual': concluidos, 'total': total})
            yield sse('done', {'texto': '\n\n'.join(r for r in resultados if r)})
        except Exception as ex:
            yield sse('erro', {'msg': str(ex)})

    return Response(stream_with_context(generate()),
                    content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ── Sefaria API ───────────────────────────────────────────────────────────────

@app.route('/api/sefaria/catalogo')
def api_sefaria_catalogo():
    if not _SEFARIA_OK:
        return jsonify({'erro': 'sefaria_api.py não disponível'})
    categoria = request.args.get('categoria', 'Tanakh')
    forcar    = request.args.get('forcar', '0') == '1'
    try:
        return jsonify(_sapi.obter_catalogo(categoria, forcar=forcar))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/sefaria/refs')
def api_sefaria_refs():
    if not _SEFARIA_OK:
        return jsonify({'erro': 'sefaria_api.py não disponível'})
    titulo = request.args.get('titulo', '')
    if not titulo:
        return jsonify({'erro': 'titulo em falta'}), 400
    try:
        return jsonify(_sapi.obter_refs(titulo))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/sefaria/passagem')
def api_sefaria_passagem():
    if not _SEFARIA_OK:
        return jsonify({'erro': 'sefaria_api.py não disponível'})
    ref = request.args.get('ref', '')
    if not ref:
        return jsonify({'erro': 'ref em falta'}), 400
    try:
        return jsonify(_sapi.obter_passagem(ref))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/sefaria/obra')
def api_sefaria_obra():
    if not _SEFARIA_OK:
        return Response(sse('erro', {'msg': 'sefaria_api.py não disponível'}),
                        content_type='text/event-stream')
    titulo = request.args.get('titulo', '')

    def generate():
        if not titulo:
            yield sse('erro', {'msg': 'titulo em falta'}); return
        try:
            refs  = _sapi.obter_refs(titulo)
            total = len(refs)
            yield sse('status', {'msg': f'0/{total} capítulos…'})
            resultados = [None] * total
            with ThreadPoolExecutor(max_workers=5) as exe:
                futuros = {exe.submit(_sapi.obter_passagem, ref): i
                           for i, ref in enumerate(refs)}
                concluidos = 0
                for fut in as_completed(futuros):
                    i = futuros[fut]
                    try:
                        d = fut.result()
                        resultados[i] = d.get('texto_heb', '')
                    except Exception as ex:
                        resultados[i] = f'[Erro: {ex}]'
                    concluidos += 1
                    yield sse('progress', {'atual': concluidos, 'total': total})
            yield sse('done', {'texto': '\n\n'.join(r for r in resultados if r)})
        except Exception as ex:
            yield sse('erro', {'msg': str(ex)})

    return Response(stream_with_context(generate()),
                    content_type='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ── API.Bible ─────────────────────────────────────────────────────────────────

@app.route('/api/apibible/chave', methods=['GET', 'POST'])
def api_apibible_chave():
    if not _APIBIBLE_OK:
        return jsonify({'ok': False, 'msg': 'apibible_api.py não disponível'})
    if request.method == 'POST':
        chave = ((request.get_json(force=True, silent=True) or {}).get('chave') or '').strip()
        if not chave:
            return jsonify({'ok': False, 'msg': 'Chave vazia'})
        _abapi.guardar_chave(chave)
        return jsonify({'ok': True})
    return jsonify({'tem_chave': bool(_abapi.obter_chave())})


@app.route('/api/apibible/biblias')
def api_apibible_biblias():
    if not _APIBIBLE_OK:
        return jsonify({'erro': 'apibible_api.py não disponível'})
    try:
        return jsonify(_abapi.listar_biblias_heb(forcar=request.args.get('forcar', '0') == '1'))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/apibible/livros')
def api_apibible_livros():
    if not _APIBIBLE_OK:
        return jsonify({'erro': 'apibible_api.py não disponível'})
    biblia_id = request.args.get('biblia_id', '')
    if not biblia_id:
        return jsonify({'erro': 'biblia_id em falta'}), 400
    try:
        return jsonify(_abapi.listar_livros(biblia_id))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/apibible/capitulos')
def api_apibible_capitulos():
    if not _APIBIBLE_OK:
        return jsonify({'erro': 'apibible_api.py não disponível'})
    biblia_id = request.args.get('biblia_id', '')
    livro_id  = request.args.get('livro_id', '')
    if not biblia_id or not livro_id:
        return jsonify({'erro': 'biblia_id e livro_id obrigatórios'}), 400
    try:
        return jsonify(_abapi.listar_capitulos(biblia_id, livro_id))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/apibible/passagem')
def api_apibible_passagem():
    if not _APIBIBLE_OK:
        return jsonify({'erro': 'apibible_api.py não disponível'})
    biblia_id   = request.args.get('biblia_id', '')
    passagem_id = request.args.get('passagem_id', '')
    if not biblia_id or not passagem_id:
        return jsonify({'erro': 'biblia_id e passagem_id obrigatórios'}), 400
    try:
        return jsonify(_abapi.obter_passagem(biblia_id, passagem_id))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


# ── Latin Library (online) ────────────────────────────────────────────────────

@app.route('/api/online/ll/catalogo')
def api_ll_catalogo():
    if not _LLONLINE_OK:
        return jsonify({'erro': 'll_online_api.py não disponível'}), 503
    forcar = request.args.get('forcar', '0') == '1'
    try:
        return jsonify(_llonline.obter_catalogo(forcar=forcar))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/online/ll/texto')
def api_ll_texto():
    if not _LLONLINE_OK:
        return jsonify({'erro': 'll_online_api.py não disponível'}), 503
    url = request.args.get('id', '').strip()
    if not url or not url.startswith('http'):
        return jsonify({'erro': 'URL inválido'}), 400
    try:
        return jsonify({'texto': _llonline.obter_texto(url)})
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


# ── PHI Latin ─────────────────────────────────────────────────────────────────

@app.route('/api/phi/catalogo')
def api_phi_catalogo():
    if not _PHI_OK:
        return jsonify({'erro': 'phi_api.py não disponível'}), 503
    forcar = request.args.get('forcar', '0') == '1'
    try:
        return jsonify(_phi.obter_catalogo(forcar=forcar))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/phi/texto')
def api_phi_texto():
    if not _PHI_OK:
        return jsonify({'erro': 'phi_api.py não disponível'}), 503
    urn = request.args.get('urn', '').strip()
    if not urn or not urn.startswith('/'):
        return jsonify({'erro': 'URN inválido'}), 400
    try:
        return jsonify({'texto': _phi.obter_texto(urn)})
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


# ── Análise Morfológica (Alpheios) ────────────────────────────────────────────

@app.route('/api/morph/analise')
def api_morph_analise():
    if not _MORPH_OK:
        return jsonify({'erro': 'morph_api.py não disponível'}), 503
    word = request.args.get('word', '').strip()
    lang = request.args.get('lang', 'lat')
    if not word:
        return jsonify({'erro': 'Palavra em falta'}), 400
    if lang not in ('lat', 'grc'):
        return jsonify({'erro': 'Língua inválida (use lat ou grc)'}), 400
    try:
        result = _morph.analisar(word, lang)
        # enriquecer com Diogenes se disponível
        if _DIOGENES_OK:
            diog_lang = 'lat' if lang == 'lat' else 'grk'
            try:
                diog = diogenes_parse(word, diog_lang)
                if diog.get('dictionary'):
                    result['diogenes'] = diog
            except Exception:
                pass
        return jsonify(result)
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


# ── CDLI (Cuneiform Digital Library) ─────────────────────────────────────────

@app.route('/api/cdli/pesquisar')
def api_cdli_pesquisar():
    if not _CDLI_OK:
        return jsonify({'erro': 'cdli_api.py não disponível'})
    termo  = request.args.get('q', '').strip()
    lang   = request.args.get('lang', '')
    limite = max(1, min(200, int(request.args.get('limite', 50))))
    try:
        return jsonify(_cdli.pesquisar(termo, lang=lang, limite=limite))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/cdli/artefato/<artifact_id>')
def api_cdli_artefato(artifact_id):
    if not _CDLI_OK:
        return jsonify({'erro': 'cdli_api.py não disponível'})
    try:
        return jsonify(_cdli.obter_artefato(artifact_id))
    except Exception as ex:
        return jsonify({'erro': str(ex)}), 500


@app.route('/api/cdli/obras_notaveis')
def api_cdli_obras_notaveis():
    if not _CDLI_OK:
        return jsonify([])
    return jsonify(_cdli.OBRAS_NOTAVEIS)


# ── API: Diogenes / LSJ / Lewis-Short ────────────────────────────────────────

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
    para_lines = defaultdict(list)
    for ln in raw_lines:
        para_lines[ln['para_id']].append(ln)
    sections = []
    for para in paras:
        lines_out = []
        for ln in para_lines.get(para['id'], []):
            words = json.loads(ln['words_json']) if ln['words_json'] else []
            lines_out.append({'num': ln['line_num'], 'translit': ln['translit'], 'words': words})
        sections.append({'para': dict(para), 'lines': lines_out})
    lang_texts = db.execute(
        'SELECT id, title_pt FROM lit_texts WHERE lang=? ORDER BY id',
        (text['lang'],)
    ).fetchall()
    return render_template('literary.html',
        text=text, sections=sections, page=page, total_pages=total_pages,
        all_texts=lang_texts,
        gemini_ok=_GEMINI_OK,
        gemini_key_set=bool(gemini_obter_chave()) if _GEMINI_OK else False,
    )


# ── search (bíblico FTS) ──────────────────────────────────────────────────────

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


if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
