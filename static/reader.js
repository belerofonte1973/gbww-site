/* reader.js — interactive morphological popup for Textos Clássicos */

(function () {
  'use strict';

  const popup   = document.getElementById('morph-popup');
  const overlay = document.getElementById('popup-overlay');
  if (!popup) return;

  const popupText   = document.getElementById('popup-text');
  const popupLemma  = document.getElementById('popup-lemma');
  const popupDesc   = document.getElementById('popup-desc');
  const btnLsj      = document.getElementById('btn-lsj');
  const btnStrongs  = document.getElementById('btn-strongs');
  const lsjEntry    = document.getElementById('lsj-entry');
  const btnClose    = document.getElementById('popup-close');

  // Detect corpus language from the text container
  const textDiv  = document.querySelector('.verse-list') || document.querySelector('.lit-text-body');
  const lang     = textDiv ? (textDiv.dataset.lang || 'grc') : 'grc';
  const isHebrew  = lang === 'heb';
  const isSumerian = lang === 'sux';

  let selectedToken = null;
  let currentLemma  = null;
  let currentStrong = null;
  let lexLoaded     = false;

  // ── show/hide ──────────────────────────────────────────────────────────────

  function openPopup(token) {
    if (selectedToken) selectedToken.classList.remove('selected');
    selectedToken = token;
    token.classList.add('selected');

    const word   = token.dataset.word;
    const lemma  = token.dataset.lemma;
    const desc   = token.dataset.desc;
    const strong = token.dataset.strong || '';

    // Reset lexicon area when switching words
    if (lemma !== currentLemma || strong !== currentStrong) {
      lsjEntry.style.display = 'none';
      lsjEntry.innerHTML = '';
      if (btnLsj)     { btnLsj.disabled = false;    btnLsj.textContent = 'LSJ ↗'; }
      if (btnStrongs) { btnStrongs.disabled = false; btnStrongs.textContent = 'Strong\'s ↗'; }
      lexLoaded = false;
    }
    currentLemma  = lemma;
    currentStrong = strong;

    // Populate popup content
    popupText.textContent = word;
    popupText.className   = 'popup-text' + (isHebrew ? ' popup-text--heb' : '');

    if (isHebrew) {
      popupLemma.textContent = strong ? strong + (lemma ? ' — ' + lemma : '') : lemma;
      popupLemma.className   = 'popup-lemma popup-lemma--heb';
    } else {
      popupLemma.textContent = lemma;
      popupLemma.className   = 'popup-lemma';
    }

    popupDesc.textContent = desc;
    popupDesc.className   = 'popup-desc' + (isHebrew ? ' popup-desc--heb' : '');

    if (btnLsj)     btnLsj.style.display     = (!isHebrew && !isSumerian) ? 'inline-block' : 'none';
    if (btnStrongs) btnStrongs.style.display  = isHebrew ? 'inline-block' : 'none';

    positionPopup(token);
    popup.style.display   = 'block';
    overlay.style.display = 'block';
    btnClose.focus();
  }

  function closePopup() {
    popup.style.display   = 'none';
    overlay.style.display = 'none';
    if (selectedToken) {
      selectedToken.classList.remove('selected');
      selectedToken = null;
    }
  }

  function positionPopup(token) {
    const rect = token.getBoundingClientRect();
    const pw   = popup.offsetWidth  || 280;
    const ph   = popup.offsetHeight || 200;
    const vw   = window.innerWidth;
    const vh   = window.innerHeight;

    let top  = rect.bottom + 8;
    let left = rect.left;

    if (left + pw > vw - 12) left = vw - pw - 12;
    if (left < 8)             left = 8;
    if (top + ph > vh - 12)   top  = rect.top - ph - 8;
    if (top < 8)              top  = 8;

    popup.style.top  = top  + 'px';
    popup.style.left = left + 'px';
  }

  // ── LSJ lookup (Greek) ────────────────────────────────────────────────────

  if (btnLsj) {
    btnLsj.addEventListener('click', function () {
      if (lexLoaded) {
        lsjEntry.style.display = lsjEntry.style.display === 'none' ? 'block' : 'none';
        return;
      }
      if (!currentLemma) return;

      btnLsj.disabled = true;
      btnLsj.textContent = 'A carregar…';
      lsjEntry.style.display = 'block';
      lsjEntry.innerHTML = '<em>A consultar Diogenes…</em>';

      fetch('/api/lsj/' + encodeURIComponent(currentLemma))
        .then(r => r.json())
        .then(data => {
          if (data.error) {
            lsjEntry.innerHTML = '<span class="lsj-error">Diogenes offline: ' + escHtml(data.error) + '</span>';
            btnLsj.textContent = 'LSJ ↗'; btnLsj.disabled = false; return;
          }
          if (!data.dictionary || data.dictionary.length === 0) {
            lsjEntry.innerHTML = '<span class="lsj-error">Sem entrada LSJ para <em>' + escHtml(currentLemma) + '</em>.</span>';
            btnLsj.textContent = 'LSJ ↗'; btnLsj.disabled = false; return;
          }
          let html = '';
          data.dictionary.forEach(function (d) {
            html += '<div class="lsj-headword">' + escHtml(d.headword) + '</div>';
            html += '<div class="lsj-body">'    + escHtml(d.entry)    + '</div>';
          });
          if (data.morphology && data.morphology.length > 0) {
            html += '<hr style="margin:8px 0;border-color:var(--border)">';
            data.morphology.forEach(function (m) {
              html += '<div style="font-size:.78rem;color:var(--muted)">'
                    + escHtml(m.lemma) + ' — ' + escHtml(m.description) + '</div>';
            });
          }
          lsjEntry.innerHTML = html;
          lexLoaded = true;
          btnLsj.textContent = 'LSJ ↗ (ocultar)';
          btnLsj.disabled = false;
        })
        .catch(function (err) {
          lsjEntry.innerHTML = '<span class="lsj-error">Erro: ' + escHtml(String(err)) + '</span>';
          btnLsj.textContent = 'LSJ ↗'; btnLsj.disabled = false;
        });
    });
  }

  // ── Strong's lookup (Hebrew) ──────────────────────────────────────────────

  if (btnStrongs) {
    btnStrongs.addEventListener('click', function () {
      if (lexLoaded) {
        lsjEntry.style.display = lsjEntry.style.display === 'none' ? 'block' : 'none';
        return;
      }
      if (!currentStrong) return;

      btnStrongs.disabled = true;
      btnStrongs.textContent = 'A carregar…';
      lsjEntry.style.display = 'block';
      lsjEntry.innerHTML = '<em>A consultar léxico…</em>';

      fetch('/api/strongs/' + encodeURIComponent(currentStrong))
        .then(r => r.json())
        .then(data => {
          if (data.error) {
            lsjEntry.innerHTML = '<span class="lsj-error">' + escHtml(data.error) + '</span>';
            btnStrongs.textContent = 'Strong\'s ↗'; btnStrongs.disabled = false; return;
          }
          let html = '<div class="strongs-num">' + escHtml(data.num) + '</div>';
          if (data.lemma_heb) {
            html += '<span style="font-family:var(--font-heb);font-size:1.2rem;direction:rtl">'
                  + escHtml(data.lemma_heb) + '</span> ';
          }
          if (data.xlit) {
            html += '<span class="strongs-xlit">(' + escHtml(data.xlit) + ')</span>';
          }
          if (data.definition) {
            html += '<div class="strongs-def">' + escHtml(data.definition) + '</div>';
          }
          lsjEntry.innerHTML = html;
          lexLoaded = true;
          btnStrongs.textContent = 'Strong\'s ↗ (ocultar)';
          btnStrongs.disabled = false;
        })
        .catch(function (err) {
          lsjEntry.innerHTML = '<span class="lsj-error">Erro: ' + escHtml(String(err)) + '</span>';
          btnStrongs.textContent = 'Strong\'s ↗'; btnStrongs.disabled = false;
        });
    });
  }

  // ── events ────────────────────────────────────────────────────────────────

  document.addEventListener('click', function (e) {
    const token = e.target.closest('.token');
    if (token) {
      e.stopPropagation();
      if (token === selectedToken && popup.style.display !== 'none') {
        closePopup();
      } else {
        openPopup(token);
      }
      return;
    }
    if (e.target === overlay) closePopup();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closePopup();
  });

  btnClose.addEventListener('click', function (e) {
    e.stopPropagation();
    closePopup();
  });

  // ── util ──────────────────────────────────────────────────────────────────

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

})();
