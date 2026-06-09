#!/usr/bin/env python3
"""
pronunciar_latim.py — Pronúncia de latim e grego antigo com múltiplos motores

Motores disponíveis
-------------------
  edge-tts   (online, gratuito, voz neural — recomendado)
  piper      (offline, voz neural humana — recomendado para grego)
  espeak-ng  (offline, voz sintética — latim e IPA interno)

Vozes sugeridas para latim
--------------------------
  it-IT-DiegoNeural    — italiano masc. (clássico / eclesiástico)
  it-IT-IsabellaNeural — italiano fem.  (clássico / eclesiástico)
  es-ES-AlvaroNeural   — espanhol masc. (bom para eclesiástico)
  es-ES-ElviraNeural   — espanhol fem.  (bom para eclesiástico)
  la (espeak-ng)       — voz latina sintética (offline)

Vozes sugeridas para grego
--------------------------
  el_GR-rapunzelina-low — Piper neural fem. (offline, recomendado)
  el-GR-AthinaNeural    — grego moderno fem. neural (online)
  el-GR-NestorasNeural  — grego moderno masc. neural (online)

  Nota: vozes gregas modernas (Piper e edge-tts) recebem texto monotónico;
  a conversão polítonico→monotónico é feita automaticamente.

CLI:
  python3 pronunciar_latim.py "Arma virumque cano"
  python3 pronunciar_latim.py "Gloria in excelsis" --ecl
  python3 pronunciar_latim.py "amor" --ipa
  python3 pronunciar_latim.py "Gallia est omnis" --voz it-IT-IsabellaNeural
  python3 pronunciar_latim.py "Ἄνδρα μοι ἔννεπε" --voz el_GR-rapunzelina-low
  python3 pronunciar_latim.py "Ἄνδρα μοι ἔννεπε" --voz el-GR-NestorasNeural
"""

import re
import unicodedata
import subprocess
import signal
import os
import tempfile
import shutil
from pathlib import Path

# caminhos dos motores TTS
_EDGE_TTS  = str(Path.home() / ".local/share/pipx/venvs/pip/bin/edge-tts")
_PIPER     = str(Path.home() / ".local/bin/piper")
_PIPER_DIR = Path.home() / ".local/share/piper"
_FFPLAY    = shutil.which("ffplay")
_ESPEAK    = shutil.which("espeak-ng")

# processos em curso
_proc_tts:   subprocess.Popen | None = None
_proc_audio: subprocess.Popen | None = None


# ── vozes disponíveis ─────────────────────────────────────────────────────────

VOZES = [
    # (id, rótulo, motor, grupo_lingua)
    # ── latim ──────────────────────────────────────────────────────────────────
    ("it-IT-DiegoNeural",    "Diego (italiano masc.) — online",       "edge",   "la"),
    ("it-IT-IsabellaNeural", "Isabella (italiano fem.) — online",     "edge",   "la"),
    ("es-ES-AlvaroNeural",   "Álvaro (espanhol masc.) — online",      "edge",   "la"),
    ("es-ES-ElviraNeural",   "Elvira (espanhol fem.) — online",       "edge",   "la"),
    ("pt-BR-AntonioNeural",  "Antônio (port. bras. masc.) — online",  "edge",   "la"),
    ("pt-BR-FranciscaNeural","Francisca (port. bras. fem.) — online", "edge",   "la"),
    ("la",                   "espeak-ng latim (offline)",              "espeak", "la"),
    ("it",                   "espeak-ng italiano (offline)",           "espeak", "la"),
    # ── grego ──────────────────────────────────────────────────────────────────
    ("el_GR-rapunzelina-low", "Rapunzelina (grego fem.) — offline",   "piper",  "grc"),
    ("el-GR-AthinaNeural",    "Athina (grego fem.) — online",         "edge",   "grc"),
    ("el-GR-NestorasNeural",  "Nestoras (grego masc.) — online",      "edge",   "grc"),
    # ── hebraico (antigo / medieval) ───────────────────────────────────────────
    # edge-tts: vozes neurais humanas de hebraico israelita moderno (online)
    ("he-IL-AvriNeural",  "Avri (hebraico masc.) — online",              "edge",   "hbo"),
    ("he-IL-HilaNeural",  "Hila (hebraico fem.) — online",               "edge",   "hbo"),
    # espeak-ng: voz sintética offline — disponível sem download
    ("he",                "espeak-ng hebraico masc. (offline)",           "espeak", "hbo"),
]

