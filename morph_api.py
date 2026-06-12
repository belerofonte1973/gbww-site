#!/usr/bin/env python3
"""
morph_api.py — Análise morfológica via Perseids/Morpheus REST API
  Endpoint: services.perseids.org/bsp/morphologyservice/analysis/word
  Motores: morpheuslat (latim), morpheusgrc (grego)

Resultados cacheados em ~/.config/busca_latina/morph/ por 30 dias.
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

BASE_URL = "https://services.perseids.org/bsp/morphologyservice/analysis/word"
ENGINES  = {"lat": "morpheuslat", "grc": "morpheusgrc"}
_CACHE   = Path.home() / ".config" / "busca_latina" / "morph"
_TTL     = 30 * 86400
_SES     = requests.Session()
_SES.headers.update({"User-Agent": "BuscaGrecoLatina/1.0", "Accept": "application/json"})

# ── tabelas de tradução PT ────────────────────────────────────────────────────
# A API devolve valores em inglês por extenso ("nominative", "plural", etc.)

_POFS_PT = {
    "noun": "substantivo", "verb": "verbo", "adjective": "adjectivo",
    "adverb": "advérbio", "pronoun": "pronome", "preposition": "preposição",
    "conjunction": "conjunção", "particle": "partícula", "numeral": "numeral",
    "article": "artigo", "interjection": "interjeição",
    "indeclinable": "indeclinável", "verb participle": "particípio",
}
_CASE_PT = {
    "nominative": "nominativo", "genitive": "genitivo", "dative": "dativo",
    "accusative": "acusativo", "ablative": "ablativo", "vocative": "vocativo",
    "locative": "locativo", "instrumental": "instrumental",
    # abreviaturas também (fallback)
    "nom": "nominativo", "gen": "genitivo", "dat": "dativo",
    "acc": "acusativo", "abl": "ablativo", "voc": "vocativo",
}
_NUM_PT = {
    "singular": "singular", "plural": "plural", "dual": "dual",
    "sg": "singular", "pl": "plural",
}
_GEND_PT = {
    "masculine": "masculino", "feminine": "feminino", "neuter": "neutro", "common": "comum",
    "masc": "masculino", "fem": "feminino", "neut": "neutro",
}
_TENSE_PT = {
    "present": "presente", "imperfect": "imperfeito", "future": "futuro",
    "perfect": "perfeito", "pluperfect": "mais-que-perf.",
    "future perfect": "futuro anterior", "aorist": "aoristo",
    "pres": "presente", "imperf": "imperfeito", "fut": "futuro",
    "perf": "perfeito", "plup": "mais-que-perf.",
}
_MOOD_PT = {
    "indicative": "indicativo", "subjunctive": "subjuntivo", "optative": "optativo",
    "imperative": "imperativo", "infinitive": "infinitivo", "participle": "particípio",
    "gerundive": "gerundivo", "supine": "supino",
    "ind": "indicativo", "subj": "subjuntivo", "inf": "infinitivo",
    "imp": "imperativo", "part": "particípio",
}
_VOICE_PT = {
    "active": "activo", "passive": "passivo", "middle": "médio",
    "medio-passive": "médio-passivo", "mediopassive": "médio-passivo",
    "act": "activo", "pass": "passivo", "mid": "médio",
}
_PERS_PT  = {
    "1st": "1ª", "2nd": "2ª", "3rd": "3ª",
    "first": "1ª", "second": "2ª", "third": "3ª",
}
_DECL_PT  = {
    "1st": "1ª dec.", "2nd": "2ª dec.", "3rd": "3ª dec.",
    "4th": "4ª dec.", "5th": "5ª dec.",
    "first": "1ª dec.", "second": "2ª dec.", "third": "3ª dec.",
}
_CONJ_PT  = {
    "1st": "1ª conj.", "2nd": "2ª conj.", "3rd": "3ª conj.", "4th": "4ª conj.",
    "first": "1ª conj.", "second": "2ª conj.", "third": "3ª conj.",
}

LABELS: dict = {
    "pofs":  ("Classe",     _POFS_PT),
    "case":  ("Caso",       _CASE_PT),
    "num":   ("Número",     _NUM_PT),
    "gend":  ("Género",     _GEND_PT),
    "tense": ("Tempo",      _TENSE_PT),
    "mood":  ("Modo",       _MOOD_PT),
    "voice": ("Voz",        _VOICE_PT),
    "pers":  ("Pessoa",     _PERS_PT),
    "decl":  ("Declinação", _DECL_PT),
    "conj":  ("Conjugação", _CONJ_PT),
}
FORM_ORDER = ("pofs", "tense", "mood", "voice", "pers", "case", "num", "gend", "decl", "conj")


def _val(v) -> str:
    if isinstance(v, dict):
        return v.get("$", "") or v.get("#text", "") or ""
    return str(v) if v else ""


def _field(field: str, raw: str) -> dict:
    label = LABELS[field][0]
    pt    = LABELS[field][1].get(raw, raw)
    return {"raw": raw, "label": label, "pt": pt}


def _cache_path(word: str, lang: str) -> Path:
    _CACHE.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w]", "_", word, flags=re.UNICODE)[:50]
    return _CACHE / f"{lang}_{safe}.json"


def _parse_response(data: dict) -> list:
    """Converte RDF Morpheus em lista de {lemma, pofs_pt, decl_dict, gend_dict, forms:[...]}."""
    results: list = []
    try:
        annotation = data.get("RDF", {}).get("Annotation", {})
        bodies = annotation.get("Body", [])
        if isinstance(bodies, dict):
            bodies = [bodies]

        for body in bodies:
            entry = body.get("rest", {}).get("entry", {})
            if not entry:
                continue

            dict_info = entry.get("dict", {})
            lemma    = _val(dict_info.get("hdwd", ""))
            pofs_raw = _val(dict_info.get("pofs", ""))
            pofs_pt  = _POFS_PT.get(pofs_raw, pofs_raw)

            # campos a nível do dicionário (decl, gend para substantivos)
            dict_decl = _val(dict_info.get("decl", ""))
            dict_gend = _val(dict_info.get("gend", ""))

            inflections = entry.get("infl", [])
            if isinstance(inflections, dict):
                inflections = [inflections]

            forms: list = []
            for infl in inflections:
                form: dict = {}

                # forma reconstruída (raiz + desinência)
                term = infl.get("term", {})
                stem = _val(term.get("stem", ""))
                suff = _val(term.get("suff", ""))
                if stem or suff:
                    form["forma"] = stem + suff

                # campos gramaticais da inflexão
                for field in FORM_ORDER:
                    raw = _val(infl.get(field, ""))
                    # fallback para campos de nível dict
                    if not raw:
                        if field == "decl":
                            raw = dict_decl
                        elif field == "gend":
                            raw = dict_gend
                    if raw and field in LABELS:
                        form[field] = _field(field, raw)

                if form:
                    forms.append(form)

            if lemma or forms:
                results.append({
                    "lemma":   lemma,
                    "pofs_raw": pofs_raw,
                    "pofs_pt":  pofs_pt,
                    "forms":    forms,
                })
    except Exception:
        pass

    return results


def analisar(word: str, lang: str = "lat") -> dict:
    """
    Analisa morfologicamente *word* via Perseids/Morpheus REST API.
    Retorna: {word, lang, results:[{lemma, pofs_pt, forms:[...]}]}.
    Lança requests.HTTPError se a API falhar.
    """
    if lang not in ENGINES:
        return {"erro": f"Língua inválida: {lang}", "word": word, "results": []}

    fp = _cache_path(word, lang)
    if fp.exists() and time.time() - fp.stat().st_mtime < _TTL:
        return json.loads(fp.read_text("utf-8"))

    engine = ENGINES[lang]
    url = f"{BASE_URL}?lang={lang}&engine={engine}&word={quote(word)}"
    r   = _SES.get(url, timeout=15)
    r.raise_for_status()

    results = _parse_response(r.json())
    out     = {"word": word, "lang": lang, "results": results}
    fp.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
    return out
