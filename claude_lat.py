#!/usr/bin/env python3
"""
claude_lat.py — Tradução de latim/grego/hebraico via Anthropic Claude API

Chave gratuita não existe; obter em: console.anthropic.com
Guardar chave: POST /api/claude_chave  {"chave": "sk-ant-..."}

CLI:
  python3 claude_lat.py "Gallia est omnis divisa in partes tres"
  python3 claude_lat.py "ἐν ἀρχῇ ἦν ὁ λόγος" --lingua grc
"""

import os
import sys
import json
from pathlib import Path
from typing import Iterator

import anthropic

SETTINGS_FILE = Path(__file__).parent / "config" / "settings.json"

MODELOS_CLAUDE = [
    ("claude-haiku-4-5-20251001", "Haiku 4.5  — rápido, económico"),
    ("claude-sonnet-4-6",         "Sonnet 4.6 — melhor qualidade"),
]
MODELO_DEFAULT = "claude-haiku-4-5-20251001"

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

def obter_chave() -> str:
    key = os.environ.get("CLAUDE_API_KEY", "").strip()
    if key:
        return key
    try:
        s = json.loads(SETTINGS_FILE.read_text())
        return s.get("claude_api_key", "").strip() or ""
    except Exception:
        return ""


def guardar_chave(chave: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {}
    except Exception:
        s = {}
    s["claude_api_key"] = chave.strip()
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2))


# ── tradução com streaming ────────────────────────────────────────────────────

def traduzir_stream(texto: str, lingua: str = "la",
                    modelo: str | None = None,
                    api_key: str | None = None) -> Iterator[str]:
    chave = api_key or obter_chave()
    if not chave:
        raise ValueError("Chave Claude não configurada. Insira a chave em ⚙ → Claude.")

    modelo  = modelo or MODELO_DEFAULT
    tmpl    = PROMPTS.get(lingua, PROMPTS["en"])
    prompt  = tmpl.format(texto=texto.strip())
    client  = anthropic.Anthropic(api_key=chave)

    with client.messages.stream(
        model=modelo,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for fragment in stream.text_stream:
            yield fragment


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("texto", nargs="?", default="")
    ap.add_argument("--lingua", "-l", default="la",
                    choices=list(PROMPTS.keys()))
    ap.add_argument("--modelo", "-m", default=MODELO_DEFAULT)
    ap.add_argument("--guardar-chave", metavar="CHAVE")
    args = ap.parse_args()

    if args.guardar_chave:
        guardar_chave(args.guardar_chave)
        print("Chave Claude guardada.")
        sys.exit(0)

    if not args.texto:
        ap.print_help(); sys.exit(1)

    for frag in traduzir_stream(args.texto, args.lingua, args.modelo):
        print(frag, end="", flush=True)
    print()
