"""Public Ficha Única directory (brand domain /propiedades): every public listing from every agency, one search.
It never duplicates content: each card links to the listing's home on the agency's own site (canonical stays there).
General inquiries ("dinos qué buscas") are the honest 'free leads' source: routed to agencies with priority in that zone."""
import json

from .. import db, geo
from .common import e, money, facts_line, label, TYPES
from .styles import BRAND_COLOR, BRAND_TOKENS, FONTS, MARK_CSS, PRECONNECT, logo, site_css

PER_PAGE = 24

# The directory is a brand page (not an agent's site): Ficha Única v7 look, light only. It reuses the site layout classes,
# so the brand tokens are laid over them (agent sites keep their own designs and dark mode; this page has none).
BRAND_CSS = BRAND_TOKENS + MARK_CSS + (
    ':root{--bg:#fff;--card:#fff;--fg:#1A1A22;--muted:#636371;--line:#E6E6EE;--hdr:#fff;--br:22px;'
    '--display:"Onest",system-ui,sans-serif;--dw:800;--body:"Onest",system-ui,sans-serif;'
    '--accent:#FF6B1A;--on-accent:#1A1A22;--accent-text:#B83F0A;--field-border:#8B8B99}'
    'body{background:var(--soft);-webkit-font-smoothing:antialiased}header.sh{background:rgba(255,255,255,.92);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}'
    'h1,h2,h3{letter-spacing:-.025em}.brand.logo{font-size:20px}.sh .btn-s{display:inline-flex;align-items:center;min-height:44px;padding:0 18px;border-radius:99px;'
    'background:var(--card);color:var(--fg);font-weight:700;text-decoration:none;box-shadow:inset 0 0 0 1.5px var(--line)}'
    '.tag{font-weight:800}.lc h3{font-size:19px;font-weight:800;line-height:1.25}.lc{box-shadow:none}'
    '.filters{display:grid;gap:8px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}'
    '.filters input,.filters select,.box input,.box textarea,.alertf input,.alertf select{font:16px var(--body);padding:12px 14px;border:1.5px solid var(--field-border);border-radius:14px;background:#fff;color:var(--fg)}'
    '.filters button,.box button{min-height:48px;border:0;border-radius:99px;background:var(--accent);color:var(--on-accent);font:800 16px var(--body);cursor:pointer;box-shadow:0 10px 22px -12px rgba(255,107,26,.75)}'
    '.notice{padding:13px 16px;border-radius:16px;background:var(--ok-soft);box-shadow:inset 0 0 0 1px rgba(15,111,80,.18)}'
    '::placeholder{color:var(--muted);opacity:1}'
    '@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}')


def _boost_order_sql(con):
    has = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='eco_boosts'").fetchone()
    if not has:
        return '0'
    return ("(SELECT COUNT(*) FROM eco_boosts b WHERE b.listing_id=l.id AND b.starts_at <= datetime('now') "
            "AND b.ends_at > datetime('now'))")


def search(con, q):
    sql = ("SELECT l.id FROM listings l JOIN agencies a ON a.id=l.agency_id WHERE l.status IN ('activa','apartada') "
           "AND EXISTS (SELECT 1 FROM photos p WHERE p.listing_id=l.id)")
    args = []
    if q.get('operation') in ('venta', 'renta'):
        sql += ' AND l.operation=?'
        args.append(q['operation'])
    if q.get('property_type') in dict(TYPES):
        sql += ' AND l.property_type=?'
        args.append(q['property_type'])
    if q.get('colonia'):
        sql += ' AND (l.colonia LIKE ? OR l.municipio LIKE ?)'
        args += ['%' + q['colonia'][:60] + '%'] * 2
    if q.get('currency') in ('MXN', 'USD'):
        sql += ' AND l.currency=?'
        args.append(q['currency'])
    for key, op in (('min', '>='), ('max', '<=')):
        raw = (q.get(key) or '').replace(',', '').replace('$', '').strip()
        if raw.replace('.', '', 1).isdigit():
            sql += ' AND l.price_cents %s ?' % op
            args.append(int(float(raw) * 100))
    if (q.get('beds') or '').isdigit():
        sql += ' AND l.bedrooms >= ?'
        args.append(int(q['beds']))
    boost = _boost_order_sql(con)
    sql += ' ORDER BY %sl.updated_at DESC LIMIT %d' % (('%s DESC, ' % boost) if boost != '0' else '', PER_PAGE * 4)
    return [r['id'] for r in con.execute(sql, args)]


def _opt(pairs, cur):
    return ''.join('<option value="%s"%s>%s</option>' % (e(k), ' selected' if k == cur else '', e(v)) for k, v in pairs)


