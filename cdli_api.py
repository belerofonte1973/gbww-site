#!/usr/bin/env python3
"""
cdli_api.py — Cuneiform Digital Library Initiative (CDLI)

Covers: Sumerian (sux), Akkadian (akk), Hittite (hit), Babylonian (akk),
        Elamite (elx), Hurrian (xhu), Ugaritic (uga), Egyptian (egy)

API: https://cdli.earth/search?q=...&limit=N&primary_edition_lang=sux
"""

import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

CDLI_BASE  = "https://cdli.earth"
CACHE_DIR  = Path.home() / ".cache" / "busca_latina" / "cdli"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LANG_LABELS = {
    "sux": "Sumério",
    "akk": "Acadiano / Babilônico",
    "hit": "Hitita",
    "elx": "Elamita",
    "xhu": "Hurrita",
    "uga": "Ugarítico",
    "egy": "Egípcio (hieroglífico)",
    "arc": "Aramaico",
    ""   : "Todas as línguas cuneiformes",
}

# Obras notáveis para navegação rápida
OBRAS_NOTAVEIS = [
    {"nome": "Epopeia de Gilgamesh",       "q": "Gilgamesh",       "lang": "akk"},
    {"nome": "Enuma Elish (Criação)",       "q": "Enuma Elish",     "lang": "akk"},
    {"nome": "Mito de Atrahasis",           "q": "Atrahasis",       "lang": "akk"},
    {"nome": "Descida de Inanna",           "q": "Inanna",          "lang": "sux"},
    {"nome": "Hino a Nanna (Ur)",           "q": "Nanna",           "lang": "sux"},
    {"nome": "Código de Hamurábi",          "q": "Hammurabi",       "lang": "akk"},
    {"nome": "Lamento pela Destruição de Ur","q": "Lamentation Ur", "lang": "sux"},
    {"nome": "Lendas de Sargão de Acádia",  "q": "Sargon",         "lang": "akk"},
    {"nome": "Textos de Tutmósis (hitita)", "q": "Hattusa",         "lang": "hit"},
    {"nome": "Tratado de Kadesh",           "q": "Kadesh",          "lang": "hit"},
    {"nome": "Anais de Assurbanipal",       "q": "Assurbanipal",    "lang": "akk"},
    {"nome": "Textos elamitas de Persépolis","q": "Persepolis",     "lang": "elx"},
]


def _get(path: str, params: dict | None = None, timeout: int = 20) -> dict | list:
    url = f"{CDLI_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v != ""})
    req = urllib.request.Request(url, headers={
        "User-Agent": "Classics-Reader/1.0 (research)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _pnum(artifact_id: str | int) -> str:
    """Converte ID numérico para número P (ex.: 1 → P000001)."""
    try:
        return f"P{int(artifact_id):06d}"
    except (ValueError, TypeError):
        return str(artifact_id)


def _parse_item(item: dict, lang_filter: str = "") -> dict:
    inscription = item.get("inscription") or {}
    atf = inscription.get("atf", "") or ""
    artifact_id = str(item.get("id", ""))
    pnum = _pnum(artifact_id)
    return {
        "id":                  artifact_id,
        "pnum":                pnum,
        "url_cdli":            f"{CDLI_BASE}/artifacts/{artifact_id}",
        "display_name":        item.get("designation") or pnum,
        "period":              (item.get("period") or {}).get("name", "") if isinstance(item.get("period"), dict) else str(item.get("period", "") or ""),
        "provenience":         (item.get("provenience") or {}).get("name", "") if isinstance(item.get("provenience"), dict) else str(item.get("provenience", "") or ""),
        "genre":               _first_name(item.get("genres")),
        "primary_publication": item.get("primary_publication", "") or "",
        "lang":                lang_filter or _first_lang(item.get("languages")),
        "atf_text":            atf,
    }


def _first_name(lst) -> str:
    if not lst:
        return ""
    first = lst[0] if isinstance(lst, list) else lst
    if isinstance(first, dict):
        return first.get("name", "") or first.get("genre", "") or first.get("designation", "")
    return str(first)


def _first_lang(lst) -> str:
    if not lst:
        return ""
    first = lst[0] if isinstance(lst, list) else lst
    if isinstance(first, dict):
        lang = first.get("language") or {}
        return (lang.get("inline_code") or lang.get("language", "")) if isinstance(lang, dict) else str(lang)
    return ""


def pesquisar(termo: str, lang: str = "", limite: int = 50) -> list[dict]:
    """
    Pesquisa no CDLI por tabletes que correspondam a *termo*.
    Retorna lista de dicts.
    """
    params: dict = {"limit": limite}
    if termo:
        params["q"] = termo
    if lang:
        params["primary_edition_lang"] = lang

    try:
        data = _get("/search", params)
        items = data if isinstance(data, list) else []
    except Exception as ex:
        return [{"erro": str(ex)}]

    return [_parse_item(item, lang) for item in items]


def obter_artefato(artifact_id: str) -> dict:
    """Busca registro completo do artefato incluindo transliteração ATF."""
    cache_file = CACHE_DIR / f"{artifact_id}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    try:
        data = _get(f"/artifacts/{artifact_id}")
        item = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
        time.sleep(0.3)
        cache_file.write_text(json.dumps(item, ensure_ascii=False))
        return item
    except Exception as ex:
        return {"erro": str(ex)}


def obter_atf(artifact_id: str) -> str:
    """Retorna o texto ATF (ASCII Transliteration Format) de um artefato."""
    data = obter_artefato(artifact_id)
    if "erro" in data:
        return f"[Erro: {data['erro']}]"
    insc = data.get("inscription") or {}
    return insc.get("atf", "") or ""
