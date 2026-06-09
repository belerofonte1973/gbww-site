#!/usr/bin/env python3
"""
busca_latina.py — Busca em corpus latino offline

Corpora disponíveis:
  • Latin Library  (~2100 textos em /cltk_data/lat/text/lat_text_latin_library)
  • Perseus/CLTK   (~173 textos em  /cltk_data/lat/text/lat_text_perseus)

Sintaxe de busca:
  amor        palavra exata e isolada ("amor", não "amorem" nem "amoris")
  amor-       prefixo: palavras que começam com "amor" (amor, amoris, amorem…)
  -que        sufixo:  palavras que terminam em "que"  (itaque, quoque…)
  -amor-      infixo:  palavras que contêm "amor"
  "carpe diem"  expressão — mesma regra (isolada na frase)
  virtut\\w+  expressão regular pura (sem regra de hífen)

Uso:
  python3 busca_latina.py amor
  python3 busca_latina.py amor- -i        # todas as formas de amor
  python3 busca_latina.py -que -i -m 20   # palavras terminadas em -que
  python3 busca_latina.py "carpe diem" -i -m 10
"""

import re
import sys
import argparse
from pathlib import Path


def _proteger_sufixo():
    """Argparse confunde termos que começam com '-' (ex.: -que) com flags.
    Este pré-processamento os move para depois de '--' preservando as demais opções."""
    OPTIONS       = {'-h', '--help', '-i', '--ignorar', '-l', '--listar',
                     '--ll', '--perseus'}
    VALUE_OPTIONS = {'-c', '--contexto', '-m', '--max'}

    argv = sys.argv[1:]
    if '--' in argv or not argv:
        return                          # já protegido ou vazio

    result, term = [], None
    i = 0
    while i < len(argv):
        a = argv[i]
        if term is None and a.startswith('-') and a not in OPTIONS and a not in VALUE_OPTIONS:
            term = a                    # este é o termo de busca com hífen inicial
        else:
            result.append(a)
            if a in VALUE_OPTIONS and i + 1 < len(argv):
                i += 1
                result.append(argv[i]) # inclui o valor da opção (-c 4, -m 10…)
        i += 1

    if term is not None:
        sys.argv[1:] = result + ['--', term]

_proteger_sufixo()

LATIN_LIB = Path.home() / "cltk_data/lat/text/lat_text_latin_library"
PERSEUS    = Path.home() / "cltk_data/lat/text/lat_text_perseus"

STRIP_TAGS   = re.compile(r"<[^>]+>")
STRIP_WS     = re.compile(r"[ \t]+")
_REGEX_CHARS = re.compile(r'[.^$*+?\[\]\\|()\{\}]')


def build_pattern(term: str, ignore_case: bool = True) -> re.Pattern:
    """
    Compila o padrão de busca aplicando as regras de hífen:

      -x   → sufixo:  \\b\\w*x\\b  (palavras terminadas em x)
      x-   → prefixo: \\bx\\w*\\b  (palavras iniciadas por x)
      -x-  → infixo:  \\b\\w*x\\w*\\b  (palavras contendo x)
      x    → exato:   \\bx\\b  (palavra isolada, sem afixos)

    Se o termo contiver caracteres especiais de regex (. * + ? [ \\ etc.)
    é tratado como expressão regular pura, sem modificação.
    """
    flags = re.IGNORECASE if ignore_case else 0

    is_suffix = term.startswith("-") and len(term) > 1
    is_prefix = term.endswith("-")   and len(term) > 1

    # separa os hifens do núcleo
    core = term
    if is_suffix:
        core = core[1:]
    if is_prefix:
        core = core[:-1]

    # se o núcleo contiver metacaracteres de regex → usa como expressão pura
    if _REGEX_CHARS.search(core):
        return re.compile(term, flags)

    esc = re.escape(core)

    if is_suffix and is_prefix:
        pat = rf"\b\w*{esc}\w*\b"
    elif is_suffix:
        pat = rf"\b\w*{esc}\b"
    elif is_prefix:
        pat = rf"\b{esc}\w*\b"
    else:
        pat = rf"\b{esc}\b"

    return re.compile(pat, flags)


# ── leitura de arquivos ──────────────────────────────────────────────────────

def read_latin_lib(path: Path) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.readlines()


