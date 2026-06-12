#!/usr/bin/env python3
"""Latin Library Online — scraping de thelatinlibrary.com"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.thelatinlibrary.com/"
_CACHE = Path.home() / ".config" / "busca_latina" / "ll_online"
_CAT_TTL = 7 * 86400
_TXT_TTL = 30 * 86400
_SES = requests.Session()
_SES.headers["User-Agent"] = "BuscaGrecoLatina/1.0"

_SKIP_PATHS = ("index", "about", "help", "search", "contact", "disclaimer", "links", ".css", ".js", ".gif", ".png", ".jpg")


def _cache_path(name: str) -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    return _CACHE / name


def obter_catalogo(forcar: bool = False) -> list:
    fp = _cache_path("catalog.json")
    if not forcar and fp.exists() and time.time() - fp.stat().st_mtime < _CAT_TTL:
        return json.loads(fp.read_text("utf-8"))

    r = _SES.get(BASE, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    obras = []
    seen: set = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        label = a.get_text(strip=True)
        if not label or len(label) < 2:
            continue
        if not re.search(r'\.(s?html?|php)$', href, re.I):
            continue
        full_url = href if href.startswith("http") else urljoin(BASE, href)
        if "thelatinlibrary.com" not in full_url:
            continue
        path = urlparse(full_url).path.lower()
        if any(x in path for x in _SKIP_PATHS):
            continue
        if full_url in seen:
            continue
        seen.add(full_url)
        obras.append({"id": full_url, "display": label, "url": full_url})

    fp.write_text(json.dumps(obras, ensure_ascii=False), "utf-8")
    return obras


def obter_texto(url: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", urlparse(url).path.strip("/")) or "text"
    fp = _cache_path(safe + ".txt")
    if fp.exists() and time.time() - fp.stat().st_mtime < _TXT_TTL:
        return fp.read_text("utf-8")

    r = _SES.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    for tag in soup.find_all(["script", "style", "nav", "header", "footer", "img"]):
        tag.decompose()

    body = soup.find("body") or soup
    text = body.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    fp.write_text(text, "utf-8")
    return text
