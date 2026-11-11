// Small glue around htmx: toasts, the modal, and the assistant composer.
(() => {
  const modal = () => document.getElementById('modal');
  let toastTimer;
  function toast(msg) {
    const t = document.getElementById('toast');
    if (!t || !msg) return;
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
  }
  function closeModal() { const m = modal(); if (m) m.innerHTML = ''; }

  document.body.addEventListener('compass:toast', e => toast(typeof e.detail === 'string' ? e.detail : e.detail.value));
  document.body.addEventListener('compass:changed', closeModal);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    // Enter sends the assistant message; Shift+Enter adds a line.
    if (e.key === 'Enter' && !e.shiftKey && e.target.id === 'id_text') { e.preventDefault(); e.target.form.requestSubmit(); }
  });
  document.addEventListener('click', e => {
    if (e.target.classList && e.target.classList.contains('modal-wrap')) closeModal();
    if (e.target.closest('[data-close-modal]')) closeModal();
    const s = e.target.closest('[data-suggest]');
    if (s) {
      const box = document.getElementById('id_text');
      if (!box) return;
      box.value = s.dataset.suggest;
      if (s.dataset.fill) { box.focus(); return; }
      box.form.requestSubmit();
    }
    const chip = e.target.closest('[data-minutes]');
    if (chip) { const f = document.getElementById('id_minutes'); if (f) f.value = chip.dataset.minutes; }
  });
  // Show the user's message right away while the assistant thinks.
  document.addEventListener('htmx:beforeRequest', e => {
    const form = e.detail.elt;
    if (form.id !== 'ask-form') return;
    const box = form.querySelector('#id_text');
    const text = box && box.value.trim();
    if (!text) { e.preventDefault(); return; }
    const thread = document.getElementById('thread');
    if (thread) {
      const div = document.createElement('div');
      div.className = 'msg user';
      div.textContent = text;
      thread.appendChild(div);
      thread.scrollTop = thread.scrollHeight;
    }
  });
  function scrollThread() { const th = document.getElementById('thread'); if (th) th.scrollTop = th.scrollHeight; }
  document.addEventListener('DOMContentLoaded', scrollThread);
  document.addEventListener('htmx:afterSettle', scrollThread);
  document.addEventListener('htmx:responseError', () => toast('Something went wrong. Try again.'));
  document.addEventListener('htmx:sendError', () => toast('You seem to be offline. Try again when you’re connected.'));
})();
