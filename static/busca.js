'use strict';

// ── estado global ─────────────────────────────────────────────────────────────

const S = {
  searchES:    null,
  transCtrl:   null,
  percObraES:  null,
  percObras:   [],
  percRefs:    [],
  percObraURN: '',
  workData:    {},
  workOrder:   [],
  selWork:     null,
  savedSel:    '',
  cdliData:    [],
  cdliSel:     null,
  llObras:     [],
  llSelWork:   null,
};

// ── tabs ──────────────────────────────────────────────────────────────────────

document.querySelectorAll('.btab').forEach(btn => {
  btn.addEventListener('click', () => {
    const id = btn.dataset.tab;
    document.querySelectorAll('.btab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.btab').forEach(b => b.classList.remove('active'));
    document.getElementById(id).classList.add('active');
    btn.classList.add('active');
  });
});

// ── status ────────────────────────────────────────────────────────────────────

function setStatus(msg) {
  const el = document.getElementById('status-bar');
  if (el) el.textContent = msg;
}

// ── busca offline ─────────────────────────────────────────────────────────────

document.getElementById('q')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') startSearch();
});

function startSearch() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;

  S.workData  = {};
  S.workOrder = [];
  S.selWork   = null;
  document.getElementById('works-list').innerHTML = '';
  document.getElementById('results').innerHTML    = '';

  const ignore = document.getElementById('chk-ignore').checked ? '1' : '0';
  const ctx    = document.getElementById('spin-ctx').value;
  const max    = document.getElementById('spin-max').value;
  const corpus = document.querySelector('input[name="corpus"]:checked').value;
  const url    = `/api/buscar?q=${enc(q)}&ignore=${ignore}&ctx=${ctx}&max=${max}&corpus=${corpus}`;

  if (S.searchES) { S.searchES.close(); }
  S.searchES = new EventSource(url);
  setBuscaBusy(true);

  S.searchES.addEventListener('result', e => onResult(JSON.parse(e.data)));
  S.searchES.addEventListener('status', e => setStatus(JSON.parse(e.data).msg));
  S.searchES.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    S.searchES.close(); S.searchES = null;
    setBuscaBusy(false);
    const n = Object.values(S.workData).reduce((s, a) => s + a.length, 0);
    const w = Object.keys(S.workData).length;
    setStatus(`${n} ocorrência(s) em ${w} obra(s)${d.truncated ? ' (truncado)' : ''}.`);
  });
  S.searchES.addEventListener('erro', e => {
    setStatus('Erro: ' + JSON.parse(e.data).msg);
    S.searchES.close(); S.searchES = null;
    setBuscaBusy(false);
  });
  S.searchES.onerror = () => { setBuscaBusy(false); S.searchES = null; };
}

function stopSearch() {
  if (S.searchES) {
    S.searchES.close(); S.searchES = null;
    setBuscaBusy(false);
    setStatus('Busca interrompida.');
  }
}

function setBuscaBusy(busy) {
  document.getElementById('btn-search').disabled = busy;
  document.getElementById('btn-stop').disabled   = !busy;
}

function onResult(d) {
  const key = `[${d.corpus}] ${d.author} — ${d.work}`;
  if (!S.workData[key]) {
    S.workData[key] = [];
    S.workOrder.push(key);
    const li = document.createElement('li');
    li.textContent = key;
    li.dataset.key = key;
    li.title       = key;
    li.addEventListener('click', () => selectWork(key));
    document.getElementById('works-list').appendChild(li);
    if (S.workOrder.length === 1) selectWork(key);
  }
  S.workData[key].push(d);
  if (S.selWork === key) appendBlock(d);
}

function selectWork(key) {
  S.selWork = key;
  document.querySelectorAll('#works-list li').forEach(li =>
    li.classList.toggle('active', li.dataset.key === key));
  const panel = document.getElementById('results');
  panel.innerHTML = '';
  (S.workData[key] || []).forEach(appendBlock);
}

function appendBlock(d) {
  const q = document.getElementById('q').value;
  const ignoreCase = document.getElementById('chk-ignore').checked;
  const pat = buildPattern(q, ignoreCase);
  const key = `[${d.corpus}] ${d.author} — ${d.work}`;
  const panel = document.getElementById('results');

  const wrap = document.createElement('div');
  wrap.className = 'result-block';

  const hdr = document.createElement('div');
  hdr.className   = 'result-header';
  hdr.textContent = key;
  wrap.appendChild(hdr);

  d.lines.forEach((line, j) => {
    const row = document.createElement('div');
    row.className = 'result-line' + (j === d.match_offset ? ' match-line' : '');
    if (j === d.match_offset) {
      row.innerHTML = '▶ ' + hlLine(line, pat);
    } else {
      row.textContent = '  ' + line;
    }
    wrap.appendChild(row);
  });

  const sep = document.createElement('div');
  sep.className   = 'result-sep';
  sep.textContent = '─'.repeat(60);
  wrap.appendChild(sep);
  panel.appendChild(wrap);
}

