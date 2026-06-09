#!/usr/bin/env python3
"""
cdli_api.py — Cuneiform Digital Library Initiative (CDLI)

Covers: Sumerian (sux), Akkadian (akk), Hittite (hit), Babylonian (akk),
        Elamite (elx), Hurrian (xhu), Ugaritic (uga), Egyptian (egy)

REST API: https://cdli.mpiwg-berlin.mpg.de/api/v2/
"""

import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

CDLI_BASE  = "https://cdli.mpiwg-berlin.mpg.de"
CACHE_DIR  = Path.home() / ".cache" / "busca_latina" / "cdli"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

LANG_LABELS = {
    "sux": "Sumério",
    "akk": "Acadiano / Babilónico",
    "hit": "Hitita",
    "elx": "Elamita",
    "xhu": "Hurrita",
    "uga": "Ugarítico",
    "egy": "Egípcio (hieroglífico)",
    "arc": "Aramaico",
    ""   : "Todas as línguas cuneiformes",
}


def _get(path: str, params: dict | None = None, timeout: int = 20) -> dict | list:
    url = f"{CDLI_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Classics-Reader/1.0 (research)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def pesquisar(termo: str, lang: str = "", limite: int = 50) -> list[dict]:
    """
    Search CDLI for tablets matching *termo*.

    Returns list of dicts: {id, display_name, period, provenience, genre,
                             primary_publication, lang, atf_text}
    """
    params = {"limit": limite, "page": 1}
    if termo:
        params["keyword"] = termo
    if lang:
        params["language"] = lang

    try:
        data = _get("/api/v2/artifacts", params)
        items = data if isinstance(data, list) else data.get("results", data.get("data", []))
    except Exception as ex:
        return [{"erro": str(ex)}]

    results = []
    for item in items:
        results.append({
            "id":                  item.get("id", ""),
            "display_name":        item.get("display_name") or item.get("designation", ""),
            "period":              item.get("period", ""),
            "provenience":         item.get("provenience", ""),
            "genre":               item.get("genre", ""),
            "primary_publication": item.get("primary_publication", ""),
            "lang":                item.get("primary_edition_lang", lang),
            "atf_text":            item.get("cdl", {}).get("atf", "") if isinstance(item.get("cdl"), dict) else "",
        })
    return results


def obter_artefacto(artifact_id: str) -> dict:
    """Fetch full artifact record including ATF transliteration."""
    cache_file = CACHE_DIR / f"{artifact_id}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    try:
        data = _get(f"/api/v2/artifacts/{artifact_id}")
        time.sleep(0.3)
        cache_file.write_text(json.dumps(data, ensure_ascii=False))
        return data
    except Exception as ex:
        return {"erro": str(ex)}


def obter_atf(artifact_id: str) -> str:
    """Return ATF (ASCII Transliteration Format) text for an artifact."""
    data = obter_artefacto(artifact_id)
    if "erro" in data:
        return f"[Erro: {data['erro']}]"
    cdl = data.get("cdl", {})
    if isinstance(cdl, dict):
        return cdl.get("atf", "") or data.get("atf", "") or ""
    return ""
