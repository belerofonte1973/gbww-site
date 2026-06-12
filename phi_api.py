#!/usr/bin/env python3
"""PHI Latin Texts — latin.packhum.org"""

import json
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://latin.packhum.org"
_CACHE = Path.home() / ".config" / "busca_latina" / "phi"
_CAT_TTL = 7 * 86400
_TXT_TTL = 14 * 86400
_SES = requests.Session()
_SES.headers["User-Agent"] = "BuscaGrecoLatina/1.0"


def _cache_path(name: str) -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    return _CACHE / name


def obter_catalogo(forcar: bool = False) -> list:
    fp = _cache_path("catalog.json")
    if not forcar and fp.exists() and time.time() - fp.stat().st_mtime < _CAT_TTL:
        return json.loads(fp.read_text("utf-8"))

    r = _SES.get(f"{BASE}/browse", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    obras: list = []
    seen: set = set()

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        label = a.get_text(strip=True)
        if not label:
            continue
        if not (href.startswith("/author/") or href.startswith("/loc/")):
            continue
        if href in seen:
            continue
        seen.add(href)
        obras.append({"id": href, "display": label, "urn": href})

    fp.write_text(json.dumps(obras, ensure_ascii=False), "utf-8")
    return obras


def obter_texto(urn: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", urn.strip("/"))
    fp = _cache_path(safe + ".txt")
    if fp.exists() and time.time() - fp.stat().st_mtime < _TXT_TTL:
        return fp.read_text("utf-8")

    r = _SES.get(f"{BASE}{urn}", timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    # PHI serves text in specific containers — try common selectors first
    main = (soup.find("div", {"id": "main"})
            or soup.find("div", class_=re.compile(r"text|content|body", re.I))
            or soup.find("body")
            or soup)

    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    fp.write_text(text, "utf-8")
    return text