function buildPattern(term, ignoreCase) {
  try {
    const flags  = ignoreCase ? 'gi' : 'g';
    const hasSuf = term.startsWith('-') && term.length > 1;
    const hasPre = term.endsWith('-')   && term.length > 1;
    let core = term;
    if (hasSuf) core = core.slice(1);
    if (hasPre) core = core.slice(0, -1);
    const isRe = /[.^$*+?\[\]\\|()\{\}]/.test(core);
    if (isRe) return new RegExp(term, flags);
    const esc2 = core.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    let pat;
    if (hasSuf && hasPre) pat = `\\b\\w*${esc2}\\w*\\b`;
    else if (hasSuf)      pat = `\\b\\w*${esc2}\\b`;
    else if (hasPre)      pat = `\\b${esc2}\\w*\\b`;
    else                  pat = `\\b${esc2}\\b`;
    return new RegExp(pat, flags);
  } catch { return null; }
}

function hlLine(line, pat) {
  const safe = line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  if (!pat) return safe;
  return safe.replace(pat, m =>
    `<span class="hl">${m.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}</span>`
  );
}

document.getElementById('results')?.addEventListener('mouseup', () => {
  const sel = window.getSelection().toString().trim();
  if (sel) S.savedSel = sel;
});

// ── tradução / IA ─────────────────────────────────────────────────────────────

function getTextoParaTraduzir() {
  const sel = window.getSelection().toString().trim();
  return sel || S.savedSel;
}

async function startTranslation(motor) {
  const texto = getTextoParaTraduzir();
  if (!texto) {
    document.getElementById('trans-output').textContent =
      '⚠ Selecione texto nos resultados primeiro.';
    return;
  }
  const lingua = document.getElementById('sel-lingua').value;
  const modelo = motor === 'gemini'
    ? (document.getElementById('sel-gemini-modelo')?.value || '')
    : (document.getElementById('sel-ollama-modelo')?.value || '');

  if (S.transCtrl) S.transCtrl.abort();
  S.transCtrl = new AbortController();

  const out   = document.getElementById('trans-output');
  const label = motor === 'gemini' ? '🌟 Gemini' : motor === 'comentario' ? '📖 Comentário' : '🤖 Ollama';
  out.textContent = `${label}…\n\n`;

  try {
    const resp = await fetch('/api/traduzir', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({texto, lingua, motor, modelo}),
      signal:  S.transCtrl.signal,
    });
    await readSSEStream(resp.body, {
      chunk:  d => { out.textContent += d.text; out.scrollTop = out.scrollHeight; },
      status: d => setStatus(d.msg),
      erro:   d => { out.textContent = `⚠ ${d.msg}`; },
    });
  } catch (err) {
    if (err.name !== 'AbortError') out.textContent = `⚠ ${err.message}`;
  }
}

function stopTranslation() {
  if (S.transCtrl) {
    S.transCtrl.abort();
    S.transCtrl = null;
    document.getElementById('trans-output').textContent += '\n\n[Interrompido]';
  }
}

// ── dicionários offline ───────────────────────────────────────────────────────

function lookupDict(modo) {
  const palavra = (window.getSelection().toString().trim() || S.savedSel).split(/\s+/)[0];
  if (!palavra) {
    document.getElementById('trans-output').textContent = '⚠ Selecione uma palavra primeiro.';
    return;
  }
  fetch(`/api/dict/${modo}?q=${enc(palavra)}`)
    .then(r => r.json())
    .then(d => {
      const out = document.getElementById('trans-output');
      if (d.erro) { out.textContent = `⚠ ${d.erro}`; return; }
      out.textContent = `[${modo.toUpperCase()}] ${palavra}\n\n${d.resultado || '(sem resultado)'}`;
    })
    .catch(err => {
      document.getElementById('trans-output').textContent = `⚠ ${err.message}`;
    });
}

// ── pronúncia ─────────────────────────────────────────────────────────────────

async function pronunciar(texto) {
  if (!texto) return;
  const voz       = document.getElementById('sel-voz')?.value || 'it-IT-DiegoNeural';
  const variante  = document.getElementById('sel-variante')?.value || 'classico';
  const audio     = document.getElementById('audio-out');

  setStatus('🔊 A gerar áudio…');
  try {
    const resp = await fetch('/api/pronunciar', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({texto, voz, variante, velocidade: 1.0}),
    });
    if (!resp.ok) {
      const d = await resp.json().catch(() => ({}));
      setStatus(`⚠ Pronúncia: ${d.erro || resp.statusText}`);
      return;
    }
    const blob = await resp.blob();
    if (audio) {
      audio.style.display = 'inline';
      audio.src = URL.createObjectURL(blob);
      audio.play();
    }
    setStatus('🔊 A reproduzir…');
  } catch (err) {
    setStatus(`⚠ Pronúncia: ${err.message}`);
  }
}

function pronunciarSeleccao() {
  const texto = window.getSelection().toString().trim() || S.savedSel;
  if (!texto) { setStatus('⚠ Selecione texto para pronunciar.'); return; }
  pronunciar(texto);
}

function pararPronuncia() {
  const audio = document.getElementById('audio-out');
  if (audio) { audio.pause(); audio.currentTime = 0; }
}

function pronunciarPercTexto() {
  const sel = window.getSelection().toString().trim();
  const txt = sel || document.getElementById('perc-texto')?.textContent.trim();
  pronunciar(txt);
}

function pronunciarCdliTexto() {
  const atf = document.getElementById('cdli-atf')?.textContent.trim();
  if (!atf) return;
  pronunciar(atf.slice(0, 1000));
}

// ── Gemini key dialog ─────────────────────────────────────────────────────────

