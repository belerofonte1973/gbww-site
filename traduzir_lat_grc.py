#!/usr/bin/env python3
"""
traduzir_lat_grc.py
Tradução de latim/grego para português + consulta de dicionários.

Fontes:
  • Google Translate (gratuito, requer internet) — latim → PT, grego → PT
  • Lewis & Short (offline) — latim → inglês → PT
  • LSJ — Liddell-Scott-Jones (offline) — grego → inglês → PT
  • Collatinus lemmes.pt (offline) — latim → português (~9900 entradas)
  • Wikcionário Português (offline, requer download) — latim → português
"""

import re
import sqlite3
import unicodedata
import requests
from pathlib import Path

LS_XML          = Path("/usr/local/diogenes/dependencies/data/lat.ls.perseus-eng1.xml")
LSJ_XML         = Path("/usr/local/diogenes/dependencies/data/grc.lsj.xml")
COLLATINUS_PT   = Path("/usr/share/collatinus/data/lemmes.pt")
WIKT_PT_DB      = Path.home() / ".cache" / "busca_latina" / "wiktionary_pt.db"
GTRANS          = "https://translate.googleapis.com/translate_a/single"

_ls_bytes  = None   # cache do L&S em bytes
_lsj_bytes = None   # cache do LSJ em bytes


# ── utilitários ───────────────────────────────────────────────────────────────

def _limpar_xml(texto: str) -> str:
    txt = re.sub(r"<[^>]+>", " ", texto)
    txt = re.sub(r"&[a-zA-Z]+;", "", txt)
    return re.sub(r" {2,}", " ", txt).strip()

def _load_ls() -> bytes:
    global _ls_bytes
    if _ls_bytes is None:
        _ls_bytes = LS_XML.read_bytes()
    return _ls_bytes

def _load_lsj() -> bytes:
    global _lsj_bytes
    if _lsj_bytes is None:
        _lsj_bytes = LSJ_XML.read_bytes()
    return _lsj_bytes

def _extrair_entrada(data: bytes, marcador: bytes) -> str | None:
    """
    Encontra marcador em data, recua até <div1/div2, avança até </div1/div2>.
    Retorna a entrada limpa ou None.
    """
    pos = data.lower().find(marcador.lower())
    if pos == -1:
        return None
    # recua até o início do verbete
    for tag in (b'<div1', b'<div2'):
        s = data.rfind(tag, 0, pos)
        if s != -1:
            start = s
            break
    else:
        return None
    # avança até o fechamento
    close = b'</div1>' if b'<div1' in data[start:start+6] else b'</div2>'
    end = data.find(close, pos) + len(close)
    if end <= len(close):
        return None
    raw = data[start:end].decode("utf-8", errors="replace")
    return _limpar_xml(raw)


# ── Google Translate ──────────────────────────────────────────────────────────

def traduzir_para_pt(texto: str, lingua: str = "la") -> str:
    """
    Traduz para português via Google Translate (sem chave de API).
    lingua: 'la' = Latim  |  'grc'/'el' = Grego  |  'en' = inglês
    """
    if not texto.strip():
        return ""

    if lingua in ("grc", "el", "grego"):
        # Remove diacríticos politônicos (politônico → monotônico)
        texto_api = "".join(
            c for c in unicodedata.normalize("NFD", texto)
            if not unicodedata.combining(c)
        )
        lang_api = "el"
    elif lingua in ("en", "inglês"):
        texto_api = texto
        lang_api  = "en"
    else:
        texto_api = texto
        lang_api  = "la"

    try:
        r = requests.get(GTRANS, params={
            "client": "gtx", "sl": lang_api, "tl": "pt",
            "dt": "t", "q": texto_api,
        }, timeout=15)
        r.raise_for_status()
        return "".join(p[0] for p in r.json()[0] if p[0])
    except requests.exceptions.ConnectionError:
        return "[Sem conexão com a internet]"
    except Exception as e:
        return f"[Erro na tradução: {e}]"


# ── Lewis & Short (Latim → Inglês → PT) ──────────────────────────────────────

def lookup_ls(palavra: str, traduzir_pt: bool = True) -> str:
    """
    Consulta o Lewis & Short para uma palavra latina.
    Se traduzir_pt=True, também traduz a definição inglesa para português.
    """
    data    = _load_ls()
    marcador = f">{palavra.strip()}</head>".encode("utf-8")
    entrada  = _extrair_entrada(data, marcador)

    if not entrada:
        # tenta busca insensível a maiúsculas
        marcador2 = f">{palavra.strip().lower()}</head>".encode("utf-8")
        entrada   = _extrair_entrada(data, marcador2)

    if not entrada:
        return f'"{palavra}" não encontrado no Lewis & Short.'

    entrada = entrada[:2000] + ("…" if len(entrada) > 2000 else "")

    if traduzir_pt:
        pt = traduzir_para_pt(entrada[:800], lingua="en")
        return (
            f"── Lewis & Short (EN) ──────────────────────\n{entrada}\n\n"
            f"── Tradução para PT ────────────────────────\n{pt}"
        )
    return entrada


