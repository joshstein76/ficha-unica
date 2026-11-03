/* Lía, the AI chat on agent sites. Vanilla JS, loaded with defer. Every piece of text from the server or the client goes in with
   textContent, never as markup. The thread token lives in sessionStorage only (per tab, per page); if storage is blocked the chat still works. */
(function () {
  'use strict';
  var root = document.getElementById('lia');
  if (!root || !window.fetch) return;
  var q = function (s) { return root.querySelector(s); };
  var fab = q('.lia-fab'), panel = q('.lia-panel'), log = q('.lia-log'), chat = q('.lia-f'), box = chat.querySelector('textarea'),
      go = chat.querySelector('.lia-s'), hp = q('.lia-hp'), cf = q('.lia-cf'), er = q('.lia-er'), html = document.documentElement;
  var ctx = root.getAttribute('data-l') || '', key = 'lia:' + ctx, token = '', busy = false, loaded = false, ty = null;
  var FALLBACK = 'Ahora mismo no puedo contestarte. Deja tus datos aquí abajo y te escribimos.';
  var fine = window.matchMedia && matchMedia('(pointer:fine)').matches;

  function mem(v) {
    try {
      if (v === undefined) return sessionStorage.getItem(key) || '';
      if (v) sessionStorage.setItem(key, v); else sessionStorage.removeItem(key);
    } catch (e) { /* storage blocked: the chat just will not survive a reload */ }
    return '';
  }
  function post(path, body) {
    var c = new AbortController(), t = setTimeout(function () { c.abort(); }, 75000);
    return fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: c.signal })
      .then(function (r) { clearTimeout(t); return r.json().catch(function () { return { ok: false }; }); })
      .catch(function () { clearTimeout(t); return { ok: false }; });
  }
  function add(who, text) {
    var p = document.createElement('p');
    p.className = 'lia-m ' + (who === 'u' ? 'u' : 'a');
    p.textContent = text;
    log.appendChild(p);
    log.scrollTop = log.scrollHeight;
  }
  function typing(on) {
    if (!on) { if (ty) { ty.remove(); ty = null; } return; }
    ty = document.createElement('p');
    ty.className = 'lia-m a lia-ty';
    var s = document.createElement('span');
    s.className = 'lia-vh';
    s.textContent = 'Lía está escribiendo…';
    ty.appendChild(s);
    for (var i = 0; i < 3; i++) ty.appendChild(document.createElement('i'));
    log.appendChild(ty);
    log.scrollTop = log.scrollHeight;
  }
  function ask(j) { cf.hidden = !!j.lead || !j.ask_contact; }
  function err(msg) { er.textContent = msg; er.hidden = false; }
  function grow() { box.style.height = 'auto'; box.style.height = Math.min(box.scrollHeight, 120) + 'px'; }
  function fit() {  /* phone: keep the composer above the on-screen keyboard */
    var v = window.visualViewport, s = panel.style;
    if (v && matchMedia('(max-width:700px)').matches) { s.height = v.height + 'px'; s.top = v.offsetTop + 'px'; s.bottom = 'auto'; }
    else { s.height = s.top = s.bottom = ''; }
    log.scrollTop = log.scrollHeight;
  }

  function open() {
    panel.hidden = false;
    fab.setAttribute('aria-expanded', 'true');
    html.classList.add('lia-open');
    fit();
    if (!loaded) {
      loaded = true;
      token = mem();
      if (token) post('/lia/historial', { t: token }).then(function (j) {
        if (!j.ok) { token = ''; mem(''); return; }
        if (j.t) { token = j.t; mem(token); }
        (j.messages || []).forEach(function (x) { add(x.r, x.m); });
        ask(j);
      });
    }
    box.focus();
  }
  function close() {
    panel.hidden = true;
    fab.setAttribute('aria-expanded', 'false');
    html.classList.remove('lia-open');
    fab.focus();
  }

  fab.addEventListener('click', open);
  q('.lia-x').addEventListener('click', close);
  panel.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') { close(); return; }
    if (ev.key !== 'Tab') return;
    var els = [].filter.call(panel.querySelectorAll('button,input,textarea,a[href]'), function (n) {
      return !n.disabled && n.tabIndex !== -1 && n.offsetParent !== null;
    });
    if (!els.length) return;
    var a = els[0], z = els[els.length - 1];
    if (ev.shiftKey && document.activeElement === a) { ev.preventDefault(); z.focus(); }
    else if (!ev.shiftKey && document.activeElement === z) { ev.preventDefault(); a.focus(); }
  });
  box.addEventListener('input', grow);
  box.addEventListener('keydown', function (ev) {  /* Enter sends with a mouse and keyboard; on a phone Enter is a new line */
    if (ev.key === 'Enter' && !ev.shiftKey && fine && !ev.isComposing) { ev.preventDefault(); if (chat.requestSubmit) chat.requestSubmit(); else go.click(); }
  });
  if (window.visualViewport) { visualViewport.addEventListener('resize', fit); visualViewport.addEventListener('scroll', fit); }

  chat.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var m = box.value.trim();
    if (!m || busy) return;
    busy = true; go.disabled = true;
    add('u', m);
    box.value = ''; grow();
    typing(true);
    post('/lia/mensaje', { t: token, l: ctx, m: m, website: hp.value }).then(function (j) {
      typing(false); busy = false; go.disabled = false;
      if (j.t) { token = j.t; mem(token); }
      if (j.reply) add('a', j.reply); else if (!j.ok) add('a', FALLBACK);
      if (j.ok) ask(j); else cf.hidden = false;
      box.focus();
    });
  });

  cf.addEventListener('submit', function (ev) {
    ev.preventDefault();
    er.hidden = true;
    var f = cf.elements, b = cf.querySelector('.lia-go');
    if (!f.consent.checked) { err('Para enviar tus datos acepta el aviso de privacidad.'); return; }
    b.disabled = true;
    post('/lia/contacto', { t: token, name: f.name.value, phone: f.phone.value, consent: f.consent.checked, website: hp.value }).then(function (j) {
      b.disabled = false;
      if (j.ok) { add('a', j.reply); cf.hidden = true; box.focus(); }
      else err(j.error || 'No pudimos enviar tus datos. Intenta de nuevo o usa el formulario de la página.');
    });
  });

  root.hidden = false;
})();