function showGeminiKeyDialog() {
  document.getElementById('gemini-key-input').value = '';
  document.getElementById('gemini-dialog').style.display = 'flex';
  document.getElementById('gemini-key-input').focus();
}
function closeGeminiKeyDialog() {
  document.getElementById('gemini-dialog').style.display = 'none';
}
async function saveGeminiKey() {
  const chave = document.getElementById('gemini-key-input').value.trim();
  if (!chave) return;
  const resp = await fetch('/api/gemini_chave', {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify({chave}),
  });
  const d = await resp.json();
  setStatus(d.ok ? '✓ Chave Gemini guardada.' : `⚠ ${d.msg}`);
  closeGeminiKeyDialog();
}
document.getElementById('gemini-key-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') saveGeminiKey();
  if (e.key === 'Escape') closeGeminiKeyDialog();
});

// ── Perseus / Textos Online ───────────────────────────────────────────────────

function percLoadCatalog(forcar = false) {
  const lingua = document.getElementById('perc-lingua').value;
  const list   = document.getElementById('perc-works');
  list.innerHTML = '<li class="loading">A carregar…</li>';
  document.getElementById('perc-cat-status').textContent = '⏳ A carregar catálogo…';

  fetch(`/api/perseus/catalogo?lingua=${lingua}&forcar=${forcar ? 1 : 0}`)
    .then(r => r.json())
    .then(obras => {
      if (obras.erro) throw new Error(obras.erro);
      S.percObras = obras;
      percFilter('');
      document.getElementById('perc-cat-status').textContent = `✓ ${obras.length} edições.`;
    })
    .catch(err => {
      document.getElementById('perc-cat-status').textContent = `⚠ ${err.message}`;
    });
}

function percFilter(q) {
  const list = document.getElementById('perc-works');
  list.innerHTML = '';
  (S.percObras || [])
    .filter(o => !q || o.display.toLowerCase().includes(q.toLowerCase()))
    .forEach(o => {
      const li = document.createElement('li');
      li.textContent = o.display;
      li.title = o.display;
      li.addEventListener('click', () => percSelectWork(o));
      list.appendChild(li);
    });
}

document.getElementById('perc-filter')?.addEventListener('input', e => onlineFilter(e.target.value));

function percSelectWork(obra) {
  S.percObraURN = obra.edicao_urn;
  document.querySelectorAll('.perc-works-list li').forEach(li =>
    li.classList.toggle('active', li.textContent === obra.display));
  document.getElementById('perc-obra-sel').innerHTML =
    `<b>${esc(obra.display)}</b><br><small>${esc(obra.edicao_urn)}</small>`;

  const refsEl = document.getElementById('perc-refs');
  refsEl.innerHTML = '<option>(a carregar…)</option>';
  setPercBtn('btn-perc-obra', false);
  document.getElementById('perc-pass-status').textContent = 'A carregar referências…';

  fetch(`/api/perseus/refs?urn=${enc(obra.edicao_urn)}`)
    .then(r => r.json())
    .then(refs => {
      if (refs.erro) throw new Error(refs.erro);
      S.percRefs   = refs;
      refsEl.innerHTML = '';
      refs.forEach(urn => {
        const opt = document.createElement('option');
        opt.value       = urn;
        opt.textContent = urn.split(':').pop();
        refsEl.appendChild(opt);
      });
      const has = refs.length > 0;
      setPercBtn('btn-perc-obra', has);
      setPercBtn('btn-perc-pron', has);
      document.getElementById('perc-pass-status').textContent =
        has ? `✓ ${refs.length} referências.` : 'Sem referências.';
      if (has) percLoadPassagem(refs[0]);
    })
    .catch(err => {
      document.getElementById('perc-pass-status').textContent = `⚠ ${err.message}`;
    });
}

function percLoadPassagem(urnOverride) {
  const urn = urnOverride || document.getElementById('perc-refs').value;
  if (!urn) return;
  const txt = document.getElementById('perc-texto');
  txt.textContent = '⏳ A carregar…';

  fetch(`/api/perseus/passagem?urn=${enc(urn)}`)
    .then(r => r.json())
    .then(d => {
      if (d.erro) throw new Error(d.erro);
      txt.textContent = d.texto || '';
      const words = (d.texto || '').trim().split(/\s+/).filter(Boolean).length;
      document.getElementById('perc-pass-status').textContent = `✓ ${words} palavras.`;
      const has = !!d.texto;
      setPercBtn('btn-perc-traduzir', has);
      setPercBtn('btn-perc-copiar', has);
      setPercBtn('btn-perc-pron', has);
    })
    .catch(err => { txt.textContent = `⚠ ${err.message}`; });
}

function percObraCompleta() {
  if (!S.percObraURN) return;
  if (S.percObraES) S.percObraES.close();

  const txt = document.getElementById('perc-texto');
  const n   = S.percRefs.length;
  txt.textContent = `⏳ A descarregar obra completa… 0/${n}`;
  setPercBtn('btn-perc-obra', false);

  S.percObraES = new EventSource(`/api/perseus/obra?urn=${enc(S.percObraURN)}`);
  S.percObraES.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    document.getElementById('perc-pass-status').textContent = `⏳ ${d.atual}/${d.total}…`;
  });
  S.percObraES.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    txt.textContent = d.texto;
    setPercBtn('btn-perc-obra', true);
    setPercBtn('btn-perc-traduzir', true);
    setPercBtn('btn-perc-copiar', true);
    setPercBtn('btn-perc-pron', true);
    const words = d.texto.trim().split(/\s+/).filter(Boolean).length;
    document.getElementById('perc-pass-status').textContent = `✓ ${words} palavras.`;
    S.percObraES.close(); S.percObraES = null;
  });
  S.percObraES.addEventListener('erro', e => {
    txt.textContent = `⚠ ${JSON.parse(e.data).msg}`;
    setPercBtn('btn-perc-obra', true);
    S.percObraES.close(); S.percObraES = null;
  });
}

