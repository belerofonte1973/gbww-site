#!/usr/bin/env python3
"""
ollama_lat.py — Tradução de latim/grego para português com IA local (Ollama)

Requer:
  • Ollama instalado e a correr:  ollama serve
  • Um modelo descarregado, ex:  ollama pull llama3.2

Uso CLI:
  python3 ollama_lat.py "Gallia est omnis divisa in partes tres"
  python3 ollama_lat.py "μῆνιν ἄειδε θεά" --lingua grc
  python3 ollama_lat.py --modelo mistral "Arma virumque cano"
  python3 ollama_lat.py --listar
"""

import json
import requests
from typing import Iterator

OLLAMA_URL = "http://localhost:11434"


# Modelos recomendados para tradução de latim/grego (do mais leve ao melhor)
MODELOS_RECOMENDADOS = [
    ("phi3",       "Phi-3 Mini 3.8B  — rápido, leve"),
    ("llama3.1",   "Llama 3.1 8B     — excelente qualidade"),
    ("gemma2",     "Gemma 2 9B       — muito boa qualidade"),
]

PROMPTS = {
    "la": (
        "És um especialista em latim clássico e língua portuguesa europeia. "
        "Traduz o seguinte texto do latim para português de Portugal, "
        "de forma fluente e fiel ao original. "
        "Regras obrigatórias: "
        "(1) usa apenas palavras que existem em português; "
        "(2) mantém concordância gramatical rigorosa em género e número; "
        "(3) fornece apenas a tradução, sem comentários, notas ou explicações.\n\n"
        "Texto latino:\n{texto}\n\nTradução:"
    ),
    "grc": (
        "És um especialista em grego antigo (clássico e helenístico) e língua portuguesa europeia. "
        "Traduz o seguinte texto do grego antigo para português de Portugal, "
        "de forma fluente e fiel ao original. "
        "Regras obrigatórias: "
        "(1) usa apenas palavras que existem em português; "
        "(2) mantém concordância gramatical rigorosa em género e número; "
        "(3) fornece apenas a tradução, sem transliteração nem comentários.\n\n"
        "Texto grego:\n{texto}\n\nTradução:"
    ),
    "hbo": (
        "És um especialista em hebraico bíblico e língua portuguesa europeia. "
        "Traduz o seguinte texto do hebraico para português de Portugal, "
        "de forma fluente e fiel ao original. "
        "Regras: usa apenas palavras existentes em português; fornece apenas a tradução, "
        "sem transliteração nem comentários.\n\n"
        "Texto hebraico:\n{texto}\n\nTradução:"
    ),
    "comentario": (
        "És um professor de latim clássico. "
        "Faz um comentário filológico breve (3-5 frases) do seguinte trecho latino, "
        "em português de Portugal, cobrindo: estrutura gramatical, vocabulário notável e contexto literário. "
        "Usa apenas palavras que existem em português; não uses termos inventados.\n\n"
        "Trecho:\n{texto}\n\nComentário:"
    ),
}


# ── API Ollama ────────────────────────────────────────────────────────────────

def listar_modelos() -> list[str]:
    """Retorna lista de modelos instalados no Ollama."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except requests.exceptions.ConnectionError:
        return []
    except Exception:
        return []


def modelo_disponivel(nome: str) -> str | None:
    """
    Devolve o nome exacto do modelo (com tag) se estiver instalado,
    ou None. Aceita nomes parciais (ex: 'llama3.2' encontra 'llama3.2:latest').
    """
    modelos = listar_modelos()
    for m in modelos:
        if m == nome or m.startswith(nome + ":") or m.startswith(nome):
            return m
    return None


def _melhor_modelo() -> str | None:
    """Escolhe o melhor modelo disponível da lista recomendada."""
    for nome, _ in reversed(MODELOS_RECOMENDADOS):  # do melhor para o mais leve
        m = modelo_disponivel(nome)
        if m:
            return m
    mods = listar_modelos()
    return mods[0] if mods else None


def precarregar_modelo(modelo: str | None = None) -> tuple[bool, str]:
    """
    Carrega o modelo em memória sem gerar texto.
    Devolve (sucesso, nome_do_modelo).
    Ideal para chamar ao iniciar a aplicação.
    """
    modelo = modelo or _melhor_modelo()
    if not modelo:
        return False, ""
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": modelo, "keep_alive": -1},
            timeout=(15, 300),   # até 5 min para carregar o modelo
        )
        return r.status_code == 200, modelo
    except requests.exceptions.ConnectionError:
        return False, modelo
    except Exception:
        return False, modelo


def traduzir_stream(texto: str,
                    lingua: str = "la",
                    modelo: str | None = None) -> Iterator[str]:
    """
    Traduz via Ollama em modo streaming.
    Yield: fragmentos de texto à medida que chegam.
    """
    modelo = modelo or _melhor_modelo()
    if not modelo:
        yield "[Nenhum modelo Ollama disponível — execute: ollama pull llama3.2]"
        return

    prompt_tmpl = PROMPTS.get(lingua, PROMPTS["la"])
    prompt = prompt_tmpl.format(texto=texto.strip())

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": modelo, "prompt": prompt, "stream": True},
            stream=True,
            timeout=(15, None),  # 15 s para conectar; sem limite de leitura (streaming)
        )
        resp.raise_for_status()
        concluido = False
        for line in resp.iter_lines():
            if line:
                chunk = json.loads(line)
                if chunk.get("response"):
                    yield chunk["response"]
                if chunk.get("done"):
                    concluido = True
                    break
        if not concluido:
            yield "\n\n⚠ [Tradução interrompida — stream fechado sem sinal de conclusão.\nPossível causa: memória insuficiente. Tente um texto mais curto.]"
    except requests.exceptions.ConnectionError:
        yield "\n[Ollama não está a correr — execute: ollama serve]"
    except Exception as e:
        yield f"\n[Erro: {e}]"


def traduzir(texto: str,
             lingua: str = "la",
             modelo: str | None = None) -> str:
    """Traduz (bloqueante) e devolve a tradução completa."""
    return "".join(traduzir_stream(texto, lingua, modelo))


def comentario(texto: str, modelo: str | None = None) -> str:
    """Comentário filológico do trecho latino."""
    return "".join(traduzir_stream(texto, "comentario", modelo))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(description="Tradução latim/grego → PT com Ollama")
    ap.add_argument("texto", nargs="*")
    ap.add_argument("--lingua", "-l", default="la", choices=["la", "grc"],
                    help="Língua de origem (padrão: la)")
    ap.add_argument("--modelo", "-m", default=None,
                    help="Modelo Ollama a usar")
    ap.add_argument("--comentario", "-c", action="store_true",
                    help="Gera comentário filológico em vez de tradução")
    ap.add_argument("--listar", action="store_true",
                    help="Lista modelos instalados")
    args = ap.parse_args()

    if args.listar:
        mods = listar_modelos()
        if not mods:
            print("Ollama não responde ou sem modelos instalados.")
            print("Execute: ollama pull llama3.2")
        else:
            print("Modelos instalados:")
            for m in mods:
                print(f"  {m}")
        sys.exit(0)

    if not args.texto:
        ap.print_help()
        sys.exit(1)

    texto = " ".join(args.texto)
    print(f"[modelo: {args.modelo or _melhor_modelo() or '?'}]\n")

    if args.comentario:
        for chunk in traduzir_stream(texto, "comentario", args.modelo):
            print(chunk, end="", flush=True)
    else:
        for chunk in traduzir_stream(texto, args.lingua, args.modelo):
            print(chunk, end="", flush=True)
    print()
