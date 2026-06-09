#!/usr/bin/env python3
"""
Wrapper para a API do servidor Diogenes local (http://127.0.0.1:8888).
Devolve JSON limpo com análise morfológica e entrada de dicionário.

Uso:
    python3 diogenes_api.py arma lat
    python3 diogenes_api.py λόγος grk

API programática:
    from diogenes_api import parse_word
    result = parse_word("amo", "lat")
"""

import subprocess
import sys
import json
import re
import time
import urllib.request
from bs4 import BeautifulSoup

DIOGENES_URL    = "http://127.0.0.1:8888"
DIOGENES_SERVER = "/usr/local/diogenes/server/diogenes-server.pl"
_server_started = False


def _ensure_running() -> bool:
    """Return True if the Diogenes server is reachable; auto-start if not."""
    global _server_started
    try:
        urllib.request.urlopen(f"{DIOGENES_URL}/", timeout=2)
        return True
    except Exception:
        if _server_started:
            return False
        try:
            subprocess.Popen(
                ["perl", DIOGENES_SERVER, "-p", "8888", "-l"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            _server_started = True
            time.sleep(3)
            urllib.request.urlopen(f"{DIOGENES_URL}/", timeout=3)
            return True
        except Exception:
            return False


def _fetch_html(word: str, lang: str) -> str:
    if not _ensure_running():
        raise ConnectionError("Servidor Diogenes não disponível em 127.0.0.1:8888")
    url = f"{DIOGENES_URL}/Perseus.cgi?do=parse&lang={lang}&q={urllib.request.quote(word)}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse_morphology(soup: BeautifulSoup, word: str) -> list[dict]:
    """Extrai análises morfológicas (lista de formas e descrições)."""
    analyses = []

    h1 = soup.find("h1", string=lambda t: t and "Perseus anal" in t)
    if not h1:
        return analyses

    # múltiplas análises → <ol><li>
    ol = h1.find_next_sibling("ol")
    if ol:
        for li in ol.find_all("li"):
            analyses.append(_parse_morph_line(li.get_text()))
    else:
        # análise única → <p>
        p = h1.find_next_sibling("p")
        if p:
            analyses.append(_parse_morph_line(p.get_text()))

    return analyses


def _parse_morph_line(text: str) -> dict:
    """
    'amō,amo: pres ind act 1st sg'  →  {lemma: 'amō,amo', description: 'pres ind act 1st sg'}
    'arma: neut nom/voc/acc pl'     →  {lemma: 'arma', description: 'neut nom/voc/acc pl'}
    """
    text = text.strip()
    if ":" in text:
        lemma, _, desc = text.partition(":")
        return {"lemma": lemma.strip(), "description": desc.strip()}
    return {"lemma": text, "description": ""}


def _parse_dictionary(soup: BeautifulSoup, lang: str) -> list[dict]:
    """Extrai entradas de dicionário (Lewis-Short para lat, LSJ para grk).

    O servidor devolve um único <h1> ("Lewis-Short entry/entries") seguido de
    um ou mais blocos <h2> headword + texto. Itera sobre os <h2> para apanhar
    todas as entradas.
    """
    dict_name = "Lewis-Short" if lang == "lat" else "LSJ"

    h1 = soup.find("h1", string=lambda t: t and ("Lewis" in t or "LSJ" in t))
    if not h1:
        return []

    # recolher todos os <h2> dentro do bloco do dicionário (até ao próximo <h1>)
    h2s = []
    for sib in h1.next_siblings:
        if sib.name == "h1":
            break
        if getattr(sib, "name", None) == "h2":
            h2s.append(sib)

    entries = []
    for h2 in h2s:
        spans = h2.find_all("span")
        headword = spans[0].get_text().strip() if spans else h2.get_text().strip()
        entry_text = _extract_entry_after_h2(h2)
        entries.append({"dictionary": dict_name, "headword": headword, "entry": entry_text})

    return entries


def _extract_entry_after_h2(h2) -> str:
    """Recolhe o texto da entrada entre este <h2> e o próximo <h2>/<h1>."""
    parts = []
    for sib in h2.next_siblings:
        if getattr(sib, "name", None) in ("h2", "h1"):
            break
        if hasattr(sib, "get_text"):
            text = sib.get_text(" ", strip=True)
            if "Previous Entry" in text or "Next Entry" in text:
                continue
            if text:
                parts.append(text)
        elif isinstance(sib, str):
            t = sib.strip()
            if t:
                parts.append(t)

    return re.sub(r"\s{2,}", " ", " ".join(parts)).strip()


def parse_word(word: str, lang: str = "lat") -> dict:
    """
    Analisa uma palavra usando o servidor Diogenes local.

    Args:
        word: palavra a analisar
        lang: 'lat' (latim) ou 'grk' (grego)

    Returns:
        dict com 'word', 'lang', 'morphology' e 'dictionary'
    """
    if lang not in ("lat", "grk"):
        raise ValueError("lang deve ser 'lat' ou 'grk'")

    html = _fetch_html(word, lang)
    soup = BeautifulSoup(html, "html.parser")

    # verificar se não houve resultado
    if "No Latin" in html or "No Greek" in html or "not found" in html.lower():
        return {"word": word, "lang": lang, "morphology": [], "dictionary": []}

    return {
        "word": word,
        "lang": lang,
        "morphology": _parse_morphology(soup, word),
        "dictionary": _parse_dictionary(soup, lang),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 diogenes_api.py PALAVRA [lat|grk]")
        sys.exit(1)

    word = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else "lat"

    result = parse_word(word, lang)
    print(json.dumps(result, ensure_ascii=False, indent=2))
