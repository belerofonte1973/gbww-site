"""Sefaria API — textos hebraicos sem autenticação"""
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

BASE   = "https://www.sefaria.org/api"
_CACHE = Path.home() / ".config" / "busca_latina"
_TTL   = 7 * 86400
_SES   = requests.Session()
_SES.headers["User-Agent"] = "BuscaGrecoLatina/1.0"

CATEGORIAS = [
    "Tanakh", "Talmud", "Midrash", "Halakhah", "Liturgy", "Jewish Thought",
]


# ── cache ──────────────────────────────────────────────────────────────────────

def _cp(name: str) -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    return _CACHE / name

def _load(name: str):
    p = _cp(name)
    if p.exists() and time.time() - p.stat().st_mtime < _TTL:
        return json.loads(p.read_text("utf-8"))
    return None

def _save(name: str, data):
    _cp(name).write_text(json.dumps(data, ensure_ascii=False), "utf-8")


# ── utilitário ─────────────────────────────────────────────────────────────────

def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


# ── catálogo ───────────────────────────────────────────────────────────────────

def obter_catalogo(categoria: str = "Tanakh", forcar: bool = False) -> list:
    """Devolve lista de {titulo, titulo_heb, categoria, display}."""
    key = f"sefaria_cat_{categoria.replace(' ', '_')}.json"
    if not forcar and (c := _load(key)) is not None:
        return c

    r = _SES.get(f"{BASE}/index", timeout=30)
    r.raise_for_status()

    obras = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if "title" in node and "heTitle" in node:
            node_cats = node.get("categories", [])
            if not categoria or categoria in node_cats:
                obras.append({
                    "titulo":     node["title"],
                    "titulo_heb": node.get("heTitle", ""),
                    "categoria":  " > ".join(node_cats),
                    "display":    f"{node.get('heTitle', '')}  ({node['title']})",
                })
            return
        for child in node.get("contents", []):
            walk(child)

    for entry in r.json():
        walk(entry)

    _save(key, obras)
    return obras


# ── referências (capítulos/secções) ───────────────────────────────────────────

def obter_refs(titulo: str) -> list:
    """Devolve lista de referências tipo ['Genesis 1', 'Genesis 2', ...]."""
    r = _SES.get(f"{BASE}/shape/{quote(titulo)}", timeout=15)
    r.raise_for_status()
    shape = r.json()
    if isinstance(shape, list):
        shape = shape[0] if shape else {}
    n = shape.get("length", 0)
    return [f"{titulo} {i + 1}" for i in range(n)]


# ── passagem ───────────────────────────────────────────────────────────────────

def obter_passagem(ref: str) -> dict:
    """Devolve {texto_heb, texto_en, ref, ref_heb}."""
    r = _SES.get(f"{BASE}/texts/{quote(ref)}", params={"pad": 0}, timeout=15)
    r.raise_for_status()
    d = r.json()

    def _fmt(verses):
        lines = []
        for i, v in enumerate(verses):
            if isinstance(v, list):
                v = " ".join(_strip_html(x) for x in v if isinstance(x, str))
            elif isinstance(v, str):
                v = _strip_html(v)
            if v:
                lines.append(f"{i + 1}. {v}")
        return "\n".join(lines)

    return {
        "texto_heb": _fmt(d.get("he",   [])),
        "texto_en":  _fmt(d.get("text", [])),
        "ref":       d.get("ref",   ref),
        "ref_heb":   d.get("heRef", ""),
    }
