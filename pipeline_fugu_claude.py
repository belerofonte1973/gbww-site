#!/usr/bin/env python3
"""
pipeline_fugu_claude.py — Pipeline sequencial Claude → Fugu → Claude

Fluxo:
  1. Claude analisa o texto e define a estratégia de tradução
  2. Fugu executa a tradução
  3. Claude revê e corrige a tradução do Fugu

Uso CLI:
  python3 pipeline_fugu_claude.py "Gallia est omnis divisa in partes tres"
  python3 pipeline_fugu_claude.py "ἐν ἀρχῇ ἦν ὁ λόγος" --lingua grc
  python3 pipeline_fugu_claude.py "De bello gallico" --lingua la --verbose
"""

import sys
import argparse
import anthropic
import requests
import json
from pathlib import Path

# ── configuração ──────────────────────────────────────────────────────────────

SETTINGS_FILE  = Path(__file__).parent / "config" / "settings.json"
CODEX_ENV_FILE = Path.home() / ".codex" / ".env"

SAKANA_BASE_URL = "https://api.sakana.ai/v1"
FUGU_MODEL      = "fugu"
CLAUDE_MODEL    = "claude-haiku-4-5-20251001"

LINGUAS = {
    "la":  "latim clássico",
    "grc": "grego antigo",
    "hbo": "hebraico bíblico",
    "sux": "sumério (transliteração ATF)",
}


# ── chaves ────────────────────────────────────────────────────────────────────

def _ler_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}


def _chave_claude() -> str:
    import os
    key = os.environ.get("CLAUDE_API_KEY", "").strip()
    if key:
        return key
    return _ler_settings().get("claude_api_key", "").strip()


def _chave_fugu() -> str:
    import os
    key = os.environ.get("SAKANA_API_KEY", "").strip()
    if key:
        return key
    try:
        for line in CODEX_ENV_FILE.read_text().splitlines():
            if line.strip().startswith("SAKANA_API_KEY="):
                return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return _ler_settings().get("fugu_api_key", "").strip()


# ── passo 1: Claude analisa e define estratégia ───────────────────────────────

def claude_planear(texto: str, lingua: str, claude_key: str) -> str:
    nome_lingua = LINGUAS.get(lingua, lingua)
    prompt = (
        f"Analisa o seguinte texto em {nome_lingua} e fornece:\n"
        f"1. Dificuldades de tradução (construções sintáticas complexas, hapax legomena, ambiguidades)\n"
        f"2. Contexto histórico-literário relevante (máx. 2 frases)\n"
        f"3. Instruções específicas para o tradutor (tom, equivalências de termos técnicos, etc.)\n\n"
        f"Texto:\n{texto}\n\n"
        f"Responde em português, de forma concisa (máx. 150 palavras)."
    )
    client = anthropic.Anthropic(api_key=claude_key)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


# ── passo 2: Fugu traduz com base na análise ──────────────────────────────────

def fugu_traduzir(texto: str, lingua: str, analise: str, fugu_key: str) -> str:
    nome_lingua = LINGUAS.get(lingua, lingua)
    prompt = (
        f"És um especialista em {nome_lingua} e língua portuguesa.\n\n"
        f"Análise prévia do texto:\n{analise}\n\n"
        f"Com base nesta análise, traduz o seguinte texto para o português do Brasil "
        f"de forma fluente e fiel ao original. Fornece apenas a tradução.\n\n"
        f"Texto:\n{texto}\n\nTradução:"
    )
    headers = {
        "Authorization": f"Bearer {fugu_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":    FUGU_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream":   False,
    }
    resp = requests.post(
        f"{SAKANA_BASE_URL}/chat/completions",
        json=payload,
        headers=headers,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── passo 3: Claude revê a tradução do Fugu ───────────────────────────────────

def claude_rever(original: str, traducao_fugu: str, lingua: str,
                 analise: str, claude_key: str) -> str:
    nome_lingua = LINGUAS.get(lingua, lingua)
    prompt = (
        f"Revê a seguinte tradução de {nome_lingua} para português do Brasil.\n\n"
        f"Texto original:\n{original}\n\n"
        f"Análise prévia:\n{analise}\n\n"
        f"Tradução a rever:\n{traducao_fugu}\n\n"
        f"Identifica e corrige erros de tradução, imprecisões ou soluções menos felizes. "
        f"Se a tradução estiver correcta, devolve-a sem alterações. "
        f"Fornece apenas a tradução final, sem comentários."
    )
    client = anthropic.Anthropic(api_key=claude_key)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


# ── pipeline completo ─────────────────────────────────────────────────────────

def pipeline(texto: str, lingua: str = "la", verbose: bool = False) -> dict:
    claude_key = _chave_claude()
    fugu_key   = _chave_fugu()

    if not claude_key:
        raise ValueError("Chave Claude não encontrada. Configure em config/settings.json → 'claude_api_key'.")
    if not fugu_key:
        raise ValueError("Chave Fugu não encontrada. Instale o codex-fugu ou configure 'fugu_api_key'.")

    if verbose:
        print(f"[1/3] Claude a analisar ({CLAUDE_MODEL})...", flush=True)
    analise = claude_planear(texto, lingua, claude_key)

    if verbose:
        print(f"\n── Análise ──────────────────────────────\n{analise}\n")
        print(f"[2/3] Fugu a traduzir ({FUGU_MODEL})...", flush=True)
    traducao_fugu = fugu_traduzir(texto, lingua, analise, fugu_key)

    if verbose:
        print(f"\n── Tradução Fugu ─────────────────────────\n{traducao_fugu}\n")
        print(f"[3/3] Claude a rever ({CLAUDE_MODEL})...", flush=True)
    traducao_final = claude_rever(texto, traducao_fugu, lingua, analise, claude_key)

    return {
        "original":      texto,
        "lingua":        lingua,
        "analise":       analise,
        "traducao_fugu": traducao_fugu,
        "traducao_final": traducao_final,
    }


# ── rota Flask (opcional — integração no app.py) ──────────────────────────────

def registar_rota(app):
    """Chama registar_rota(app) em app.py para expor /api/pipeline."""
    from flask import request, jsonify

    @app.route('/api/pipeline', methods=['POST'])
    def api_pipeline():
        data   = request.get_json(force=True, silent=True) or {}
        texto  = (data.get('texto') or '').strip()
        lingua = data.get('lingua', 'la')
        if not texto:
            return jsonify({'erro': 'Texto vazio'}), 400
        try:
            resultado = pipeline(texto, lingua, verbose=False)
            return jsonify(resultado)
        except ValueError as e:
            return jsonify({'erro': str(e)}), 503
        except Exception as e:
            return jsonify({'erro': str(e)}), 500


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Pipeline sequencial Claude → Fugu → Claude para tradução de textos clássicos"
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
    else:
        if not args.verbose:
            print(resultado["traducao_final"])
        else:
            print(f"\n── Tradução Final ────────────────────────\n{resultado['traducao_final']}")
