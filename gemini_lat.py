#!/usr/bin/env python3
"""
gemini_lat.py — Tradução de latim/grego para português via API Gemini (Google)

Usa a API REST do Gemini com streaming — sem SDK, apenas requests.
Chave gratuita em: aistudio.google.com  (15 req/min, 1500/dia)

Configuração da chave:
  1. Variável de ambiente:  export GEMINI_API_KEY="AIza..."
  2. Ficheiro de config:    ~/.config/busca_latina/settings.json → "gemini_api_key": "..."

CLI:
  python3 gemini_lat.py "Gallia est omnis divisa in partes tres"
  python3 gemini_lat.py "amor" --comentario
  python3 gemini_lat.py --guardar-chave "AIza..."
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Iterator

SETTINGS_FILE = Path.home() / ".config" / "busca_latina" / "settings.json"

MODELOS_GEMINI = [
    ("gemini-2.5-flash",       "Flash 2.5  — melhor qualidade, gratuito"),
    ("gemini-2.5-pro",         "Pro 2.5    — máxima qualidade (limite baixo)"),
]
MODELO_DEFAULT = "gemini-2.5-flash"

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

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
    "comentario": (
        "És um professor de latim clássico. "
        "Faz um comentário filológico breve (3–5 frases) do seguinte trecho, "
        "em português do Brasil, cobrindo: estrutura gramatical, "
        "vocabulário notável e contexto literário.\n\n"
        "Trecho:\n{texto}\n\nComentário:"
    ),
}


# ── gestão da chave ───────────────────────────────────────────────────────────

def obter_chave() -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        s = json.loads(SETTINGS_FILE.read_text())
        return s.get("gemini_api_key", "").strip() or None
    except Exception:
        return None


def guardar_chave(chave: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        s = json.loads(SETTINGS_FILE.read_text())
    except Exception:
        s = {}
    s["gemini_api_key"] = chave.strip()
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False))


# ── tradução com streaming ────────────────────────────────────────────────────

def traduzir_stream(texto: str,
                    lingua: str = "la",
                    modelo: str = MODELO_DEFAULT,
                    api_key: str | None = None,
                    should_stop=None) -> Iterator[str]:
    """
    Traduz via Gemini com streaming (API REST, sem SDK).
    Yield: fragmentos de texto à medida que chegam.
    """
    key = api_key or obter_chave()
    if not key:
        yield "[Chave API Gemini não configurada. Obtenha em aistudio.google.com]"
        return

    prompt_tmpl = PROMPTS.get(lingua, PROMPTS["la"])
    prompt = prompt_tmpl.format(texto=texto.strip())

    url = f"{_BASE}/{modelo}:streamGenerateContent?key={key}&alt=sse"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 65536},
    }

    _MAX_RETRIES = 4

    def _parse_429(body: dict) -> tuple[int, bool]:
        """Devolve (segundos_a_esperar, é_limite_diário)."""
        err = body.get("error", {})
        details = err.get("details", [])
        diario = any(
            "PerDay" in v.get("quotaId", "")
            for d in details if d.get("@type", "").endswith("QuotaFailure")
            for v in d.get("violations", [])
        )
        espera = 30  # fallback
        for d in details:
            if d.get("@type", "").endswith("RetryInfo"):
                raw = d.get("retryDelay", "")
                try:
                    espera = int(raw.rstrip("s")) + 2
                except ValueError:
                    pass
        return espera, diario

    for tentativa in range(_MAX_RETRIES):
        try:
            with requests.post(url, json=payload, stream=True,
                               timeout=(10, None)) as resp:
                if resp.status_code == 400:
                    err = resp.json().get("error", {})
                    if "API key" in err.get("message", ""):
                        yield "[Chave API Gemini inválida. Verifique as definições.]"
                    else:
                        yield f"[Erro Gemini: {err.get('message', resp.text[:100])}]"
                    return
                if resp.status_code == 429:
                    try:
                        body = resp.json()
                    except Exception:
                        body = {}
                    espera, diario = _parse_429(body)
                    if diario:
                        yield "[Quota diária Gemini esgotada. Tente novamente amanhã.]"
                        return
                    if tentativa < _MAX_RETRIES - 1:
                        # \x01retry: é interpretado pelo GeminiThread como mensagem de estado
                        yield f"\x01retry:Limite de taxa Gemini. A tentar novamente em {espera}s… ({tentativa+1}/{_MAX_RETRIES-1})"
                        for _ in range(espera):
                            if should_stop and should_stop():
                                return
                            time.sleep(1)
                        continue
                    yield "[Limite de taxa Gemini excedido. Aguarde alguns minutos e tente novamente.]"
                    return
                resp.raise_for_status()

                for line in resp.iter_lines():
                    if not line:
                        continue
                    raw = line.decode("utf-8") if isinstance(line, bytes) else line
                    if not raw.startswith("data:"):
                        continue
                    data_str = raw[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        for cand in chunk.get("candidates", []):
                            for part in cand.get("content", {}).get("parts", []):
                                txt = part.get("text", "")
                                if txt:
                                    yield txt
                    except (json.JSONDecodeError, KeyError):
                        pass
                return  # sucesso

        except requests.exceptions.ConnectionError:
            yield "[Sem ligação à API Gemini. Verifique a internet.]"
            return
        except Exception as e:
            yield f"[Erro Gemini: {e}]"
            return


def traduzir(texto: str,
             lingua: str = "la",
             modelo: str = MODELO_DEFAULT,
             api_key: str | None = None) -> str:
    return "".join(traduzir_stream(texto, lingua, modelo, api_key))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(description="Tradução latim/grego → PT via Gemini")
    ap.add_argument("texto", nargs="*")
    ap.add_argument("--lingua", "-l", default="la", choices=["la", "grc"])
    ap.add_argument("--modelo", "-m", default=MODELO_DEFAULT)
    ap.add_argument("--comentario", "-c", action="store_true")
    ap.add_argument("--guardar-chave", metavar="KEY")
    args = ap.parse_args()

    if args.guardar_chave:
        guardar_chave(args.guardar_chave)
        print("Chave guardada em", SETTINGS_FILE)
        sys.exit(0)

    if not args.texto:
        ap.print_help()
        sys.exit(1)

    lingua = "comentario" if args.comentario else args.lingua
    texto  = " ".join(args.texto)
    print(f"[Gemini {args.modelo}]\n")
    for frag in traduzir_stream(texto, lingua, args.modelo):
        print(frag, end="", flush=True)
    print()
