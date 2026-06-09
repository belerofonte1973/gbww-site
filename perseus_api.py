#!/usr/bin/env python3
"""
perseus_api.py — Acesso à API CTS do Perseus Project (textos gregos e latinos).

Endpoints usados (sem autenticação, uso livre):
  cts.perseids.org/api/cts/?request=GetCapabilities
  cts.perseids.org/api/cts/?request=GetValidReff&urn=URN&level=N
  cts.perseids.org/api/cts/?request=GetPassage&urn=URN

O catálogo é guardado em cache local (7 dias) para evitar pedidos repetidos.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

CTS_BASE    = "http://cts.perseids.org/api/cts/"
CACHE_DIR   = Path.home() / ".config" / "busca_latina"
CATALOG_TTL = 7 * 24 * 3600          # 7 dias em segundos
TIMEOUT_CAT = 45                      # timeout para GetCapabilities (grande)
TIMEOUT_REF = 20
TIMEOUT_PAS = 25

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# elementos TEI cujo conteúdo de texto deve ser ignorado
_IGNORAR_TAGS = {"teiheader", "note", "bibl", "figdesc", "foreign",
                 "app", "rdg", "lem",
                 # metadados CTS (wrapper da resposta, não conteúdo TEI)
                 "request", "requestname", "requesturn", "urn"}


# ── utilitários internos ──────────────────────────────────────────────────────

def _tag(elem) -> str:
    """Devolve o nome local do elemento (sem namespace)."""
    t = elem.tag
    return t.split("}")[-1].lower() if "}" in t else t.lower()


def _get(params: dict, timeout: int = 20) -> str:
    resp = requests.get(CTS_BASE, params=params, timeout=timeout,
                        headers={"User-Agent": "BuscaLatina/2.0"})
    resp.raise_for_status()
    return resp.text


def _extrair_texto(xml_str: str) -> str:
    """Extrai texto limpo de uma resposta XML TEI do Perseus."""
    # Remove DTD interno (causa erros no ElementTree)
    xml_str = re.sub(r"<!DOCTYPE[^>]*(?:\[.*?\])?>", "", xml_str,
                     flags=re.DOTALL)
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        # fallback: strip de tags à bruta
        return re.sub(r"<[^>]+>", " ", xml_str).strip()

    partes = []
    _coletar(root, partes, ignorar=False)
    texto = "\n".join(partes)
    # colapsa múltiplos espaços mas preserva quebras de linha
    texto = re.sub(r"[^\S\n]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _coletar(elem, partes: list, ignorar: bool):
    """Percorre a árvore TEI e colecta texto."""
    nome = _tag(elem)
    if nome in _IGNORAR_TAGS:
        # ainda processa o tail (texto que vem a seguir na árvore pai)
        if elem.tail and elem.tail.strip():
            partes.append(elem.tail.strip())
        return

    if elem.text and elem.text.strip():
        partes.append(elem.text.strip())

    for child in elem:
        _coletar(child, partes, ignorar)

    # depois de um elemento de linha/parágrafo, adiciona quebra
    if nome in ("l", "lb", "p", "ab", "div", "div1", "div2", "div3"):
        if partes and partes[-1] != "":
            partes.append("")

    if elem.tail and elem.tail.strip():
        partes.append(elem.tail.strip())


# ── catálogo ──────────────────────────────────────────────────────────────────

def _cache_path(lingua: str) -> Path:
    return CACHE_DIR / f"perseus_catalogo_{lingua}.json"


def obter_catalogo(lingua: str = "grc", forcar: bool = False) -> list[dict]:
    """
    Retorna lista de dicts com obras disponíveis na língua indicada.
    Cada dict: {display, autor, obra, edicao_urn, lingua}
    lingua: 'grc' | 'lat'
    """
    cp = _cache_path(lingua)
    if not forcar and cp.exists():
        if time.time() - cp.stat().st_mtime < CATALOG_TTL:
            try:
                return json.loads(cp.read_text(encoding="utf-8"))
            except Exception:
                pass

    xml_str = _get({"request": "GetCapabilities"}, timeout=TIMEOUT_CAT)
    # Remove DTD
    xml_str = re.sub(r"<!DOCTYPE[^>]*(?:\[.*?\])?>", "", xml_str,
                     flags=re.DOTALL)
    root = ET.fromstring(xml_str)

    obras = []
    for tg in root.iter():
        if _tag(tg) != "textgroup":
            continue

        autor_urn = tg.get("urn", "")
        autor = next(
            ((c.text or "").strip() for c in tg if _tag(c) == "groupname"),
            autor_urn,
        )

        for work in tg:
            if _tag(work) != "work":
                continue

            obra_urn = work.get("urn", "")
            titulo = next(
                ((c.text or "").strip() for c in work if _tag(c) == "title"),
                obra_urn,
            )

            for ed in work:
                if _tag(ed) not in ("edition", "translation"):
                    continue
                ed_urn = ed.get("urn", "")

                # língua da edição
                ed_lingua = ed.get(XML_LANG, "")
                if not ed_lingua:
                    # heurística pelo URN: ...perseus-grc2 → grc
                    m = re.search(r"perseus-([a-z]{2,3})\d*$", ed_urn)
                    ed_lingua = m.group(1) if m else ""

                # filtrar língua — aceita só originais (grc / lat)
                if lingua == "grc" and ed_lingua != "grc":
                    continue
                if lingua == "lat" and ed_lingua != "lat":
                    continue

                obras.append({
                    "display":    f"{autor} — {titulo}",
                    "autor":      autor,
                    "obra":       titulo,
                    "edicao_urn": ed_urn,
                    "lingua":     ed_lingua,
                })

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(obras, indent=2, ensure_ascii=False),
                  encoding="utf-8")
    return obras


def buscar_obras(query: str, lingua: str = "grc") -> list[dict]:
    """Filtra o catálogo por autor ou obra (case-insensitive)."""
    cat = obter_catalogo(lingua)
    q = query.lower()
    return [o for o in cat if q in o["display"].lower()]


# ── referências e passagens ───────────────────────────────────────────────────

def obter_referencias(edicao_urn: str, nivel: int = 1) -> list[str]:
    """
    Devolve lista de URNs de referências de nível N (ex: livros de um poema).
    """
    xml_str = _get({"request": "GetValidReff",
                    "urn": edicao_urn, "level": nivel},
                   timeout=TIMEOUT_REF)
    xml_str = re.sub(r"<!DOCTYPE[^>]*(?:\[.*?\])?>", "", xml_str,
                     flags=re.DOTALL)
    root = ET.fromstring(xml_str)
    return [
        elem.text.strip()
        for elem in root.iter()
        if _tag(elem) == "urn" and elem.text and elem.text.strip()
        and ":" in elem.text  # exclui a linha vazia da raiz
    ]


def obter_passagem(urn: str) -> str:
    """Busca uma passagem pelo URN CTS e devolve texto limpo."""
    xml_str = _get({"request": "GetPassage", "urn": urn},
                   timeout=TIMEOUT_PAS)
    return _extrair_texto(xml_str)


def obter_obra_completa(edicao_urn: str,
                        progresso_cb=None,
                        should_stop=None,
                        workers: int = 5) -> str:
    """
    Descarrega a obra completa concatenando todas as passagens de nível 1
    em paralelo (até `workers` pedidos simultâneos).

    progresso_cb(atual, total) — chamado após cada passagem concluída.
    should_stop()              — se devolver True, cancela e devolve ''.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    refs = obter_referencias(edicao_urn, nivel=1)
    if not refs:
        return ""

    total      = len(refs)
    resultados = [None] * total

    with ThreadPoolExecutor(max_workers=workers) as exe:
        futuros = {exe.submit(obter_passagem, urn): i
                   for i, urn in enumerate(refs)}
        concluidos = 0
        for fut in as_completed(futuros):
            if should_stop and should_stop():
                return ""
            i = futuros[fut]
            try:
                resultados[i] = fut.result()
            except Exception as e:
                resultados[i] = f"[Erro — {label_referencia(refs[i])}: {e}]"
            concluidos += 1
            if progresso_cb:
                progresso_cb(concluidos, total)

    return "\n\n".join(r for r in resultados if r)


def label_referencia(urn: str) -> str:
    """Transforma 'urn:cts:...:1.2' em '1.2'."""
    return urn.rsplit(":", 1)[-1] if ":" in urn else urn