# grupos para filtrar na GUI
VOZES_LATIM    = [v for v in VOZES if v[3] == "la"]
VOZES_GREGO    = [v for v in VOZES if v[3] == "grc"]
VOZES_HEBRAICO = [v for v in VOZES if v[3] == "hbo"]

VOZES_DEFAULT_CLASSICO     = "it-IT-DiegoNeural"
VOZES_DEFAULT_ECLESIASTICO = "it-IT-IsabellaNeural"
VOZES_DEFAULT_GREGO        = "el_GR-rapunzelina-low"
VOZES_DEFAULT_HEBRAICO     = "he-IL-AvriNeural"
VOZES_DEFAULT_HEBRAICO_OFFLINE = "he"

_PIPER_VOICES_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


def baixar_modelo_piper(nome_voz: str, progresso_cb=None) -> bool:
    """
    Descarrega o modelo Piper (ONNX + JSON de configuração) para *nome_voz*
    se ainda não estiver presente em _PIPER_DIR.

    progresso_cb(msg: str) é chamado com a etapa actual (opcional).
    Devolve True em caso de sucesso.

    Exemplo: baixar_modelo_piper("he_IL-udi-medium")
    """
    onnx  = _PIPER_DIR / f"{nome_voz}.onnx"
    jfile = _PIPER_DIR / f"{nome_voz}.onnx.json"
    if onnx.exists() and jfile.exists():
        return True

    # Constrói o URL: «he_IL-udi-medium» → he/he_IL/udi/medium/
    parts        = nome_voz.split("-")
    lang_country = parts[0]                   # e.g. he_IL
    lang         = lang_country.split("_")[0]  # e.g. he
    quality      = parts[-1]                   # low / medium / high
    speaker      = "-".join(parts[1:-1])       # udi / rapunzelina / …
    base_url     = f"{_PIPER_VOICES_BASE}/{lang}/{lang_country}/{speaker}/{quality}"

    import urllib.request
    _PIPER_DIR.mkdir(parents=True, exist_ok=True)

    for filename, dest in [
        (f"{nome_voz}.onnx",      onnx),
        (f"{nome_voz}.onnx.json", jfile),
    ]:
        url = f"{base_url}/{filename}"
        try:
            if progresso_cb:
                progresso_cb(f"A descarregar {filename}…")
            urllib.request.urlretrieve(url, dest)
        except Exception:
            if dest.exists():
                dest.unlink(missing_ok=True)
            return False
    return True


# ── pré-processamento eclesiástico ────────────────────────────────────────────

def _eclesiastico(texto: str) -> str:
    """
    Adapta grafia latina para pronúncia eclesiástica (vaticana).
    O resultado é enviado para a voz italiana/espanhola do motor TTS.

      ph → f        ae/oe → e     sc+e/i → sci
      c+e/i → ci    g+e/i → gi    ti+V → zi
      J → I / j → i               h mudo (exceto ch)
    """
    t = texto
    t = re.sub(r'ph', 'f', t, flags=re.IGNORECASE)
    t = re.sub(r'th', 't', t, flags=re.IGNORECASE)
    t = re.sub(r'rh', 'r', t, flags=re.IGNORECASE)
    t = re.sub(r'æ|ae', 'e', t, flags=re.IGNORECASE)
    t = re.sub(r'œ|oe', 'e', t, flags=re.IGNORECASE)
    t = re.sub(r'sc(?=[eiEI])', 'sci', t)
    t = re.sub(r'c(?=[eiEI])', 'ci', t)
    t = re.sub(r'g(?=[eiEI])', 'gi', t)
    t = re.sub(r'(?<![stxSTX])ti(?=[aeiouAEIOU])', 'zi', t)
    t = re.sub(r'J', 'I', t)
    t = re.sub(r'j', 'i', t)
    t = re.sub(r'(?<!c)h', '', t, flags=re.IGNORECASE)
    return t