def read_perseus_xml(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # remove cabeçalho <teiHeader> inteiro
    raw = re.sub(r"<teiHeader[^>]*>.*?</teiHeader>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    # remove todas as tags
    raw = STRIP_TAGS.sub(" ", raw)
    # colapsa espaços e divide em linhas de ~120 chars (no limite de palavra)
    words = raw.split()
    lines, buf, length = [], [], 0
    for w in words:
        buf.append(w)
        length += len(w) + 1
        if length >= 120:
            lines.append(" ".join(buf))
            buf, length = [], 0
    if buf:
        lines.append(" ".join(buf))
    return lines


# ── rótulo autor / obra ──────────────────────────────────────────────────────

def label_ll(path: Path) -> tuple[str, str]:
    """Retorna (autor, obra) para Latin Library."""
    rel = path.relative_to(LATIN_LIB)
    parts = rel.parts
    if len(parts) == 1:
        return "Latin Library", parts[0].removesuffix(".txt")
    return parts[0], "/".join(parts[1:]).removesuffix(".txt")


def label_perseus(path: Path) -> tuple[str, str]:
    """Retorna (autor, obra) para Perseus."""
    rel = path.relative_to(PERSEUS)
    parts = rel.parts          # ex: ['Cicero', 'opensource', 'cic.off_lat.xml']
    author = parts[0]
    stem = path.stem           # ex: 'cic.off_lat'
    work = stem.removesuffix("_lat").removesuffix("_grc")
    return author, work


def first_line_title(path: Path) -> str:
    """Lê a primeira linha não vazia do arquivo (Latin Library costuma ter o título lá)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                t = line.strip()
                if t:
                    return t[:80]
    except OSError:
        pass
    return ""


# ── busca principal ──────────────────────────────────────────────────────────

def search_corpus(files, pattern, ctx_size, is_xml):
    """
    Gerador: yield (path, line_idx, lines, is_xml)
    para cada linha que casa com o padrão.
    """
    for path in sorted(files):
        lines = read_perseus_xml(path) if is_xml else read_latin_lib(path)
        for i, line in enumerate(lines):
            if pattern.search(line):
                yield path, i, lines


def format_match(path, line_idx, lines, is_xml, ctx_size):
    if is_xml:
        corpus, (author, work) = "Perseus", label_perseus(path)
    else:
        corpus, (author, work) = "Latin Library", label_ll(path)
        # tenta enriquecer com título da primeira linha
        title = first_line_title(path)
        if title and title.lower() not in author.lower() and title.lower() not in work.lower():
            work = f"{work}  [{title}]"

    start = max(0, line_idx - ctx_size)
    end   = min(len(lines), line_idx + ctx_size + 1)

    header = f"\n{'─'*64}\n[{corpus}] {author} — {work}  (linha {line_idx + 1})"
    ctx = []
    for j in range(start, end):
        marker = "▶▶" if j == line_idx else "  "
        ctx.append(f"  {marker} {lines[j].rstrip()}")
    return header + "\n" + "\n".join(ctx)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Busca em corpus latino offline (Latin Library + Perseus/CLTK)",
        epilog=(
            "Exemplos:\n"
            "  %(prog)s amor\n"
            "  %(prog)s 'carpe diem' -i -m 10\n"
            "  %(prog)s 'dum spiro' -c 4 --perseus\n"
            "  %(prog)s 'virtut\\w+' -i -l\n"
            "  %(prog)s Catilina --ll -l"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("termo", help="Palavra / frase / expressão regular")
    ap.add_argument("-c", "--contexto", type=int, default=2, metavar="N",
                    help="Linhas de contexto antes/depois do resultado (padrão: 2)")
    ap.add_argument("-i", "--ignorar", action="store_true",
                    help="Ignorar maiúsculas/minúsculas")
    ap.add_argument("-l", "--listar", action="store_true",
                    help="Listar apenas obras com ocorrências (sem exibir contexto)")
    ap.add_argument("-m", "--max", type=int, default=0, metavar="N",
                    help="Parar após N ocorrências (0 = sem limite)")
    ap.add_argument("--ll", action="store_true",
                    help="Buscar somente na Latin Library")
    ap.add_argument("--perseus", action="store_true",
                    help="Buscar somente no Perseus/CLTK")
    args = ap.parse_args()

    try:
        pat = build_pattern(args.termo, args.ignorar)
    except re.error as e:
        print(f"Expressão regular inválida: {e}", file=sys.stderr)
        sys.exit(1)

    do_ll      = not args.perseus
    do_perseus = not args.ll

    sources = []
    if do_ll and LATIN_LIB.exists():
        sources.append((LATIN_LIB.rglob("*.txt"), False))
    elif do_ll:
        print(f"Latin Library não encontrada em {LATIN_LIB}", file=sys.stderr)

    if do_perseus and PERSEUS.exists():
        sources.append((PERSEUS.rglob("*_lat.xml"), True))
    elif do_perseus:
        print(f"Perseus não encontrado em {PERSEUS}", file=sys.stderr)

    total        = 0
    listed_works = set()   # para --listar, evita repetição da mesma obra

    for files, is_xml in sources:
        for path, line_idx, lines in search_corpus(files, pat, args.contexto, is_xml):
            if args.listar:
                work_id = str(path)
                if work_id not in listed_works:
                    listed_works.add(work_id)
                    if is_xml:
                        corpus, (author, work) = "Perseus", label_perseus(path)
                    else:
                        corpus, (author, work) = "Latin Library", label_ll(path)
                    print(f"[{corpus}] {author} — {work}")
            else:
                print(format_match(path, line_idx, lines, is_xml, args.contexto))
                total += 1
                if args.max and total >= args.max:
                    print(f"\n[Parado em {args.max} resultado(s). Use -m 0 para ver todos.]")
                    sys.exit(0)

    if args.listar:
        n = len(listed_works)
        print(f"\n{n} obra(s) com ocorrências de '{args.termo}'.")
    else:
        if total == 0:
            print(f"Nenhuma ocorrência encontrada para: '{args.termo}'")
        else:
            print(f"\n{'─'*64}\nTotal: {total} ocorrência(s)  (use -m N para limitar)")


if __name__ == "__main__":
    main()