async function percTraduzir() {
  const sel   = window.getSelection().toString().trim();
  const texto = sel || document.getElementById('perc-texto').textContent.trim();
  if (!texto) return;

  const fonte  = onlineFonte();
  const lingua = fonte !== 'perseus' ? 'hbo' :
                 (document.getElementById('perc-lingua').value === 'grc' ? 'grc' : 'la');
  const modelo = document.getElementById('sel-gemini-modelo')?.value || '';
  const outEl  = document.getElementById('perc-trans-output');
  outEl.style.display = 'block';
  outEl.textContent   = '🌟 Gemini…\n\n';

  if (S.transCtrl) S.transCtrl.abort();
  S.transCtrl = new AbortController();

  try {
    const resp = await fetch('/api/traduzir', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({texto, lingua, motor: 'gemini', modelo}),
      signal:  S.transCtrl.signal,
    });
    await readSSEStream(resp.body, {
      chunk: d => { outEl.textContent += d.text; outEl.scrollTop = outEl.scrollHeight; },
      erro:  d => { outEl.textContent = `⚠ ${d.msg}`; },
    });
  } catch (err) {
    if (err.name !== 'AbortError') outEl.textContent = `⚠ ${err.message}`;
  }
}

function percCopiar() {
  const texto = document.getElementById('perc-texto').textContent;
  navigator.clipboard.writeText(texto).then(() => {
    document.getElementById('perc-pass-status').textContent = '✓ Copiado.';
  });
}

function setPercBtn(id, enabled) {
  const el = document.getElementById(id);
  if (el) el.disabled = !enabled;
}

// ── Textos Online: fonte dispatcher ──────────────────────────────────────────

function onlineFonte() {
  return document.getElementById('online-fonte')?.value || 'perseus';
}

function onlineFonteChange() {
  const fonte = onlineFonte();
  document.getElementById('perc-lingua-wrap').style.display  = fonte === 'perseus'  ? '' : 'none';
  document.getElementById('sefaria-cat-wrap').style.display  = fonte === 'sefaria'  ? '' : 'none';
  const abWrap = document.getElementById('apibible-wrap');
  if (abWrap) abWrap.style.display = fonte === 'apibible' ? '' : 'none';

  const textoEl = document.getElementById('perc-texto');
  textoEl.classList.toggle('rtl', fonte !== 'perseus' && fonte !== 'll');
  textoEl.classList.toggle('alpheios-enabled', fonte === 'll');
  if (fonte === 'll') textoEl.setAttribute('lang', 'lat');
  else textoEl.removeAttribute('lang');

  document.getElementById('perc-obra-sel').innerHTML = '<em>(nenhuma obra seleccionada)</em>';
  document.getElementById('perc-refs').innerHTML = '';
  textoEl.textContent = '';
  document.getElementById('perc-pass-status').textContent = '';
  ['btn-perc-obra','btn-perc-traduzir','btn-perc-copiar','btn-perc-pron'].forEach(id => setPercBtn(id, false));

  if (fonte === 'perseus') percLoadCatalog();
  else if (fonte === 'll') llLoadCatalog();
  else if (fonte === 'sefaria') sefariaLoadCatalog();
  else if (fonte === 'apibible') apibibleInit();
}

function reloadCurrentCatalog() {
  const fonte = onlineFonte();
  if (fonte === 'perseus') percLoadCatalog(true);
  else if (fonte === 'll') llLoadCatalog(true);
  else if (fonte === 'sefaria') sefariaLoadCatalog(true);
  else if (fonte === 'apibible') apibibleLoadBiblias(true);
}

function onlineFilter(q) {
  const fonte = onlineFonte();
  if (fonte === 'sefaria') sefariaFilter(q);
  else if (fonte === 'apibible') apibibleFilter(q);
  else if (fonte === 'll') llFilter(q);
  else percFilter(q);
}

function onPercRefsChange() {
  const fonte = onlineFonte();
  if (fonte === 'sefaria') sefariaLoadPassagem();
  else if (fonte === 'apibible') apibibleLoadPassagem();
  else if (fonte === 'll') llLoadTexto();
  else percLoadPassagem();
}

function onlineObraCompleta() {
  const fonte = onlineFonte();
  if (fonte === 'sefaria') sefariaObraCompleta();
  else if (fonte === 'apibible') { /* não implementado */ }
  else if (fonte === 'll') llLoadTexto();
  else percObraCompleta();
}

// ── Sefaria ───────────────────────────────────────────────────────────────────

