# Great Books of the Western World — Site de Consulta

**Repositório:** https://github.com/belerofonte1973/gbww-site

Aplicação web em Flask para navegar e pesquisar a coleção *Great Books of the Western World* (Encyclopædia Britannica, 1952). Permite explorar os 102 tópicos do **Syntopicon** (com introduções e referências cruzadas) e fazer busca de texto completo nas ~60 mil passagens dos 54 volumes.

Os textos-fonte são produzidos pelo pipeline de extração em [belerofonte1973/gbww](https://github.com/belerofonte1973/gbww).

## Funcionalidades

- **Página inicial** — os 102 tópicos do Syntopicon agrupados por letra.
- **Tópico** (`/topic/<slug>`) — introdução, *outline* de subtópicos, referências agrupadas por autor e referências cruzadas para outros tópicos.
- **Passagem** (`/passage/<volume>/<marcador>`) — texto de uma passagem, navegação anterior/seguinte e tópicos que a citam.
- **Volume** (`/volume/<n>`) — pré-visualização das passagens de um volume.
- **Busca** (`/search?q=...`) — texto completo (FTS5) nas passagens, ou por tópico, ou por autor/obra.
- **API** (`/api/passage/<volume>/<marcador>`) — JSON de uma passagem.

## Base de dados

`gbww.db` (~277 MB, SQLite com FTS5) **não é versionada** — reconstrói-se a partir das fontes. Tabelas principais:

| Tabela | Conteúdo |
|--------|----------|
| `topics` | 102 tópicos do Syntopicon (nome, slug, introdução, *outline*) |
| `passages` | ~60.500 passagens dos 54 volumes (volume, marcador `[Xa]`, texto) |
| `refs` | ~51.000 referências do Mapa do Syntopicon (tópico → volume/autor/obra/página) |
| `passages_fts`, `topics_fts` | índices FTS5 de busca |

## Instalação

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Construir a base de dados

O `build_db.py` lê os ficheiros do repositório [gbww](https://github.com/belerofonte1973/gbww) (por omissão em `/home/rodrigo/gbww/`):

- `txts/` — TXTs dos 54 volumes (passagens)
- `syntopicon_v18/` — 102 tópicos do Syntopicon (introduções e *outlines*)
- `Mapa de referências do Syntopicon/` — referências cruzadas (volumes 2 e 3)

```bash
python3 build_db.py
```

## Executar

```bash
python3 app.py        # http://127.0.0.1:5000
```

## Estrutura

```
gbww_site/
  app.py          servidor Flask e rotas
  build_db.py     construção da base de dados SQLite
  requirements.txt
  templates/      index, topic, passage, volume, search, base, 404, 500
  static/         style.css, script.js
```