# ── pré-processamento grego ───────────────────────────────────────────────────

def _para_monotono(texto: str) -> str:
    """
    Converte texto grego polítonico para monotónico (sem espíritos, sem acentos
    adicionais), de modo a ser aceite por vozes de grego moderno (edge-tts).
    Usa decomposição NFD para separar diacríticos e remove todos os combining
    marks do bloco Unicode «Combining Diacritical Marks» e «Greek Extended».
    """
    norm = unicodedata.normalize('NFD', texto)
    resultado = []
    for ch in norm:
        cat = unicodedata.category(ch)
        # Remove todo o tipo de combining mark (Mn = Mark, Nonspacing; Mc, Me)
        if cat.startswith('M'):
            continue
        resultado.append(ch)
    return unicodedata.normalize('NFC', ''.join(resultado))


# ── IPA ───────────────────────────────────────────────────────────────────────

def ipa_classico(texto: str) -> str:
    """Transcrição IPA da pronúncia latina clássica (via espeak-ng)."""
    if not _ESPEAK:
        return "[espeak-ng não encontrado]"
    resultado = subprocess.run(
        [_ESPEAK, '-v', 'la', '--ipa', '-q'],
        input=texto, capture_output=True, text=True
    )
    return resultado.stdout.strip()


def ipa_grego(texto: str) -> str:
    """Transcrição IPA do grego antigo reconstituído (via espeak-ng grc)."""
    if not _ESPEAK:
        return "[espeak-ng não encontrado]"
    resultado = subprocess.run(
        [_ESPEAK, '-v', 'grc', '--ipa', '-q'],
        input=texto, capture_output=True, text=True
    )
    return resultado.stdout.strip()


# ── controlo de reprodução ────────────────────────────────────────────────────

def parar():
    """Interrompe TTS e reprodução em curso (mata o grupo de processos inteiro)."""
    global _proc_tts, _proc_audio
    for proc in (_proc_tts, _proc_audio):
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    proc.kill()
    _proc_tts   = None
    _proc_audio = None


def esta_a_falar() -> bool:
    return ((_proc_tts   and _proc_tts.poll()   is None) or
            (_proc_audio and _proc_audio.poll() is None))


# ── pronúncia principal ───────────────────────────────────────────────────────