def page(con, q, notice=''):
    ids = search(con, q)
    cards, pins = [], []
    for i in ids[:PER_PAGE]:
        c = db.canonical(con, i)
        img = c['photos'][0]['url_800'] if c['photos'] else ''
        where = ', '.join(x for x in (c['address']['colonia'], c['address']['municipio']) if x)
        cards.append('<a class="lc" href="%s">%s<div class="t"><span class="tag">%s · %s</span><h3>%s</h3>'
                     '<span class="p">%s</span><span class="f">%s</span><span class="f">%s · %s</span></div></a>' % (
                         e(c['url']), ('<img src="%s" alt="" loading="lazy" width="800" height="600">' % e(img)) if img else '',
                         'Venta' if c['operation'] == 'venta' else 'Renta', e(label(TYPES, c['property_type'])), e(c['title']),
                         e(money(c['price'], c['currency'])), e(facts_line(c)), e(where), e(c['agency']['name'])))
        a = c['address']
        if a['lat'] is not None and a['lng'] is not None:
            la, ln = geo.approx(a['lat'], a['lng'], exact=a['show_exact'])
            pins.append({'lat': la, 'lng': ln, 't': c['title'], 'p': money(c['price'], c['currency']), 'a': c['agency']['name']})
    from .panel import map_block
    form = ('<form class="filters" method="get" action="/propiedades" role="search">'
            '<label class="vh" for="q-col">Colonia o alcaldía</label><input id="q-col" name="colonia" placeholder="Colonia o alcaldía" value="%s">'
            '<label class="vh" for="q-op">Operación</label><select id="q-op" name="operation"><option value="">Venta y renta</option>%s</select>'
            '<label class="vh" for="q-ty">Tipo</label><select id="q-ty" name="property_type"><option value="">Cualquier tipo</option>%s</select>'
            '<label class="vh" for="q-bd">Recámaras</label><select id="q-bd" name="beds"><option value="">Recámaras</option>%s</select>'
            '<label class="vh" for="q-mx">Precio máximo</label><input id="q-mx" name="max" inputmode="numeric" placeholder="Precio máximo" value="%s">'
            '<button type="submit">Buscar</button></form>') % (
        e(q.get('colonia')), _opt([('venta', 'Venta'), ('renta', 'Renta')], q.get('operation')), _opt(TYPES, q.get('property_type')),
        _opt([(str(n), '%d+' % n) for n in (1, 2, 3, 4)], q.get('beds')), e(q.get('max')))
    ask = ('<section class="box" id="busco" style="position:static"><h2>¿No encuentras lo que buscas?</h2>'
           '<p class="muted">Dinos qué buscas y un asesor de la zona te escribe por WhatsApp.</p>'
           '<form method="post" action="/busco"><input name="website" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px">'
           '<label class="vh" for="b-name">Tu nombre</label><input id="b-name" name="name" placeholder="Tu nombre" required autocomplete="name">'
           '<label class="vh" for="b-phone">Tu WhatsApp</label><input id="b-phone" name="phone" placeholder="Tu WhatsApp (10 dígitos)" inputmode="tel" required autocomplete="tel">'
           '<label class="vh" for="b-msg">Qué buscas</label><textarea id="b-msg" name="message" rows="3" required>Busco %s en %s, hasta %s.</textarea>'
           '<label class="check"><input type="checkbox" name="consent" value="1" required> Acepto el aviso de privacidad de Ficha Única.</label>'
           '<button type="submit">Quiero que me contacten</button></form></section>') % (
        e(label(TYPES, q.get('property_type')) if q.get('property_type') else 'propiedad'), e(q.get('colonia') or 'CDMX'),
        e(q.get('max') or 'mi presupuesto'))
    body = ('<a class="skip" href="#main">Saltar al contenido</a><header class="sh"><div class="in"><a class="brand logo" href="/propiedades">%s</a>'
            '<a class="btn-s" href="/">Soy asesor</a></div></header><main id="main" class="in sec">'
            '<div><h1>Propiedades en México</h1><p class="muted">Cada propiedad la publica un asesor; te atiende directo por WhatsApp.</p></div>'
            '%s%s<p class="muted small">%d resultado%s</p>%s<div class="cards">%s</div>%s</main>'
            '<footer class="sf"><div class="in"><span>© Ficha Única · un servicio de %s</span><a href="/aviso-de-privacidad">Aviso de privacidad</a></div></footer>') % (
        logo('fu-top'), ('<p class="notice" role="status">%s</p>' % e(notice)) if notice else '', form, len(ids), '' if len(ids) == 1 else 's',
        map_block(pins), ''.join(cards) or '<p class="muted">No hay propiedades con ese filtro. Cuéntanos qué buscas abajo.</p>', ask, e(db.OWNER))
    ld = {'@context': 'https://schema.org', '@type': 'WebSite', 'name': 'Ficha Única', 'url': db.origin() + '/propiedades',
          'potentialAction': {'@type': 'SearchAction', 'target': db.origin() + '/propiedades?colonia={q}', 'query-input': 'required name=q'}}
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>Propiedades en venta y renta · Ficha Única</title><meta name="description" content="Busca casas y departamentos publicados por asesores en México. Te atienden directo por WhatsApp.">'
            '<meta name="theme-color" content="%s"><link rel="icon" type="image/png" href="/_s/icon-192.png"><link rel="apple-touch-icon" href="/_s/apple-touch-icon.png">'
            '<link rel="canonical" href="%s/propiedades">%s'
            '<link rel="stylesheet" href="%s"><style>%s%s</style>'
            '<script type="application/ld+json">%s</script></head><body>%s</body></html>') % (
        BRAND_COLOR, e(db.origin()), PRECONNECT, FONTS, site_css('ciudad', BRAND_COLOR, dark_mode=False), BRAND_CSS,
        json.dumps(ld, ensure_ascii=False), body)