function sefariaLoadCatalog(forcar = false) {
  const cat  = document.getElementById('sefaria-cat')?.value || 'Tanakh';
  const list = document.getElementById('perc-works');
  list.innerHTML = '<li class="loading">A carregar…</li>';
  document.getElementById('perc-cat-status').textContent = '⏳ A carregar Sefaria…';

  fetch(`/api/sefaria/catalogo?categoria=${enc(cat)}&forcar=${forcar ? 1 : 0}`)
    .then(r => r.json())
    .then(obras => {
      if (obras.erro) throw new Error(obras.erro);
      S.percObras = obras;
      sefariaFilter('');
      document.getElementById('perc-cat-status').textContent = `✓ ${obras.length} obras.`;
    })
    .catch(err => {
      list.innerHTML = '';
      document.getElementById('perc-cat-status').textContent = `⚠ ${err.message}`;
    });
}

function sefariaFilter(q) {
  const list = document.getElementById('perc-works');
  list.innerHTML = '';
  (S.percObras || [])
    .filter(o => !q || o.display.toLowerCase().includes(q.toLowerCase()) ||
                       o.titulo.toLowerCase().includes(q.toLowerCase()))
    .forEach(o => {
      const li = document.createElement('li');
      li.textContent = o.display;
      li.title       = o.titulo;
      li.addEventListener('click', () => sefariaSelectWork(o));
      list.appendChild(li);
    });
}

function sefariaSelectWork(obra) {
  document.querySelectorAll('.perc-works-list li').forEach(li =>
    li.classList.toggle('active', li.title === obra.titulo));
  document.getElementById('perc-obra-sel').innerHTML = `<b>${esc(obra.display)}</b>`;

  const refsEl = document.getElementById('perc-refs');
  refsEl.innerHTML = '<option>(a carregar…)</option>';
  setPercBtn('btn-perc-obra', false);

  fetch(`/api/sefaria/refs?titulo=${enc(obra.titulo)}`)
    .then(r => r.json())
    .then(refs => {
      if (refs.erro) throw new Error(refs.erro);
      S.percRefs = refs;
      refsEl.innerHTML = '';
      refs.forEach(ref => {
        const opt = document.createElement('option');
        opt.value       = ref;
        opt.textContent = ref.split(' ').pop();
        refsEl.appendChild(opt);
      });
      const has = refs.length > 0;
      setPercBtn('btn-perc-obra', has);
      document.getElementById('perc-pass-status').textContent =
        has ? `✓ ${refs.length} capítulos.` : 'Sem capítulos.';
      if (has) sefariaLoadPassagem(refs[0]);
    })
    .catch(err => {
      document.getElementById('perc-pass-status').textContent = `⚠ ${err.message}`;
    });
}

function sefariaLoadPassagem(refOverride) {
  const ref = refOverride || document.getElementById('perc-refs').value;
  if (!ref) return;
  const txt = document.getElementById('perc-texto');
  txt.textContent = '⏳ A carregar…';

  fetch(`/api/sefaria/passagem?ref=${enc(ref)}`)
    .then(r => r.json())
    .then(d => {
      if (d.erro) throw new Error(d.erro);
      const heb   = d.texto_heb || '';
      const words = heb.trim().split(/\s+/).filter(Boolean).length;
      txt.textContent = heb;
      document.getElementById('perc-pass-status').textContent =
        `✓ ${d.ref_heb || d.ref} — ${words} palavras.`;
      setPercBtn('btn-perc-traduzir', !!heb);
      setPercBtn('btn-perc-copiar',   !!heb);
    })
    .catch(err => { txt.textContent = `⚠ ${err.message}`; });
}

function sefariaObraCompleta() {
  const titulo = (document.getElementById('perc-obra-sel').querySelector('b')?.textContent || '')
                   .match(/\(([^)]+)\)/)?.[1];
  if (!titulo) return;
  if (S.percObraES) S.percObraES.close();

  const txt = document.getElementById('perc-texto');
  txt.textContent = `⏳ A descarregar…`;
  setPercBtn('btn-perc-obra', false);

  S.percObraES = new EventSource(`/api/sefaria/obra?titulo=${enc(titulo)}`);
  S.percObraES.addEventListener('progress', e => {
    const d = JSON.parse(e.data);
    document.getElementById('perc-pass-status').textContent = `⏳ ${d.atual}/${d.total}…`;
  });
  S.percObraES.addEventListener('done', e => {
    const d = JSON.parse(e.data);
    txt.textContent = d.texto;
    setPercBtn('btn-perc-obra', true);
    setPercBtn('btn-perc-traduzir', true);
    setPercBtn('btn-perc-copiar', true);
    S.percObraES.close(); S.percObraES = null;
  });
  S.percObraES.addEventListener('erro', e => {
    txt.textContent = `⚠ ${JSON.parse(e.data).msg}`;
    setPercBtn('btn-perc-obra', true);
    S.percObraES.close(); S.percObraES = null;
  });
}

// ── Latin Library (local) ─────────────────────────────────────────────────────

function llLoadCatalog(forcar = false) {
  const list = document.getElementById('perc-works');
  list.innerHTML = '<li class="loading">A carregar…</li>';
  document.getElementById('perc-cat-status').textContent = '⏳ A carregar Latin Library…';

  fetch(`/api/online/ll/catalogo?forcar=${forcar ? 1 : 0}`)
    .then(r => r.json())
    .then(obras => {
      if (obras.erro) throw new Error(obras.erro);
      S.llObras = obras;
      llFilter('');
      document.getElementById('perc-cat-status').textContent = `✓ ${obras.length} obras.`;
    })
    .catch(err => {
      list.innerHTML = '';
      document.getElementById('perc-cat-status').textContent = `⚠ ${err.message}`;
    });
}