# ── LSJ — Liddell-Scott-Jones (Grego → Inglês → PT) ─────────────────────────

def lookup_lsj(palavra: str, traduzir_pt: bool = True) -> str:
    """
    Consulta o LSJ para uma palavra grega.
    Se traduzir_pt=True, também traduz a definição inglesa para português.
    """
    data    = _load_lsj()
    marcador = f">{palavra.strip()}</head>".encode("utf-8")
    entrada  = _extrair_entrada(data, marcador)

    if not entrada:
        # tenta sem diacríticos
        sem_diac = "".join(
            c for c in unicodedata.normalize("NFD", palavra.strip())
            if not unicodedata.combining(c)
        )
        marcador2 = f">{sem_diac}</head>".encode("utf-8")
        entrada   = _extrair_entrada(data, marcador2)

    if not entrada:
        return f'"{palavra}" não encontrado no LSJ.'

    entrada = entrada[:2000] + ("…" if len(entrada) > 2000 else "")

    if traduzir_pt:
        pt = traduzir_para_pt(entrada[:800], lingua="en")
        return (
            f"── LSJ (EN) ────────────────────────────────\n{entrada}\n\n"
            f"── Tradução para PT ────────────────────────\n{pt}"
        )
    return entrada


# ── Collatinus lemmes.pt (Latim → Português, offline) ────────────────────────

_collatinus_pt: dict[str, str] | None = None

def _load_collatinus_pt() -> dict[str, str]:
    global _collatinus_pt
    if _collatinus_pt is not None:
        return _collatinus_pt
    d: dict[str, str] = {}
    try:
        with open(COLLATINUS_PT, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("!") and ":" in line:
                    word, _, defn = line.partition(":")
                    w = word.strip().lower()
                    if w:
                        d[w] = defn.strip()
    except OSError:
        pass
    _collatinus_pt = d
    return d


def lookup_collatinus_pt(palavra: str) -> str:
    """Consulta o dicionário Collatinus (latim → português, offline)."""
    d = _load_collatinus_pt()
    if not d:
        return "[Collatinus não instalado — execute: sudo apt install collatinus]"
    key = palavra.strip().lower()
    defn = d.get(key)
    if defn:
        return f"── Collatinus Lat→PT ────────────────────────\n{palavra}:  {defn}"
    # tenta sem o último caractere (formas flexionadas simples)
    if len(key) > 3:
        for k, v in d.items():
            if k.startswith(key[:4]):
                return (
                    f"── Collatinus Lat→PT (forma próxima: {k}) ──\n{k}:  {v}"
                )
    return f'"{palavra}" não encontrado no Collatinus (PT).'


# ── Wikcionário Português (Latim → Português, offline após download) ──────────

def lookup_wikt_pt(palavra: str) -> str:
    """Consulta o Wikcionário Português (latim → português, offline)."""
    if not WIKT_PT_DB.exists():
        return (
            "[Base de dados do Wikcionário PT não encontrada.\n"
            "Execute primeiro:  python3 ~/baixar_dicionario_pt.py]"
        )
    try:
        conn = sqlite3.connect(f"file:{WIKT_PT_DB}?mode=ro", uri=True)
        row = conn.execute(
            "SELECT definicao FROM entradas WHERE palavra = ? COLLATE NOCASE",
            (palavra.strip(),),
        ).fetchone()
        conn.close()
        if row:
            return f"── Wikcionário PT ──────────────────────────\n{palavra}:  {row[0]}"
        return f'"{palavra}" não encontrado no Wikcionário PT.'
    except Exception as e:
        return f"[Erro ao consultar Wikcionário PT: {e}]"


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, argparse
    ap = argparse.ArgumentParser(description="Tradução e dicionário latim/grego → PT")
    ap.add_argument("texto", nargs="+", help="Texto ou palavra a traduzir/consultar")
    ap.add_argument("--lingua", "-l", default="la",
                    choices=["la", "grc", "en"],
                    help="Língua de origem (padrão: la)")
    ap.add_argument("--dic", "-d", action="store_true",
                    help="Consultar dicionário (L&S ou LSJ) em vez de traduzir")
    args = ap.parse_args()
    texto = " ".join(args.texto)

    if args.dic:
        if args.lingua == "grc":
            print(lookup_lsj(texto))
        else:
            print(lookup_ls(texto))
    else:
        print(traduzir_para_pt(texto, args.lingua))
