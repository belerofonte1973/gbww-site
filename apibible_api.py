"""API.Bible wrapper — textos hebraicos (requer chave gratuita de scripture.api.bible)"""
import json
import re
import time
from pathlib import Path

import requests

BASE   = "https://api.scripture.api.bible/v1"
_CACHE = Path.home() / ".config" / "busca_latina"
_TTL   = 7 * 86400
_SES   = requests.Session()


# ── chave ──────────────────────────────────────────────────────────────────────

def _chave_path() -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    return _CACHE / "apibible_chave.txt"

def obter_chave() -> str:
    p = _chave_path()
    return p.read_text().strip() if p.exists() else ""

def guardar_chave(chave: str):
    _chave_path().write_text(chave.strip())


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

def _hdrs() -> dict:
    return {"api-key": obter_chave()}

def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


# ── Bíblias disponíveis ────────────────────────────────────────────────────────

def listar_biblias_heb(forcar: bool = False) -> list:
    """Bíblias em hebraico bíblico (hbo) disponíveis na conta do utilizador."""
    key = "apibible_biblias_heb.json"
    if not forcar and (c := _load(key)) is not None:
        return c
    r = _SES.get(f"{BASE}/bibles", params={"language": "hbo"},
                 headers=_hdrs(), timeout=15)
    r.raise_for_status()
    bibles = r.json().get("data", [])
    result = [{"id": b["id"], "nome": b["name"],
               "descricao": b.get("description", "")} for b in bibles]
    _save(key, result)
    return result


# ── livros ─────────────────────────────────────────────────────────────────────

def listar_livros(biblia_id: str, forcar: bool = False) -> list:
    key = f"apibible_livros_{biblia_id}.json"
    if not forcar and (c := _load(key)) is not None:
        return c
    r = _SES.get(f"{BASE}/bibles/{biblia_id}/books",
                 headers=_hdrs(), timeout=15)
    r.raise_for_status()
    books = r.json().get("data", [])
    result = [{"id": b["id"], "nome": b["name"],
               "abrev": b.get("abbreviation", "")} for b in books]
    _save(key, result)
    return result


# ── capítulos ──────────────────────────────────────────────────────────────────

def listar_capitulos(biblia_id: str, livro_id: str, forcar: bool = False) -> list:
    key = f"apibible_caps_{biblia_id}_{livro_id}.json"
    if not forcar and (c := _load(key)) is not None:
        return c
    r = _SES.get(f"{BASE}/bibles/{biblia_id}/books/{livro_id}/chapters",
                 headers=_hdrs(), timeout=15)
    r.raise_for_status()
    caps = r.json().get("data", [])
    result = [{"id": c["id"], "numero": c.get("number", c["id"])} for c in caps]
    _save(key, result)
    return result


# ── passagem ───────────────────────────────────────────────────────────────────

def obter_passagem(biblia_id: str, passagem_id: str) -> dict:
    r = _SES.get(
        f"{BASE}/bibles/{biblia_id}/passages/{passagem_id}",
        params={"content-type": "text", "include-verse-numbers": "true",
                "include-chapter-numbers": "false"},
        headers=_hdrs(), timeout=15,
    )
    r.raise_for_status()
    d = r.json().get("data", {})
    texto = _strip_html(d.get("content", ""))
    return {
        "texto":     texto,
        "ref":       d.get("reference", passagem_id),
        "copyright": d.get("copyright", ""),
    }