function llFilter(q) {
  const list = document.getElementById('perc-works');
  list.innerHTML = '';
  const lq = q.toLowerCase();
  (S.llObras || [])
    .filter(o => !q || o.author.toLowerCase().includes(lq) || o.work.toLowerCase().includes(lq) || o.title.toLowerCase().includes(lq))
    .forEach(o => {
      const li = document.createElement('li');
      li.textContent = o.author ? `${o.author} — ${o.work || o.title}` : (o.work || o.title || o.id);
      li.title = o.id;
      li.addEventListener('click', () => llSelectWork(o));
      list.appendChild(li);
    });
}

function llSelectWork(obra) {
  S.llSelWork = obra;
  document.querySelectorAll('.perc-works-list li').forEach(li =>
    li.classList.toggle('active', li.title === obra.id));
  const label = obra.author ? `${obra.author} — ${obra.work || obra.title}` : (obra.work || obra.title || obra.id);
  document.getElementById('perc-obra-sel').innerHTML =
    `<b>${esc(label)}</b><br><small>${esc(obra.id)}</small>`;

  const refsEl = document.getElementById('perc-refs');
  refsEl.innerHTML = '<option value="full">Texto completo</option>';
  setPercBtn('btn-perc-obra', true);
  document.getElementById('perc-pass-status').textContent = '';
  llLoadTexto();
}

function llLoadTexto() {
  if (!S.llSelWork) return;
  const textoEl = document.getElementById('perc-texto');
  textoEl.textContent = '⏳…';
  document.getElementById('perc-pass-status').textContent = 'A carregar…';

  fetch(`/api/online/ll/texto?id=${enc(S.llSelWork.id)}`)
    .then(r => r.json())
    .then(d => {
      if (d.erro) throw new Error(d.erro);
      textoEl.textContent = d.texto;
      document.getElementById('perc-pass-status').textContent = '';
      ['btn-perc-traduzir','btn-perc-copiar','btn-perc-pron'].forEach(id => setPercBtn(id, true));
    })
    .catch(err => {
      textoEl.textContent = '';
      document.getElementById('perc-pass-status').textContent = `⚠ ${err.message}`;
    });
}

// ── API.Bible ─────────────────────────────────────────────────────────────────

function apibibleInit() {
  document.getElementById('perc-cat-status').textContent = '⏳ A verificar chave…';
  fetch('/api/apibible/chave')
    .then(r => r.json())
    .then(d => {
      if (!d.tem_chave) {
        document.getElementById('perc-cat-status').textContent = '⚠ Configure a chave API.Bible (🔑).';
        return;
      }
      apibibleLoadBiblias();
    });
}

function apibibleLoadBiblias(forcar = false) {
  document.getElementById('perc-cat-status').textContent = '⏳ A carregar Bíblias…';
  fetch(`/api/apibible/biblias?forcar=${forcar ? 1 : 0}`)
    .then(r => r.json())
    .then(bibles => {
      if (bibles.erro) throw new Error(bibles.erro);
      const sel = document.getElementById('apibible-biblia');
      sel.innerHTML = '';
      bibles.forEach(b => {
        const opt = document.createElement('option');
        opt.value = b.id; opt.textContent = b.nome;
        sel.appendChild(opt);
      });
      if (bibles.length > 0) apibibleLoadBooks();
      else document.getElementById('perc-cat-status').textContent = 'Sem Bíblias hebraicas.';
    })
    .catch(err => {
      document.getElementById('perc-cat-status').textContent = `⚠ ${err.message}`;
    });
}

function apibibleLoadBooks() {
  const bibliaId = document.getElementById('apibible-biblia')?.value;
  if (!bibliaId) return;
  const list = document.getElementById('perc-works');
  list.innerHTML = '<li class="loading">A carregar…</li>';

  fetch(`/api/apibible/livros?biblia_id=${enc(bibliaId)}`)
    .then(r => r.json())
    .then(livros => {
      if (livros.erro) throw new Error(livros.erro);
      S.percObras = livros.map(l => ({...l, display: l.nome}));
      apibibleFilter('');
      document.getElementById('perc-cat-status').textContent = `✓ ${livros.length} livros.`;
    })
    .catch(err => {
      list.innerHTML = '';
      document.getElementById('perc-cat-status').textContent = `⚠ ${err.message}`;
    });
}

function apibibleFilter(q) {
  const list = document.getElementById('perc-works');
  list.innerHTML = '';
  (S.percObras || [])
    .filter(o => !q || o.display.toLowerCase().includes(q.toLowerCase()))
    .forEach(o => {
      const li = document.createElement('li');
      li.textContent = o.display;
      li.addEventListener('click', () => apibibleSelectBook(o.id));
      list.appendChild(li);
    });
}

