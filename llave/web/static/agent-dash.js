/*! AgentDashKit 1.1.0 - framework-free agent dashboard. One global: window.AgentDashKit.
 *  Plain ES5. All text is set with textContent. All URLs pass through safeUrl().
 *  No network requests. Pair with agent-dash.css. */
(function (global) {
  'use strict';

  var VERSION = '1.2.0';
  var SVGNS = 'http://www.w3.org/2000/svg';
  var uid = 0;

  /* ------------------------------------------------------------------ icons */
  /* Stroke paths on a 24x24 grid, drawn with stroke="currentColor". Data refers to them by name.
     A host can add its own: AgentDashKit.icons.myIcon = 'M...'. */
  var ICONS = {
    users: 'M16 19v-1a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v1M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 19v-1a4 4 0 0 0-3-3.9M16 2.1a4 4 0 0 1 0 7.8',
    home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
    pencil: 'M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5z',
    mail: 'M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM22 6l-10 7L2 6',
    share: 'M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8M16 6l-4-4-4 4M12 2v13',
    calc: 'M6 2h12a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM8 6h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01M8 19h8',
    file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h5',
    tag: 'M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8zM7 7h.01',
    plug: 'M12 22v-5M9 8V2M15 8V2M18 8v5a6 6 0 0 1-12 0V8z',
    phone: 'M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zM12 18h.01',
    cal: 'M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM16 2v4M8 2v4M3 10h18',
    shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
    chat: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z',
    dollar: 'M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6',
    globe: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20',
    list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
    plus: 'M12 5v14M5 12h14',
    bolt: 'M13 2 3 14h9l-1 8 10-12h-9l1-8z',
    search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3',
    bell: 'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0',
    copy: 'M11 9h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1',
    check: 'M20 6 9 17l-5-5',
    alert: 'M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
    circle: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z'
  };

  /* --------------------------------------------------------------- defaults */
  var TOKEN_KEYS = ['bg', 'ink', 'ink2', 'muted', 'line', 'line2', 'accent', 'onAccent', 'accentText', 'soft', 'card'];
  var TOKEN_DEFAULTS = {
    bg: '#F7F7F8', ink: '#111827', ink2: '#374151', muted: '#4B5563', line: '#E5E7EB', line2: '#B8BEC8',
    accent: '#2563EB', onAccent: '#FFFFFF', accentText: '#1D4ED8', soft: '#DBEAFE', card: '#FFFFFF'
  };
  var DEFAULT_FONT = 'system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
  /* Neutral English fallbacks so a brand file with a missing key never shows "undefined". */
  var DEFAULT_LABELS = {
    navLabel: 'Main', search: 'Search', searchPh: 'Search', bell: 'Notifications', bellUnread: 'Notifications (new)',
    help: 'Help', helpLabel: 'Help', account: 'My account',
    greeting: { morning: 'Good morning, {name}', afternoon: 'Good afternoon, {name}', evening: 'Good evening, {name}' },
    dateLine: '{date}', statsLabel: 'Overview', nextLabel: 'Your next step', later: 'Not now',
    toolsTitle: 'Your tools', arrange: 'Arrange', svcTitle: 'Grow with our partners', svcSub: '',
    sideLabel: 'More for you', share: 'Share', copy: 'Copy code', codeLabel: 'Your code',
    copied: 'Copied', copyFailed: 'Could not copy. Select the code and copy it.',
    newsTitle: 'What is new', eventsTitle: 'Live help', addCal: 'Add to my calendar',
    alertsLabel: 'Alerts', checklistTitle: 'Getting started', checklistProgress: '{done} of {total} done',
    checkDone: 'Done', checkTodo: 'To do'
  };

  /* ---------------------------------------------------------------- helpers */
  function isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function str(v) { return (typeof v === 'string' || typeof v === 'number') ? String(v) : ''; }
  function list(v) {
    if (!Array.isArray(v)) { return []; }
    return v.filter(function (x) { return isObj(x); });
  }
  function each(o, fn) { Object.keys(o).forEach(function (k) { fn(k, o[k]); }); }

  /* http(s), mailto, tel, relative and #fragment links only. Everything else returns ''. */
  function safeUrl(u) {
    if (typeof u !== 'string') { return ''; }
    var s = u.replace(/^[\s\u0000-\u001f]+|[\s\u0000-\u001f]+$/g, '');
    if (!s) { return ''; }
    var probe = s.replace(/[\u0000-\u0020\u007f-\u009f\u00ad\u200b-\u200f\u2028\u2029\ufeff]/g, '');
    if (/^(\/\/|\\|\/\\)/.test(probe)) { return ''; }
    var m = /^([a-z][a-z0-9+.\-]*):/i.exec(probe);
    if (m) {
      var scheme = m[1].toLowerCase();
      return (scheme === 'http' || scheme === 'https' || scheme === 'mailto' || scheme === 'tel') ? s : '';
    }
    return s;
  }
  function safeColor(c) {
    if (typeof c !== 'string') { return ''; }
    var s = c.trim();
    if (/^#[0-9a-f]{3,8}$/i.test(s)) { return s; }
    if (/^(rgb|hsl)a?\([0-9\s,.%\/]+\)$/i.test(s)) { return s; }
    return '';
  }
  function safeFont(f) {
    if (typeof f !== 'string') { return DEFAULT_FONT; }
    var s = f.trim();
    if (!s || !/^[A-Za-z0-9 ,'"\-_.]+$/.test(s)) { return DEFAULT_FONT; }
    return s + ', ' + DEFAULT_FONT;
  }
  function safeIconPath(d) {
    return (typeof d === 'string' && /^[MmLlHhVvCcSsQqTtAaZz0-9\s,.\-eE]+$/.test(d)) ? d : '';
  }
  function mergeLabels(base, over) {
    var out = {};
    each(base, function (k, v) { out[k] = isObj(v) ? mergeLabels(v, {}) : v; });
    if (isObj(over)) {
      each(over, function (k, v) {
        if (isObj(base[k]) && isObj(v)) { out[k] = mergeLabels(base[k], v); }
        else if (typeof v === 'string' && !isObj(base[k])) { out[k] = v; }
      });
    }
    return out;
  }
  function fill(tpl, key, value) {
    return String(tpl).replace('{' + key + '}', function () { return value; });
  }

  function el(tag, cls, text) {
    var n = doc().createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined && text !== null && text !== '') { n.textContent = text; }
    return n;
  }
  function doc() { return global.document; }
  function icon(name, size) {
    var d = safeIconPath(ICONS[name]) || ICONS.circle;
    var s = doc().createElementNS(SVGNS, 'svg');
    s.setAttribute('class', 'adk-ico');
    s.setAttribute('width', String(size || 22));
    s.setAttribute('height', String(size || 22));
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('fill', 'none');
    s.setAttribute('stroke', 'currentColor');
    s.setAttribute('stroke-width', '2');
    s.setAttribute('stroke-linecap', 'round');
    s.setAttribute('stroke-linejoin', 'round');
    s.setAttribute('aria-hidden', 'true');
    s.setAttribute('focusable', 'false');
    var p = doc().createElementNS(SVGNS, 'path');
    p.setAttribute('d', d);
    s.appendChild(p);
    return s;
  }
  function clear(n) { while (n.firstChild) { n.removeChild(n.firstChild); } }

  function normBrand(b) {
    b = isObj(b) ? b : {};
    var t = isObj(b.tokens) ? b.tokens : {};
    var tokens = {};
    TOKEN_KEYS.forEach(function (k) { tokens[k] = safeColor(t[k]) || TOKEN_DEFAULTS[k]; });
    var lang = str(b.lang);
    return {
      name: str(b.name), mono: str(b.mono), logo: str(b.logo),
      lang: /^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$/.test(lang) ? lang : '',
      font: safeFont(b.font), tokens: tokens,
      labels: mergeLabels(DEFAULT_LABELS, b.labels)
    };
  }

  function initialsOf(name) {
    var parts = str(name).replace(/^\s+|\s+$/g, '').split(/\s+/);
    if (!parts[0]) { return ''; }
    var out = parts[0].charAt(0);
    if (parts.length > 1) { out += parts[parts.length - 1].charAt(0); }
    return out.toUpperCase();
  }
  function timeOfDay(data) {
    var k = str(data.greetingKey);
    if (k === 'morning' || k === 'afternoon' || k === 'evening') { return k; }
    var h = new Date().getHours();
    return h < 12 ? 'morning' : (h < 19 ? 'afternoon' : 'evening');
  }

  /* ------------------------------------------------------------------ mount */
  function mount(host, opts) {
    if (!host || host.nodeType !== 1) { throw new Error('AgentDashKit.mount: pass a DOM element.'); }
    if (host.__agentDashKit) { host.__agentDashKit.destroy(); }
    opts = isObj(opts) ? opts : {};

    var brand = normBrand(opts.brand);
    var data = isObj(opts.data) ? opts.data : {};
    var onAction = typeof opts.onAction === 'function' ? opts.onAction : null;
    var id = 'adk' + (++uid);
    var dismissedKey = null;
    var toastTimer = null;
    var destroyed = false;
    var view, toast, h1, searchInput;

    /* root element: class, tokens, language */
    var hadClass = host.classList.contains('adk');
    var prevLang = host.getAttribute('lang');
    host.classList.add('adk');
    TOKEN_KEYS.forEach(function (k) { host.style.setProperty('--adk-' + k, brand.tokens[k]); });
    host.style.setProperty('--adk-font', brand.font);
    if (brand.lang) { host.setAttribute('lang', brand.lang); }
    clear(host);
    view = el('div', 'adk-view');
    toast = el('div', 'adk-toast');
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    host.appendChild(view);
    host.appendChild(toast);

    function emit(action, payload) {
      if (!onAction) { return; }
      try { onAction(action, payload); }
      catch (e) { if (global.console && global.console.error) { global.console.error(e); } }
    }

    /* A link (safe href) or a button (action id). Either may also carry an action id. */
    function interactive(cls, spec, section, index) {
      if (!isObj(spec)) { return null; }
      var href = safeUrl(spec.href), action = str(spec.action), node;
      if (href) {
        node = el('a', cls);
        node.setAttribute('href', href);
        if (spec.newTab === true) {
          node.setAttribute('target', '_blank');
          node.setAttribute('rel', 'noopener noreferrer');
        }
      } else if (action) {
        node = el('button', cls);
        node.setAttribute('type', 'button');
      } else {
        return null;
      }
      if (action) {
        node.addEventListener('click', function () { emit(action, { section: section, index: index, item: spec }); });
      }
      return node;
    }

    function labels() { return mergeLabels(brand.labels, data.labels); }

    function showToast(msg) {
      toast.textContent = msg;
      toast.classList.add('adk-toast--on');
      if (toastTimer) { global.clearTimeout(toastTimer); }
      toastTimer = global.setTimeout(function () {
        toast.classList.remove('adk-toast--on');
        toast.textContent = '';
        toastTimer = null;
      }, 2200);
    }

    function legacyCopy(text) {
      var prev = doc().activeElement, ok = false;
      var ta = el('textarea', 'adk-offscreen');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.setAttribute('aria-hidden', 'true');
      ta.setAttribute('tabindex', '-1');
      host.appendChild(ta);
      try { ta.select(); ta.setSelectionRange(0, text.length); ok = doc().execCommand('copy'); } catch (e) { ok = false; }
      host.removeChild(ta);
      if (prev && prev.focus) { try { prev.focus(); } catch (e2) { /* ignore */ } }
      return ok;
    }
    function copyText(text, done) {
      var nav = global.navigator;
      if (nav && nav.clipboard && typeof nav.clipboard.writeText === 'function') {
        nav.clipboard.writeText(text).then(function () { done(true); }, function () { done(legacyCopy(text)); });
      } else {
        done(legacyCopy(text));
      }
    }
    function copyWithToast(text) {
      var L = labels();
      copyText(text, function (ok) { if (!destroyed) { showToast(ok ? L.copied : L.copyFailed); } });
    }

    function shareReferral(ref) {
      var code = str(ref.code);
      var text = str(ref.shareText) || [str(ref.body), code].join(' ').replace(/^\s+|\s+$/g, '');
      emit('share_code', { section: 'referral', code: code, shareText: text, item: ref });
      var nav = global.navigator;
      if (nav && typeof nav.share === 'function') {
        var payload = { title: str(ref.title), text: text };
        var u = safeUrl(ref.url);
        if (u) { payload.url = u; }
        var p;
        try { p = nav.share(payload); } catch (e) { p = null; }
        if (p && typeof p.then === 'function') {
          p.then(null, function (err) {
            if (err && err.name === 'AbortError') { return; }
            copyWithToast(text);
          });
          return;
        }
      }
      copyWithToast(text);
    }

    /* ------------------------------------------------------------ sections */
    function buildHeader(L) {
      var header = el('header', 'adk-top');
      var row = el('div', 'adk-top__row');

      var brandBox = el('div', 'adk-brand');
      var logoUrl = brand.logo ? safeUrl(str(brand.logo)) : '';
      if (logoUrl) {  // 1.2.0: the brand's own mark (square image); falls back to the letter badge
        var logo = el('img', 'adk-logo');
        logo.setAttribute('src', logoUrl);
        logo.setAttribute('alt', '');
        logo.setAttribute('width', '34');
        logo.setAttribute('height', '34');
        brandBox.appendChild(logo);
      } else if (brand.mono) {
        var mono = el('span', 'adk-mono', brand.mono);
        mono.setAttribute('aria-hidden', 'true');
        brandBox.appendChild(mono);
      }
      if (brand.name) { brandBox.appendChild(el('span', 'adk-brand__name', brand.name)); }
      row.appendChild(brandBox);

      if (data.search !== false) {
        var form = el('form', 'adk-search');
        form.setAttribute('role', 'search');
        var box = el('label', 'adk-search__box');
        box.appendChild(icon('search', 18));
        box.appendChild(el('span', 'adk-sr', L.search));
        searchInput = el('input', 'adk-search__input');
        searchInput.setAttribute('type', 'search');
        searchInput.setAttribute('name', 'adk-search');
        searchInput.setAttribute('autocomplete', 'off');
        searchInput.setAttribute('placeholder', L.searchPh);
        box.appendChild(searchInput);
        form.appendChild(box);
        form.addEventListener('submit', function (ev) {
          ev.preventDefault();
          emit('search', { section: 'header', query: searchInput.value });
        });
        row.appendChild(form);
      } else {
        searchInput = null;
      }

      var actions = el('div', 'adk-actions');
      var notif = data.notifications;
      if (notif !== false) {
        var unread = isObj(notif) && (notif.unread === true || Number(notif.count) > 0);
        var bell = el('button', 'adk-iconbtn');
        bell.setAttribute('type', 'button');
        bell.setAttribute('aria-label', unread ? L.bellUnread : L.bell);
        bell.appendChild(icon('bell', 20));
        if (unread) {
          var dot = el('span', 'adk-dot');
          dot.setAttribute('aria-hidden', 'true');
          bell.appendChild(dot);
        }
        bell.addEventListener('click', function () { emit('notifications', { section: 'header' }); });
        actions.appendChild(bell);
      }
      if (L.help && data.help !== false) {
        var helpSpec = isObj(data.help) ? data.help : { action: 'help' };
        var help = interactive('adk-helpbtn', helpSpec, 'header', 0) || interactive('adk-helpbtn', { action: 'help' }, 'header', 0);
        help.textContent = L.help;
        if (L.helpLabel) { help.setAttribute('aria-label', L.helpLabel); }
        actions.appendChild(help);
      }
      var user = isObj(data.user) ? data.user : {};
      var initials = str(user.initials) || initialsOf(user.name);
      if (initials) {
        var av = interactive('adk-avatar', user, 'header', 0) || el('span', 'adk-avatar');
        av.textContent = initials;
        if (av.tagName.toLowerCase() === 'span') { av.setAttribute('aria-hidden', 'true'); }
        else { av.setAttribute('aria-label', str(user.name) ? L.account + ': ' + str(user.name) : L.account); }
        actions.appendChild(av);
      }
      row.appendChild(actions);
      header.appendChild(row);

      var tabs = list(data.tabs);
      if (tabs.length) {
        var nav = el('nav', 'adk-tabs');
        nav.setAttribute('aria-label', L.navLabel);
        tabs.forEach(function (t, i) {
          var label = str(t.label);
          if (!label) { return; }
          var node = interactive('adk-tab', t, 'tabs', i) || el('span', 'adk-tab');
          node.textContent = label;
          if (t.current === true) { node.setAttribute('aria-current', 'page'); }
          nav.appendChild(node);
        });
        if (nav.childNodes.length) { header.appendChild(nav); }
      }
      return header;
    }

    function buildHello(L) {
      var user = isObj(data.user) ? data.user : {};
      var name = str(user.name);
      var greeting = str(data.greeting);
      if (!greeting) {
        greeting = fill(L.greeting[timeOfDay(data)] || '', 'name', name);
        if (!name) { greeting = greeting.replace(/[,\s]*(?:\{name\})?\s*$/, ''); }
      }
      var wrap = el('div', 'adk-hello');
      var left = el('div', 'adk-hello__text');
      h1 = el('h1', 'adk-h1', greeting);
      h1.setAttribute('tabindex', '-1');
      left.appendChild(h1);
      var date = str(data.dateText);
      if (date) { left.appendChild(el('p', 'adk-sub', fill(L.dateLine, 'date', date))); }
      wrap.appendChild(left);
      if (isObj(data.primary) && str(data.primary.label)) {
        var btn = interactive('adk-btn adk-btn--dark', data.primary, 'primary', 0);
        if (btn) {
          btn.appendChild(icon('plus', 18));
          btn.appendChild(doc().createTextNode(str(data.primary.label)));
          wrap.appendChild(btn);
        }
      }
      return wrap;
    }

    function buildStats(L) {
      var items = list(data.stats);
      if (!items.length) { return null; }
      var ul = el('ul', 'adk-stats');
      ul.setAttribute('role', 'list');
      ul.setAttribute('aria-label', L.statsLabel);
      items.forEach(function (s, i) {
        var li = el('li', 'adk-stat');
        li.appendChild(el('span', 'adk-stat__label', str(s.label)));
        li.appendChild(el('span', 'adk-stat__value', str(s.value)));
        if (str(s.sub)) { li.appendChild(el('span', 'adk-stat__sub', str(s.sub))); }
        if (isObj(s.cta) && str(s.cta.label)) {
          var c = interactive('adk-btn adk-btn--accent adk-btn--sm adk-stat__cta', s.cta, 'stats', i);
          if (c) { c.textContent = str(s.cta.label); li.appendChild(c); }
        }
        if (isObj(s.more) && str(s.more.label)) {
          var ml = interactive('adk-link adk-stat__morelink', s.more, 'stats', i);
          if (ml) {
            var more = el('div', 'adk-stat__more');
            ml.textContent = str(s.more.label);
            more.appendChild(ml);
            if (str(s.more.by)) { more.appendChild(el('span', 'adk-stat__by', str(s.more.by))); }
            li.appendChild(more);
          }
        }
        ul.appendChild(li);
      });
      return ul;
    }

    function buildNext(L) {
      var n = data.next;
      if (!isObj(n) || !str(n.title)) { return null; }
      var key = str(n.title) + '|' + str(n.body);
      if (dismissedKey === key) { return null; }
      var sec = el('section', 'adk-next');
      var hid = id + '-next-h';
      sec.setAttribute('aria-labelledby', hid);
      var ico = el('span', 'adk-next__icon');
      ico.setAttribute('aria-hidden', 'true');
      ico.appendChild(icon(str(n.icon) || 'bolt', 26));
      sec.appendChild(ico);
      var text = el('div', 'adk-next__text');
      text.appendChild(el('p', 'adk-next__label', str(n.label) || L.nextLabel));
      var h = el('h2', 'adk-h2', str(n.title));
      h.id = hid;
      text.appendChild(h);
      if (str(n.body)) { text.appendChild(el('p', 'adk-next__body', str(n.body))); }
      sec.appendChild(text);
      var actions = el('div', 'adk-next__actions');
      if (isObj(n.cta) && str(n.cta.label)) {
        var cta = interactive('adk-btn adk-btn--accent', n.cta, 'next', 0);
        if (cta) { cta.textContent = str(n.cta.label); actions.appendChild(cta); }
      }
      if (n.dismissible !== false) {
        var later = el('button', 'adk-btn adk-btn--ghost', L.later);
        later.setAttribute('type', 'button');
        later.addEventListener('click', function () {
          dismissedKey = key;
          if (sec.parentNode) { sec.parentNode.removeChild(sec); }
          emit('dismiss_next', { section: 'next', item: n });
          if (h1 && h1.focus) { h1.focus(); }
        });
        actions.appendChild(later);
      }
      if (actions.childNodes.length) { sec.appendChild(actions); }
      return sec;
    }

    function buildTools(L) {
      var items = list(data.tools);
      if (!items.length) { return null; }
      var sec = el('section', 'adk-sec');
      var hid = id + '-tools-h';
      sec.setAttribute('aria-labelledby', hid);
      var head = el('div', 'adk-sec__head');
      var h = el('h2', 'adk-h2', L.toolsTitle);
      h.id = hid;
      head.appendChild(h);
      var arr = data.arrange;
      if (arr !== false && L.arrange) {
        var spec = isObj(arr) ? arr : { action: 'arrange' };
        var a = interactive('adk-link', spec, 'tools', 0) || interactive('adk-link', { action: 'arrange' }, 'tools', 0);
        a.textContent = L.arrange;
        head.appendChild(a);
      }
      sec.appendChild(head);
      var ul = el('ul', 'adk-tools');
      ul.setAttribute('role', 'list');
      items.forEach(function (t, i) {
        if (!str(t.label)) { return; }
        var li = el('li', 'adk-tools__item');
        var card = interactive('adk-tool', t, 'tools', i) || el('div', 'adk-tool adk-tool--static');
        var ico = el('span', 'adk-tool__ico');
        ico.setAttribute('aria-hidden', 'true');
        ico.appendChild(icon(str(t.icon), 22));
        card.appendChild(ico);
        var txt = el('span', 'adk-tool__txt');
        txt.appendChild(el('span', 'adk-tool__label', str(t.label)));
        if (str(t.hint)) { txt.appendChild(el('span', 'adk-tool__hint', str(t.hint))); }
        card.appendChild(txt);
        li.appendChild(card);
        ul.appendChild(li);
      });
      sec.appendChild(ul);
      return sec;
    }

    function buildServices(L) {
      var items = list(data.services);
      if (!items.length) { return null; }
      var sec = el('section', 'adk-sec');
      var hid = id + '-svc-h';
      sec.setAttribute('aria-labelledby', hid);
      var head = el('div', 'adk-sec__head adk-sec__head--stack');
      var h = el('h2', 'adk-h2', L.svcTitle);
      h.id = hid;
      head.appendChild(h);
      if (L.svcSub) { head.appendChild(el('p', 'adk-sec__sub', L.svcSub)); }
      sec.appendChild(head);
      var ul = el('ul', 'adk-svcs');
      ul.setAttribute('role', 'list');
      items.forEach(function (s, i) {
        if (!str(s.name)) { return; }
        var li = el('li', 'adk-svc');
        var top = el('div', 'adk-svc__top');
        var badge = el('span', 'adk-svc__mono', str(s.mono));
        badge.setAttribute('aria-hidden', 'true');
        var bg = safeColor(s.color), fg = safeColor(s.onColor);
        if (bg) { badge.style.backgroundColor = bg; }
        if (fg) { badge.style.color = fg; }
        if (str(s.mono)) { top.appendChild(badge); }
        top.appendChild(el('span', 'adk-svc__name', str(s.name)));
        li.appendChild(top);
        if (str(s.text)) { li.appendChild(el('p', 'adk-svc__text', str(s.text))); }
        if (isObj(s.cta) && str(s.cta.label)) {
          var c = interactive('adk-link adk-svc__cta', s.cta, 'services', i);
          if (c) { c.textContent = str(s.cta.label); li.appendChild(c); }
        }
        ul.appendChild(li);
      });
      sec.appendChild(ul);
      return sec;
    }

    function buildReferral(L) {
      var r = data.referral;
      if (!isObj(r) || !(str(r.title) || str(r.body) || str(r.code))) { return null; }
      var box = el('section', 'adk-refer');
      var hid = id + '-ref-h';
      if (str(r.title)) {
        box.setAttribute('aria-labelledby', hid);
        var h = el('h2', 'adk-h3', str(r.title));
        h.id = hid;
        box.appendChild(h);
      }
      if (str(r.body)) { box.appendChild(el('p', 'adk-refer__body', str(r.body))); }
      var code = str(r.code);
      if (code || str(r.shareText)) {
        var row = el('div', 'adk-refer__row');
        if (code) {
          var cbox = el('div', 'adk-code');
          cbox.appendChild(el('span', 'adk-sr', L.codeLabel + ': '));
          cbox.appendChild(el('span', 'adk-code__text', code));
          var cp = el('button', 'adk-code__copy');
          cp.setAttribute('type', 'button');
          cp.setAttribute('aria-label', L.copy);
          cp.appendChild(icon('copy', 18));
          cp.addEventListener('click', function () {
            emit('copy_code', { section: 'referral', code: code, item: r });
            copyWithToast(code);
          });
          cbox.appendChild(cp);
          row.appendChild(cbox);
        }
        var sh = el('button', 'adk-btn adk-btn--accent', L.share);
        sh.setAttribute('type', 'button');
        sh.addEventListener('click', function () { shareReferral(r); });
        row.appendChild(sh);
        box.appendChild(row);
      }
      return box;
    }

    function buildNews(L) {
      var items = list(data.news);
      if (!items.length) { return null; }
      var card = el('section', 'adk-card');
      var hid = id + '-news-h';
      card.setAttribute('aria-labelledby', hid);
      var h = el('h2', 'adk-h3', L.newsTitle);
      h.id = hid;
      card.appendChild(h);
      var ul = el('ul', 'adk-news');
      ul.setAttribute('role', 'list');
      items.forEach(function (n, i) {
        if (!str(n.title)) { return; }
        var li = el('li', 'adk-news__li');
        var item = interactive('adk-news__item', n, 'news', i) || el('div', 'adk-news__item adk-news__item--static');
        if (str(n.tag)) { item.appendChild(el('span', 'adk-news__tag', str(n.tag))); }
        item.appendChild(el('span', 'adk-news__title', str(n.title)));
        if (str(n.date)) { item.appendChild(el('span', 'adk-news__date', str(n.date))); }
        li.appendChild(item);
        ul.appendChild(li);
      });
      card.appendChild(ul);
      return card;
    }

    function buildEvents(L) {
      var items = list(data.events);
      if (!items.length) { return null; }
      var card = el('section', 'adk-card');
      var hid = id + '-ev-h';
      card.setAttribute('aria-labelledby', hid);
      var h = el('h2', 'adk-h3', L.eventsTitle);
      h.id = hid;
      card.appendChild(h);
      var ul = el('ul', 'adk-events');
      ul.setAttribute('role', 'list');
      items.forEach(function (ev, i) {
        if (!str(ev.title)) { return; }
        var li = el('li', 'adk-ev');
        var chip = el('span', 'adk-ev__chip');
        chip.appendChild(el('span', 'adk-ev__month', str(ev.month)));
        chip.appendChild(el('span', 'adk-ev__day', str(ev.day)));
        li.appendChild(chip);
        var txt = el('span', 'adk-ev__txt');
        var title = interactive('adk-ev__title', ev, 'events', i) || el('span', 'adk-ev__title');
        title.textContent = str(ev.title);
        txt.appendChild(title);
        if (str(ev.when)) { txt.appendChild(el('span', 'adk-ev__when', str(ev.when))); }
        li.appendChild(txt);
        ul.appendChild(li);
      });
      card.appendChild(ul);
      var cal = data.calendar;
      if (cal !== false && L.addCal) {
        var a;
        if (isObj(cal) && (safeUrl(cal.href) || str(cal.action))) {
          a = interactive('adk-link adk-ev__cal', cal, 'events', -1);
        } else {
          /* default: a button that hands the host the whole event list */
          a = el('button', 'adk-link adk-ev__cal');
          a.setAttribute('type', 'button');
          a.addEventListener('click', function () {
            emit('add_to_calendar', { section: 'events', events: list(data.events) });
          });
        }
        a.textContent = L.addCal;
        card.appendChild(a);
      }
      return card;
    }

    function buildApp() {
      var a = data.app;
      if (!isObj(a) || !(str(a.title) || str(a.body))) { return null; }
      var box = el('section', 'adk-pwa');
      box.appendChild(icon(str(a.icon) || 'phone', 26));
      var txt = el('span', 'adk-pwa__txt');
      if (str(a.title)) { txt.appendChild(el('strong', 'adk-pwa__title', str(a.title))); }
      if (str(a.body)) { txt.appendChild(doc().createTextNode(str(a.body))); }
      box.appendChild(txt);
      if (isObj(a.cta) && str(a.cta.label)) {
        var c = interactive('adk-link', a.cta, 'app', 0);
        if (c) { c.textContent = str(a.cta.label); box.appendChild(c); }
      }
      return box;
    }

    /* 1.1.0: urgent notices at the top of the main column (late leads, follow-ups due, stale prices). */
    function buildAlerts(L) {
      var items = list(data.alerts).filter(function (a) { return str(a.title); });
      if (!items.length) { return null; }
      var sec = el('section', 'adk-alerts');
      sec.setAttribute('aria-label', L.alertsLabel);
      var ul = el('ul', 'adk-alerts__list');
      ul.setAttribute('role', 'list');
      items.forEach(function (a, i) {
        var warn = a.tone === 'warn';
        var li = el('li', 'adk-alert' + (warn ? ' adk-alert--warn' : ''));
        var ico = el('span', 'adk-alert__ico');
        ico.setAttribute('aria-hidden', 'true');
        ico.appendChild(icon(str(a.icon) || (warn ? 'alert' : 'bell'), 20));
        li.appendChild(ico);
        var txt = el('div', 'adk-alert__txt');
        txt.appendChild(el('p', 'adk-alert__title', str(a.title)));
        if (str(a.body)) { txt.appendChild(el('p', 'adk-alert__body', str(a.body))); }
        li.appendChild(txt);
        if (isObj(a.cta) && str(a.cta.label)) {
          var c = interactive('adk-btn adk-btn--ghost adk-btn--sm adk-alert__cta', a.cta, 'alerts', i);
          if (c) { c.textContent = str(a.cta.label); li.appendChild(c); }
        }
        ul.appendChild(li);
      });
      sec.appendChild(ul);
      return sec;
    }

    /* 1.1.0: a short to-do list with progress (first week, setup). Counts come from the items. */
    function buildChecklist(L) {
      var c = data.checklist;
      if (!isObj(c)) { return null; }
      var items = list(c.items).filter(function (t) { return str(t.label); });
      if (!items.length) { return null; }
      var done = items.filter(function (t) { return t.done === true; }).length;
      var total = items.length;
      var sec = el('section', 'adk-sec adk-check');
      var hid = id + '-check-h';
      sec.setAttribute('aria-labelledby', hid);
      var head = el('div', 'adk-sec__head');
      var h = el('h2', 'adk-h2', str(c.title) || L.checklistTitle);
      h.id = hid;
      head.appendChild(h);
      var progText = fill(fill(L.checklistProgress, 'done', String(done)), 'total', String(total));
      head.appendChild(el('span', 'adk-check__count', progText));
      sec.appendChild(head);
      var bar = el('div', 'adk-check__bar');
      bar.setAttribute('role', 'progressbar');
      bar.setAttribute('aria-valuemin', '0');
      bar.setAttribute('aria-valuemax', String(total));
      bar.setAttribute('aria-valuenow', String(done));
      bar.setAttribute('aria-valuetext', progText);
      bar.setAttribute('aria-labelledby', hid);
      var fillEl = el('span', 'adk-check__fill');
      fillEl.style.width = Math.round(done / total * 100) + '%';
      bar.appendChild(fillEl);
      sec.appendChild(bar);
      var ul = el('ul', 'adk-check__list');
      ul.setAttribute('role', 'list');
      items.forEach(function (t, i) {
        var isDone = t.done === true;
        var li = el('li', 'adk-check__li' + (isDone ? ' adk-check__li--done' : ''));
        var row = (!isDone && interactive('adk-check__item', t, 'checklist', i)) || el('div', 'adk-check__item adk-check__item--static');
        var mark = el('span', 'adk-check__mark');
        mark.setAttribute('aria-hidden', 'true');
        if (isDone) { mark.appendChild(icon('check', 16)); }
        row.appendChild(mark);
        row.appendChild(el('span', 'adk-sr', (isDone ? L.checkDone : L.checkTodo) + ': '));
        var txt = el('span', 'adk-check__txt');
        txt.appendChild(el('span', 'adk-check__label', str(t.label)));
        if (str(t.hint) && !isDone) { txt.appendChild(el('span', 'adk-check__hint', str(t.hint))); }
        row.appendChild(txt);
        li.appendChild(row);
        ul.appendChild(li);
      });
      sec.appendChild(ul);
      return sec;
    }

    function add(parent, node) { if (node) { parent.appendChild(node); } }

    function render() {
      var prevQuery = searchInput ? searchInput.value : '';
      h1 = null;
      searchInput = null;
      clear(view);
      var L = labels();
      view.appendChild(buildHeader(L));
      var layout = el('div', 'adk-layout');
      var main = el('div', 'adk-main');
      add(main, buildHello(L));
      add(main, buildAlerts(L));
      add(main, buildStats(L));
      add(main, buildNext(L));
      add(main, buildChecklist(L));
      add(main, buildTools(L));
      add(main, buildServices(L));
      layout.appendChild(main);
      var side = el('aside', 'adk-side');
      side.setAttribute('aria-label', L.sideLabel);
      add(side, buildReferral(L));
      add(side, buildNews(L));
      add(side, buildEvents(L));
      add(side, buildApp());
      if (side.childNodes.length) { layout.appendChild(side); }
      view.appendChild(layout);
      if (searchInput && prevQuery) { searchInput.value = prevQuery; }
    }

    render();

    var api = {
      update: function (next) {
        if (destroyed) { return; }
        data = isObj(next) ? next : {};
        render();
      },
      destroy: function () {
        if (destroyed) { return; }
        destroyed = true;
        if (toastTimer) { global.clearTimeout(toastTimer); }
        clear(host);
        TOKEN_KEYS.forEach(function (k) { host.style.removeProperty('--adk-' + k); });
        host.style.removeProperty('--adk-font');
        if (!hadClass) { host.classList.remove('adk'); }
        if (prevLang === null) { host.removeAttribute('lang'); } else { host.setAttribute('lang', prevLang); }
        host.__agentDashKit = null;
      }
    };
    host.__agentDashKit = api;
    return api;
  }

  global.AgentDashKit = { version: VERSION, mount: mount, icons: ICONS, safeUrl: safeUrl };
}(typeof window !== 'undefined' ? window : this));
