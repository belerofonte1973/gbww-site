#!/usr/bin/env python3
"""
pipeline_fugu_claude.py — Pipeline sequencial Fugu × 3

Fluxo:
  1. Fugu analisa o texto e define a estratégia de tradução
  2. Fugu executa a tradução com base na análise
  3. Fugu revê e corrige a própria tradução

Uso CLI:
  python3 pipeline_fugu_claude.py "Gallia est omnis divisa in partes tres"
  python3 pipeline_fugu_claude.py "ἐν ἀρχῇ ἦν ὁ λόγος" --lingua grc
  python3 pipeline_fugu_claude.py "De bello gallico" --lingua la --verbose
  python3 pipeline_fugu_claude.py "Arma virumque cano" --json
"""

import sys
import argparse
import requests
import json
import os
from pathlib import Path

# ── configuração ──────────────────────────────────────────────────────────────

SETTINGS_FILE  = Path(__file__).parent / "config" / "settings.json"
CODEX_ENV_FILE = Path.home() / ".codex" / ".env"

SAKANA_BASE_URL = "https://api.sakana.ai/v1"
FUGU_MODEL      = "fugu"

LINGUAS = {
    "la":  "latim clássico",
    "grc": "grego antigo",
    "hbo": "hebraico bíblico",
    "sux": "sumério (transliteração ATF)",
}


# ── chave ─────────────────────────────────────────────────────────────────────

def _chave_fugu() -> str:
    key = os.environ.get("SAKANA_API_KEY", "").strip()
    if key:
        return key
    try:
        for line in CODEX_ENV_FILE.read_text().splitlines():
            if line.strip().startswith("SAKANA_API_KEY="):
                return line.strip().split("=", 1)[1]
    except OSError:
        pass
    try:
        return json.loads(SETTINGS_FILE.read_text()).get("fugu_api_key", "").strip()
    except Exception:
        return ""


# ── chamada à API ─────────────────────────────────────────────────────────────

def _fugu(prompt: str, chave: str, max_tokens: int = 1024) -> str:
    resp = requests.post(
        f"{SAKANA_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        json={"model": FUGU_MODEL, "messages": [{"role": "user", "content": prompt}],
              "stream": False, "max_tokens": max_tokens},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── passos do pipeline ────────────────────────────────────────────────────────

def fugu_planear(texto: str, lingua: str, chave: str) -> str:
    nome_lingua = LINGUAS.get(lingua, lingua)
    return _fugu(
        f"Analisa o seguinte texto em {nome_lingua} e fornece:\n"
        f"1. Dificuldades de tradução (construções sintáticas complexas, hapax legomena, ambiguidades)\n"
        f"2. Contexto histórico-literário relevante (máx. 2 frases)\n"
        f"3. Instruções específicas para o tradutor (tom, equivalências de termos técnicos, etc.)\n\n"
        f"Texto:\n{texto}\n\n"
        f"Responde em português, de forma concisa (máx. 150 palavras).",
        chave, max_tokens=512,
    )


def fugu_traduzir(texto: str, lingua: str, analise: str, chave: str) -> str:
    nome_lingua = LINGUAS.get(lingua, lingua)
    return _fugu(
        f"És um especialista em {nome_lingua} e língua portuguesa.\n\n"
        f"Análise prévia do texto:\n{analise}\n\n"
        f"Com base nesta análise, traduz o seguinte texto para o português do Brasil "
        f"de forma fluente e fiel ao original. Fornece apenas a tradução.\n\n"
        f"Texto:\n{texto}\n\nTradução:",
        chave,
    )


def fugu_rever(original: str, traducao: str, lingua: str, analise: str, chave: str) -> str:
    nome_lingua = LINGUAS.get(lingua, lingua)
    return _fugu(
        f"Revê a seguinte tradução de {nome_lingua} para português do Brasil.\n\n"
        f"Texto original:\n{original}\n\n"
        f"Análise prévia:\n{analise}\n\n"
        f"Tradução a rever:\n{traducao}\n\n"
        f"Identifica e corrige erros de tradução, imprecisões ou soluções menos felizes. "
        f"Se a tradução estiver correcta, devolve-a sem alterações. "
        f"Fornece apenas a tradução final, sem comentários.",
        chave,
    )


# ── pipeline completo ─────────────────────────────────────────────────────────

def pipeline(texto: str, lingua: str = "la", verbose: bool = False) -> dict:
    chave = _chave_fugu()
    if not chave:
        raise ValueError("Chave Fugu não encontrada. Instale o codex-fugu ou configure 'fugu_api_key'.")

    if verbose:
        print(f"[1/3] Fugu a analisar...", flush=True)
    analise = fugu_planear(texto, lingua, chave)

    if verbose:
        print(f"\n── Análise ──────────────────────────────\n{analise}\n")
        print(f"[2/3] Fugu a traduzir...", flush=True)
    traducao_fugu = fugu_traduzir(texto, lingua, analise, chave)

    if verbose:
        print(f"\n── Tradução ──────────────────────────────\n{traducao_fugu}\n")
        print(f"[3/3] Fugu a rever...", flush=True)
    traducao_final = fugu_rever(texto, traducao_fugu, lingua, analise, chave)

    return {
        "original":       texto,
        "lingua":         lingua,
        "analise":        analise,
        "traducao_fugu":  traducao_fugu,
        "traducao_final": traducao_final,
    }


# ── rota Flask (opcional — integração no app.py) ──────────────────────────────

def registar_rota(app):
    from flask import request, jsonify

    @app.route('/api/pipeline', methods=['POST'])
    def api_pipeline():
        data   = request.get_json(force=True, silent=True) or {}
        texto  = (data.get('texto') or '').strip()
        lingua = data.get('lingua', 'la')
        if not texto:
            return jsonify({'erro': 'Texto vazio'}), 400
        try:
            return jsonify(pipeline(texto, lingua))
        except ValueError as e:
            return jsonify({'erro': str(e)}), 503
        except Exception as e:
            return jsonify({'erro': str(e)}), 500


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Pipeline Fugu × 3: análise → tradução → revisão"
    )
    ap.add_argument("texto", nargs="+")
    ap.add_argument("--lingua", "-l", default="la", choices=list(LINGUAS.keys()))
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="Mostra cada passo do pipeline")
    ap.add_argument("--json", action="store_true",
                    help="Saída em JSON (inclui análise e tradução intermédia)")
    args = ap.parse_args()

    texto = " ".join(args.texto)
    try:
        resultado = pipeline(texto, args.lingua, verbose=args.verbose)
    except ValueError as e:
        print(f"Erro: {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    elif args.verbose:
        print(f"\n── Tradução Final ────────────────────────\n{resultado['traducao_final']}")
    else:
        print(resultado["traducao_final"])