function apibibleSelectBook(livroId) {
  const bibliaId = document.getElementById('apibible-biblia')?.value;
  const obra = S.percObras.find(o => o.id === livroId);
  document.querySelectorAll('.perc-works-list li').forEach(li =>
    li.classList.toggle('active', li.textContent === (obra?.display || '')));
  document.getElementById('perc-obra-sel').innerHTML = `<b>${esc(obra?.nome || livroId)}</b>`;

  const refsEl = document.getElementById('perc-refs');
  refsEl.innerHTML = '<option>(a carregar…)</option>';

  fetch(`/api/apibible/capitulos?biblia_id=${enc(bibliaId)}&livro_id=${enc(livroId)}`)
    .then(r => r.json())
    .then(caps => {
      if (caps.erro) throw new Error(caps.erro);
      S.percRefs = caps.map(c => c.id);
      refsEl.innerHTML = '';
      caps.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id; opt.textContent = c.numero;
        refsEl.appendChild(opt);
      });
      const has = caps.length > 0;
      document.getElementById('perc-pass-status').textContent =
        has ? `✓ ${caps.length} capítulos.` : 'Sem capítulos.';
      if (has) apibibleLoadPassagem(caps[0].id);
    })
    .catch(err => {
      document.getElementById('perc-pass-status').textContent = `⚠ ${err.message}`;
    });
}

function apibibleLoadPassagem(passIdOverride) {
  const bibliaId = document.getElementById('apibible-biblia')?.value;
  const passId   = passIdOverride || document.getElementById('perc-refs').value;
  if (!bibliaId || !passId) return;

  const txt = document.getElementById('perc-texto');
  txt.textContent = '⏳ A carregar…';

  fetch(`/api/apibible/passagem?biblia_id=${enc(bibliaId)}&passagem_id=${enc(passId)}`)
    .then(r => r.json())
    .then(d => {
      if (d.erro) throw new Error(d.erro);
      txt.textContent = d.texto || '';
      const words = (d.texto || '').trim().split(/\s+/).filter(Boolean).length;
      document.getElementById('perc-pass-status').textContent = `✓ ${d.ref} — ${words} palavras.`;
      setPercBtn('btn-perc-traduzir', !!d.texto);
      setPercBtn('btn-perc-copiar',   !!d.texto);
    })
    .catch(err => { txt.textContent = `⚠ ${err.message}`; });
}

function showApibibleKeyDialog() {
  const el = document.getElementById('apibible-key-input');
  if (el) el.value = '';
  document.getElementById('apibible-dialog').style.display = 'flex';
  if (el) el.focus();
}
function closeApibibleKeyDialog() {
  document.getElementById('apibible-dialog').style.display = 'none';
}
async function saveApibibleKey() {
  const chave = document.getElementById('apibible-key-input').value.trim();
  if (!chave) return;
  const resp = await fetch('/api/apibible/chave', {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify({chave}),
  });
  const d = await resp.json();
  setStatus(d.ok ? '✓ Chave API.Bible guardada.' : `⚠ ${d.msg}`);
  closeApibibleKeyDialog();
  if (d.ok && onlineFonte() === 'apibible') apibibleLoadBiblias();
}
document.getElementById('apibible-key-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') saveApibibleKey();
  if (e.key === 'Escape') closeApibibleKeyDialog();
});

// ── CDLI ──────────────────────────────────────────────────────────────────────

document.getElementById('cdli-q')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') cdliPesquisar();
});

function cdliPesquisar() {
  const q      = (document.getElementById('cdli-q')?.value || '').trim();
  const lang   = document.getElementById('cdli-lang')?.value || '';
  const limite = document.getElementById('cdli-limite')?.value || 50;
  const list   = document.getElementById('cdli-list');
  const status = document.getElementById('cdli-status');

  list.innerHTML = '<li class="loading">A pesquisar…</li>';
  status.textContent = '⏳ A consultar CDLI…';
  cdliClearDetail();

  fetch(`/api/cdli/pesquisar?q=${enc(q)}&lang=${enc(lang)}&limite=${limite}`)
    .then(r => r.json())
    .then(items => {
      list.innerHTML = '';
      if (!items.length) {
        status.textContent = 'Sem resultados.';
        return;
      }
      if (items[0]?.erro) {
        status.textContent = `⚠ ${items[0].erro}`;
        return;
      }
      S.cdliData = items;
      items.forEach((item, i) => {
        const li = document.createElement('li');
        li.textContent = item.display_name || item.id;
        li.title = [item.period, item.provenience, item.genre].filter(Boolean).join(' · ');
        li.addEventListener('click', () => cdliSelectItem(i));
        list.appendChild(li);
      });
      status.textContent = `✓ ${items.length} artefatos.`;
      if (items.length > 0) cdliSelectItem(0);
    })
    .catch(err => {
      list.innerHTML = '';
      status.textContent = `⚠ ${err.message}`;
    });
}

