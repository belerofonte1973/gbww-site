/* GBWW — Great Books Web Application */

document.addEventListener('DOMContentLoaded', function () {

  // ── Sidebar: highlight active topic on scroll ───────────────────────────────
  const activeLink = document.querySelector('.sidebar-link.active');
  if (activeLink) {
    activeLink.scrollIntoView({ block: 'nearest' });
  }

  // ── Passage: inline preview on ref hover ───────────────────────────────────
  const refLinks = document.querySelectorAll('a[data-vol][data-marker]');
  let previewTimeout;
  let activePopover = null;

  refLinks.forEach(link => {
    link.addEventListener('mouseenter', function (e) {
      const vol = this.dataset.vol;
      const marker = this.dataset.marker;
      previewTimeout = setTimeout(() => fetchPreview(this, vol, marker), 300);
    });
    link.addEventListener('mouseleave', function () {
      clearTimeout(previewTimeout);
      if (activePopover) {
        activePopover.remove();
        activePopover = null;
      }
    });
  });

  function fetchPreview(anchor, vol, marker) {
    fetch(`/api/passage/${vol}/${marker}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data || !data.text) return;
        const pop = document.createElement('div');
        pop.className = 'passage-popover';
        pop.innerHTML = `<div class="pop-header">${data.volume} · ${marker}</div>
          <div class="pop-text">${data.text.slice(0, 400)}…</div>`;
        document.body.appendChild(pop);
        const rect = anchor.getBoundingClientRect();
        pop.style.top = (rect.bottom + window.scrollY + 6) + 'px';
        pop.style.left = Math.min(rect.left + window.scrollX, window.innerWidth - 340) + 'px';
        activePopover = pop;
      })
      .catch(() => {});
  }

  // ── Topic page: tab state in URL hash ──────────────────────────────────────
  const tabEls = document.querySelectorAll('[data-bs-toggle="tab"]');
  if (tabEls.length) {
    // Restore from hash
    const hash = window.location.hash;
    if (hash) {
      const target = document.querySelector(`[data-bs-target="${hash}"]`);
      if (target) {
        bootstrap.Tab.getOrCreateInstance(target).show();
      }
    }
    tabEls.forEach(tab => {
      tab.addEventListener('shown.bs.tab', function (e) {
        history.replaceState(null, '', e.target.dataset.bsTarget);
      });
    });
  }

  // ── Search: auto-submit on type change ─────────────────────────────────────
  const typeSelect = document.querySelector('.search-type');
  if (typeSelect) {
    typeSelect.addEventListener('change', function () {
      const form = this.closest('form');
      if (form && form.querySelector('input[name="q"]').value.trim()) {
        form.submit();
      }
    });
  }

  // ── Passage text: double-click to search selection ─────────────────────────
  const passageBody = document.querySelector('.passage-text');
  if (passageBody) {
    passageBody.addEventListener('dblclick', function () {
      const sel = window.getSelection().toString().trim();
      if (sel.length > 3 && sel.length < 100) {
        window.location.href = `/search?q=${encodeURIComponent(sel)}&type=text`;
      }
    });
  }

  // ── Back-to-top button ──────────────────────────────────────────────────────
  const backBtn = document.getElementById('backToTop');
  if (backBtn) {
    window.addEventListener('scroll', () => {
      backBtn.style.display = window.scrollY > 400 ? 'flex' : 'none';
    });
    backBtn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
  }

});