def pronunciar(texto: str,
               voz: str        = VOZES_DEFAULT_CLASSICO,
               variante: str   = 'classico',
               velocidade: int = 0,
               tom: int        = 0) -> None:
    """
    Reproduz texto latino ou grego com o motor e voz indicados.

    Parâmetros
    ----------
    texto      : texto a pronunciar (latim ou grego polítonico)
    voz        : id da voz (ver VOZES)
    variante   : 'classico' | 'eclesiastico'  (só relevante para latim)
    velocidade : ajuste de velocidade em % relativa (-50 a +50); 0 = padrão
    tom        : apenas para espeak-ng (0-99)
    """
    global _proc_tts, _proc_audio
    parar()

    # determina o motor e grupo de língua
    voz_info  = next((v for v in VOZES if v[0] == voz), None)
    motor     = voz_info[2] if voz_info else "edge"
    grupo_ling = voz_info[3] if voz_info else "la"

    if grupo_ling == "grc":
        # Piper e edge-tts usam vozes de grego moderno: precisam de texto monotónico
        if motor in ("edge", "piper"):
            texto_proc = _para_monotono(texto)
        else:
            texto_proc = texto   # espeak-ng grc lida com polítonico directamente
    elif variante == 'eclesiastico':
        texto_proc = _eclesiastico(texto)
    else:
        texto_proc = texto

    if motor == "espeak":
        # espeak-ng: offline
        spd = 130 + int(velocidade * 0.5)
        _proc_tts = subprocess.Popen(
            [_ESPEAK, '-v', voz, '-s', str(max(70, min(220, spd))),
             '-p', str(max(0, min(99, 50 + tom))), texto_proc],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    elif motor == "piper":
        # piper: TTS neural offline; gera WAV e reproduz com ffplay
        model_path = _PIPER_DIR / f"{voz}.onnx"
        if not model_path.exists():
            print(f"[Erro: modelo Piper não encontrado: {model_path}]")
            return
        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        tmp.close()
        # velocidade → length_scale (1.0 = normal; <1 = mais rápido; >1 = mais lento)
        length_scale = max(0.5, min(2.0, 1.0 - velocidade / 100.0))
        _proc_tts = subprocess.Popen(
            [_PIPER, '-m', str(model_path),
             '--length-scale', f'{length_scale:.2f}',
             '-f', tmp.name],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _proc_tts.communicate(input=texto_proc.encode())
        ret_code = _proc_tts.returncode
        _proc_tts = None
        if ret_code == 0 and _FFPLAY:
            _proc_audio = subprocess.Popen(
                [_FFPLAY, '-nodisp', '-autoexit', tmp.name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    else:
        # edge-tts: gera MP3 e reproduz com ffplay
        if not Path(_EDGE_TTS).exists():
            print(f"[Erro: edge-tts não encontrado em {_EDGE_TTS}]")
            return
        tmp = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        tmp.close()

        # Bug: '--rate', '-30%' → argparse do edge-tts confunde '-30%' com flag.
        # Solução: passar '--rate=-30%' como argumento único (formato com '=').
        rate_str = f"+{velocidade}%" if velocidade >= 0 else f"{velocidade}%"

        cmd_edge = [_EDGE_TTS,
                    '--voice', voz,
                    f'--rate={rate_str}',       # '=' evita ambiguidade com valores negativos
                    '--text', texto_proc,
                    '--write-media', tmp.name]

        # Usar Popen (não subprocess.run) para que parar() possa matar o processo
        _proc_tts = subprocess.Popen(
            cmd_edge,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _proc_tts.wait()          # bloqueia o thread PronunciaThread até gerar o MP3
        ret_code = _proc_tts.returncode
        _proc_tts = None          # edge-tts concluiu; liberta o handle

        if ret_code == 0 and _FFPLAY:
            _proc_audio = subprocess.Popen(
                [_FFPLAY, '-nodisp', '-autoexit', tmp.name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser(description='Pronúncia de latim')
    ap.add_argument('texto', nargs='+')
    ap.add_argument('--ecl',  action='store_true', help='Pronúncia eclesiástica')
    ap.add_argument('--ipa',  action='store_true', help='Mostra IPA (clássico)')
    ap.add_argument('--voz',  default=VOZES_DEFAULT_CLASSICO,
                    help=f'Voz (padrão: {VOZES_DEFAULT_CLASSICO})')
    ap.add_argument('--listar', action='store_true', help='Lista vozes disponíveis')
    ap.add_argument('-r', '--rate', type=int, default=0,
                    help='Velocidade relativa -50..+50 (padrão 0)')
    args = ap.parse_args()

    if args.listar:
        print(f"{'ID':40} {'Motor':8} {'Rótulo'}")
        print('-' * 80)
        for vid, rot, motor, *_ in VOZES:
            print(f"{vid:40} {motor:8} {rot}")
        raise SystemExit(0)

    texto = ' '.join(args.texto)
    if args.ipa:
        print('IPA (clássico):', ipa_classico(texto))

    variante = 'eclesiastico' if args.ecl else 'classico'
    pronunciar(texto, args.voz, variante, args.rate)

    # espera fim da reprodução
    import time
    while esta_a_falar():
        time.sleep(0.2)
