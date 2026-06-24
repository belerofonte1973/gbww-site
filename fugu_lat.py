#!/usr/bin/env python3
"""
fugu_lat.py — Tradução de latim/grego/hebraico via Sakana Fugu API

Chave obtida em: console.sakana.ai
Guardada automaticamente em: ~/.codex/.env  (pelo instalador codex-fugu)
Ou manualmente:  POST /api/fugu_chave  {"chave": "fish_..."}

CLI:
  python3 fugu_lat.py "Gallia est omnis divisa in partes tres"
  python3 fugu_lat.py "ἐν ἀρχῇ ἦν ὁ λόγος" --lingua grc
  python3 fugu_lat.py "amor" --comentario
"""

import os
import json
import requests
from pathlib import Path
from typing import Iterator

SETTINGS_FILE  = Path(__file__).parent / "config" / "settings.json"
CODEX_ENV_FILE = Path.home() / ".codex" / ".env"

SAKANA_BASE_URL = "https://api.sakana.ai/v1"
MODELO_FUGU     = "fugu"

MODELOS_FUGU = [
    (MODELO_FUGU, "Fugu — rápido, multi-agente, alta qualidade"),
]
MODELO_DEFAULT = MODELO_FUGU

PROMPTS = {
    "la": (
        "És um especialista em latim clássico e língua portuguesa. "
        "Traduz o seguinte texto do latim para o português do Brasil, "
        "de forma fluente e fiel ao original. "
        "Fornece apenas a tradução, sem comentários ou explicações.\n\n"
        "Texto latino:\n{texto}\n\nTradução:"
    ),
    "grc": (
        "És um especialista em grego antigo e língua portuguesa. "
        "Traduz o seguinte texto do grego antigo para o português do Brasil, "
        "de forma fluente e fiel ao original. "
        "Fornece apenas a tradução, sem transliteração nem comentários.\n\n"
        "Texto grego:\n{texto}\n\nTradução:"
    ),
    "hbo": (
        "És um especialista em hebraico bíblico e língua portuguesa. "
        "Traduz o seguinte texto do hebraico bíblico para o português do Brasil, "
        "de forma fluente e fiel ao original. "
        "Fornece apenas a tradução, sem transliteração nem comentários.\n\n"
        "Texto hebraico:\n{texto}\n\nTradução:"
    ),
    "sux": (
        "És um especialista em sumério e língua portuguesa. "
        "Traduz o seguinte texto sumério (transliteração ATF) para o português do Brasil. "
        "Fornece apenas a tradução.\n\nTexto:\n{texto}\n\nTradução:"
    ),
    "comentario": (
        "És um professor de latim clássico. "
        "Faz um comentário filológico breve (3–5 frases) do seguinte trecho, "
        "em português do Brasil, cobrindo: estrutura gramatical, "
        "vocabulário notável e contexto literário.\n\n"
        "Trecho:\n{texto}\n\nComentário:"
    ),
    "en": (
        "Traduz o seguinte texto para o português do Brasil de forma fluente. "
        "Fornece apenas a tradução.\n\nTexto:\n{texto}\n\nTradução:"
    ),
}


# ── gestão da chave ───────────────────────────────────────────────────────────

def _ler_codex_env() -> str:
    """Lê SAKANA_API_KEY do ficheiro ~/.codex/.env (instalado pelo codex-fugu)."""
    try:
        for line in CODEX_ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("SAKANA_API_KEY="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def obter_chave() -> str:
    key = os.environ.get("SAKANA_API_KEY", "").strip()
    if key:
        return key
    key = _ler_codex_env()
    if key:
        return key
    try:
        s = json.loads(SETTINGS_FILE.read_text())
        return s.get("fugu_api_key", "").strip()
    except Exception:
        return ""


def guardar_chave(chave: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {}
    except Exception:
        s = {}
    s["fugu_api_key"] = chave.strip()
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


# ── tradução com streaming ────────────────────────────────────────────────────

def traduzir_stream(texto: str,
                    lingua: str = "la",
                    modelo: str | None = None,
                    api_key: str | None = None) -> Iterator[str]:
    chave = api_key or obter_chave()
    if not chave:
        raise ValueError("Chave Fugu não configurada. Instale o codex-fugu ou insira a chave em ⚙ → Fugu.")

    modelo  = modelo or MODELO_DEFAULT
    tmpl    = PROMPTS.get(lingua, PROMPTS["en"])
    prompt  = tmpl.format(texto=texto.strip())

    payload = {
        "model":    modelo,
        "messages": [{"role": "user", "content": prompt}],
        "stream":   True,
    }
    headers = {
        "Authorization": f"Bearer {chave}",
        "Content-Type":  "application/json",
    }

    try:
        resp = requests.post(
            f"{SAKANA_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            stream=True,
            timeout=(15, None),
        )
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if line.startswith("data: "):
                line = line[6:]
            if line == "[DONE]":
                break
            try:
                chunk = json.loads(line)
                delta = chunk["choices"][0]["delta"].get("content") or ""
                if delta:
                    yield delta
            except (KeyError, json.JSONDecodeError):
                continue
    except requests.exceptions.ConnectionError:
        yield "[Sem conexão com a Sakana API]"
    except requests.exceptions.HTTPError as e:
        yield f"[Erro HTTP {e.response.status_code}: {e.response.text[:200]}]"
    except Exception as e:
        yield f"[Erro: {e}]"


def traduzir(texto: str, lingua: str = "la", modelo: str | None = None,
             api_key: str | None = None) -> str:
    return "".join(traduzir_stream(texto, lingua, modelo, api_key))


def comentario(texto: str, modelo: str | None = None,
               api_key: str | None = None) -> str:
    return "".join(traduzir_stream(texto, "comentario", modelo, api_key))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import argparse

    ap = argparse.ArgumentParser(description="Tradução latim/grego → PT via Sakana Fugu")
    ap.add_argument("texto", nargs="?", default="")
    ap.add_argument("--lingua", "-l", default="la",
                    choices=list(PROMPTS.keys()))
    ap.add_argument("--modelo", "-m", default=MODELO_DEFAULT)
    ap.add_argument("--comentario", "-c", action="store_true")
    ap.add_argument("--guardar-chave", metavar="CHAVE")
    args = ap.parse_args()

    if args.guardar_chave:
        guardar_chave(args.guardar_chave)
        print("Chave Fugu guardada.")
        sys.exit(0)

    if not args.texto:
        ap.print_help()
        sys.exit(1)

    lingua = "comentario" if args.comentario else args.lingua
    for frag in traduzir_stream(args.texto, lingua, args.modelo):
        print(frag, end="", flush=True)
    print()