function cdliSelectItem(index) {
  S.cdliSel = index;
  document.querySelectorAll('#cdli-list li').forEach((li, i) =>
    li.classList.toggle('active', i === index));

  const item = S.cdliData[index];
  if (!item) return;

  document.getElementById('cdli-detalhe-titulo').textContent =
    `${item.display_name || item.id}  (${item.pnum || item.id})`;
  document.getElementById('cdli-detalhe-meta').innerHTML =
    [item.period && `<span>Período: ${esc(item.period)}</span>`,
     item.provenience && `<span>Procedência: ${esc(item.provenience)}</span>`,
     item.genre && `<span>Gênero: ${esc(item.genre)}</span>`,
     item.primary_publication && `<span>Pub.: ${esc(item.primary_publication)}</span>`,
     item.lang && `<span>Língua: ${esc(item.lang)}</span>`,
    ].filter(Boolean).join(' · ');

  // Link "Ver no CDLI"
  const verBtn = document.getElementById('btn-cdli-ver');
  if (verBtn && item.url_cdli) {
    verBtn.href = item.url_cdli;
    verBtn.style.display = 'inline-block';
  }

  const atfEl = document.getElementById('cdli-atf');
  atfEl.textContent = item.atf_text || '(a carregar transliteração…)';

  ['btn-cdli-traduzir','btn-cdli-copiar','btn-cdli-pron'].forEach(id => setPercBtn(id, true));
  document.getElementById('cdli-trans-output').style.display = 'none';

  if (!item.atf_text && item.id) {
    fetch(`/api/cdli/artefato/${enc(item.id)}`)
      .then(r => r.json())
      .then(d => {
        if (d.erro) { atfEl.textContent = '(sem transliteração disponível)'; return; }
        const insc = d.inscription || {};
        const atf = insc.atf || d.atf || '';
        if (atf) {
          atfEl.textContent = atf;
          S.cdliData[index].atf_text = atf;
        } else {
          atfEl.textContent = '(transliteração não disponível para este artefato)';
        }
      })
      .catch(() => { atfEl.textContent = '(erro ao carregar detalhes)'; });
  }
}

function cdliClearDetail() {
  document.getElementById('cdli-detalhe-titulo').innerHTML = '<em>(nenhum artefato selecionado)</em>';
  document.getElementById('cdli-detalhe-meta').textContent = '';
  document.getElementById('cdli-atf').textContent = '';
  const verBtn = document.getElementById('btn-cdli-ver');
  if (verBtn) verBtn.style.display = 'none';
  ['btn-cdli-traduzir','btn-cdli-copiar','btn-cdli-pron'].forEach(id => setPercBtn(id, false));
  document.getElementById('cdli-trans-output').style.display = 'none';
}

function cdliLoadObrasNotaveis() {
  fetch('/api/cdli/obras_notaveis')
    .then(r => r.json())
    .then(obras => {
      const container = document.getElementById('cdli-obras-btns');
      if (!container) return;
      container.innerHTML = '';
      obras.forEach(o => {
        const btn = document.createElement('button');
        btn.className   = 'cdli-obra-btn';
        btn.textContent = o.nome;
        btn.title       = `Pesquisar: ${o.q}  [${o.lang}]`;
        btn.addEventListener('click', () => {
          document.getElementById('cdli-q').value = o.q;
          const langSel = document.getElementById('cdli-lang');
          if (langSel) {
            const opt = Array.from(langSel.options).find(x => x.value === o.lang);
            if (opt) langSel.value = o.lang;
          }
          cdliPesquisar();
        });
        container.appendChild(btn);
      });
    })
    .catch(() => {
      const c = document.getElementById('cdli-obras-btns');
      if (c) c.innerHTML = '';
    });
}

async function cdliTraduzir() {
  const texto = document.getElementById('cdli-atf')?.textContent.trim();
  if (!texto) return;
  const modelo = document.getElementById('sel-gemini-modelo')?.value || '';
  const outEl  = document.getElementById('cdli-trans-output');
  outEl.style.display = 'block';
  outEl.textContent   = '🌟 Gemini…\n\n';

  if (S.transCtrl) S.transCtrl.abort();
  S.transCtrl = new AbortController();

  try {
    const resp = await fetch('/api/traduzir', {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify({texto: texto.slice(0, 3000), lingua: 'sux', motor: 'gemini', modelo}),
      signal:  S.transCtrl.signal,
    });
    await readSSEStream(resp.body, {
      chunk: d => { outEl.textContent += d.text; outEl.scrollTop = outEl.scrollHeight; },
      erro:  d => { outEl.textContent = `⚠ ${d.msg}`; },
    });
  } catch (err) {
    if (err.name !== 'AbortError') outEl.textContent = `⚠ ${err.message}`;
  }
}

function cdliCopiar() {
  const atf = document.getElementById('cdli-atf')?.textContent || '';
  navigator.clipboard.writeText(atf).then(() => {
    document.getElementById('cdli-status').textContent = '✓ ATF copiado.';
  });
}

// ── utilitários ───────────────────────────────────────────────────────────────

function enc(s) { return encodeURIComponent(s); }
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function readSSEStream(body, handlers) {
  const reader  = body.getReader();
  const decoder = new TextDecoder();
  let buf = '';

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buf += decoder.decode(value, {stream: true});
    const parts = buf.split('\n\n');
    buf = parts.pop();
    for (const block of parts) {
      let eventType = 'message', dataStr = '';
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        if (line.startsWith('data: '))  dataStr   = line.slice(6);
      }
      if (!dataStr) continue;
      try {
        const data = JSON.parse(dataStr);
        handlers[eventType]?.(data);
      } catch { /* ignore */ }
    }
  }
}

// ── init ──────────────────────────────────────────────────────────────────────

// Auto-initialize on page load since Textos Online is the default tab
(function initOnlineTab() {
  const fonte = onlineFonte();
  if (fonte === 'll') llLoadCatalog();
  else if (fonte === 'sefaria') sefariaLoadCatalog();
  else if (fonte === 'apibible') apibibleInit();
  else if (fonte === 'perseus') percLoadCatalog();
})();

document.querySelector('[data-tab="tab-cuneiforme"]')?.addEventListener('click', () => {
  cdliLoadObrasNotaveis();
}, {once: true});
