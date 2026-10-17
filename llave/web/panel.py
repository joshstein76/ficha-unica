"""The agent panel (app.<base>): sign up, listings + photos, leads, portals, Bolsa, my site.
Pages are plain functions returning HTML; server.py handles routing, sessions and POSTs."""
import json

from .. import db, whatsapp
from ..feeds import registry, validate
from .common import (e, money, nice_date, facts_line, label, csrf_token, TYPES, STATUSES, LEAD_STATUSES, DESIGNS)
from .styles import FONTS, PANEL

ICONS = {
    'inicio': '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    'propiedades': '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h8M8 15h5"/>',
    'clientes': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    'portales': '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    'bolsa': '<path d="M7 7h10l-1 13H8z"/><path d="M9 7a3 3 0 0 1 6 0"/>',
    'sitio': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
}
TABS = [('inicio', 'Inicio', '/'), ('propiedades', 'Propiedades', '/propiedades'), ('clientes', 'Clientes', '/clientes'),
        ('portales', 'Portales', '/portales'), ('bolsa', 'Bolsa', '/bolsa'), ('sitio', 'Mi sitio', '/sitio')]


def _icon(k):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true">%s</svg>' % ICONS[k])


def layout(title, body, ctx=None, tab=None, flash=''):
    nav = ''
    top_right = '<a class="btn ghost small" href="/entrar">Entrar</a>'
    if ctx:
        nav = '<nav class="tabs">%s</nav>' % ''.join(
            '<a href="%s" class="%s">%s<span>%s</span></a>' % (href, 'on' if k == tab else '', _icon(k), lab)
            for k, lab, href in TABS)
        top_right = ('<span class="row small"><a href="%s" target="_blank" rel="noopener">Ver mi sitio ↗</a>'
                     '<form method="post" action="/salir" style="margin:0">%s<button class="btn ghost small">Salir</button></form></span>'
                     % (e(db.site_url(ctx['agency'])), csrf_field(ctx)))
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>%s · LLAVE</title><link rel="stylesheet" href="%s"><style>%s</style></head><body>'
            '<header class="top"><a class="logo" href="/">LLA<span>VE</span></a>%s</header>%s'
            '<main class="wrap">%s%s</main></body></html>') % (
        e(title), FONTS, PANEL, top_right, nav, flash, body)


def csrf_field(ctx):
    return '<input type="hidden" name="csrf" value="%s">' % csrf_token(ctx['token'])


def notice(msg, kind=''):
    return ('<div class="notice %s" role="status">%s</div>' % (kind, e(msg))) if msg else ''


# ---------- auth ----------
def signup(error='', values=None):
    v = values or {}
    body = ('<div class="auth"><div><h1>Tu sitio inmobiliario gratis, hoy.</h1>'
            '<p class="muted">Sube tus propiedades una vez. Aparecen en tu sitio, en Google y en los portales. '
            'Tus clientes te llegan por WhatsApp.</p></div>%s'
            '<form class="stack card" method="post" action="/registro">'
            '<label>Tu nombre<input name="name" value="%s" autocomplete="name" required></label>'
            '<label>Nombre de tu inmobiliaria o marca<input name="agency" value="%s" placeholder="Ej. Casas Roma" required></label>'
            '<label>Tu WhatsApp<input name="whatsapp" value="%s" inputmode="tel" placeholder="55 1234 5678" required></label>'
            '<label>Correo<input name="email" type="email" value="%s" autocomplete="email" required></label>'
            '<label>Contraseña<input name="password" type="password" minlength="8" autocomplete="new-password" required></label>'
            '<label class="check"><input type="checkbox" name="terms" value="1" required> Acepto los términos y el aviso de privacidad (borrador).</label>'
            '<button class="btn">Crear mi sitio gratis</button>'
            '<p class="small muted">¿Ya tienes cuenta? <a href="/entrar">Entrar</a></p></form></div>') % (
        notice(error, 'err'), e(v.get('name')), e(v.get('agency')), e(v.get('whatsapp')), e(v.get('email')))
    return layout('Crear cuenta', body)


def login(error=''):
    body = ('<div class="auth"><h1>Entrar</h1>%s<form class="stack card" method="post" action="/entrar">'
            '<label>Correo<input name="email" type="email" autocomplete="email" required></label>'
            '<label>Contraseña<input name="password" type="password" autocomplete="current-password" required></label>'
            '<button class="btn">Entrar</button><p class="small muted">¿Nuevo? <a href="/registro">Crea tu sitio gratis</a></p>'
            '</form></div>') % notice(error, 'err')
    return layout('Entrar', body)


# ---------- dashboard ----------
def dashboard(con, ctx, welcome=False):
    a = ctx['agency']
    n_list = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status IN ('activa','apartada')", (a['id'],)).fetchone()[0]
    n_all = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status NOT IN ('vendida','rentada')", (a['id'],)).fetchone()[0]
    n_new = con.execute("SELECT COUNT(*) FROM leads WHERE agency_id=? AND status='nuevo'", (a['id'],)).fetchone()[0]
    n_feed = con.execute("SELECT COUNT(*) FROM portal_publications p JOIN listings l ON l.id=p.listing_id "
                         "WHERE l.agency_id=? AND p.enabled=1", (a['id'],)).fetchone()[0]
    limit = db.PLAN_LIMITS.get(a['plan'], 10)
    steps = [
        (n_all > 0, 'Sube tu primera propiedad', '/propiedades/nueva'),
        (con.execute('SELECT COUNT(*) FROM photos p JOIN listings l ON l.id=p.listing_id WHERE l.agency_id=?', (a['id'],)).fetchone()[0] >= 5,
         'Agrega al menos 5 fotos', '/propiedades'),
        (n_list > 0, 'Publícala (estado: Activa)', '/propiedades'),
        (n_feed > 0, 'Actívala en los portales', '/portales'),
        (bool(a['tagline'] and a['about']), 'Personaliza tu sitio', '/sitio'),
    ]
    done = sum(1 for s in steps if s[0])
    leads = con.execute('SELECT * FROM leads WHERE agency_id=? ORDER BY id DESC LIMIT 5', (a['id'],)).fetchall()
    body = ('%s<div><h1>Hola, %s</h1><p class="muted">Tu sitio: <a href="%s" target="_blank" rel="noopener">%s</a></p></div>'
            '<div class="stats"><div class="stat"><b>%d</b><small>Propiedades publicadas</small></div>'
            '<div class="stat"><b>%d/%d</b><small>Usadas en plan %s</small></div>'
            '<div class="stat"><b>%d</b><small>Clientes nuevos</small></div>'
            '<div class="stat"><b>%d</b><small>Publicaciones en portales</small></div></div>'
            '<section class="card"><h2>Tu sitio listo en 5 pasos (%d/5)</h2><div class="list">%s</div></section>'
            '<section class="card"><div class="row" style="justify-content:space-between"><h2>Últimos clientes</h2>'
            '<a href="/clientes">Ver todos</a></div>%s</section>') % (
        notice('¡Listo! Tu sitio ya existe. Ahora sube tu primera propiedad.') if welcome else '',
        e(ctx['user']['name'].split(' ')[0]), e(db.site_url(a)), e(db.site_url(a).split('//')[1]),
        n_list, n_all, limit, e(a['plan']), n_new, n_feed, done,
        ''.join('<a class="row" href="%s" style="text-decoration:none;color:inherit"><span class="pill %s">%s</span>%s</a>'
                % (href, 'ok' if ok else 'pendiente', '✓' if ok else '•', e(t)) for ok, t, href in steps),
        _leads_list(con, leads) if leads else '<p class="muted">Aún no tienes clientes. Cuando alguien escriba desde tu sitio, aparece aquí y en WhatsApp.</p>')
    return layout('Inicio', body, ctx, 'inicio')


# ---------- listings ----------
def _thumb(con, a, lid):
    p = con.execute('SELECT * FROM photos WHERE listing_id=? ORDER BY position, id LIMIT 1', (lid,)).fetchone()
    return ('<img src="/media/%s" alt="">' % e(json.loads(p['sizes'])['400'])) if p else '<span class="ph"></span>'


def listings(con, ctx, flash=''):
    a = ctx['agency']
    rows = con.execute('SELECT * FROM listings WHERE agency_id=? ORDER BY updated_at DESC', (a['id'],)).fetchall()
    items = ''.join(
        '<a class="item" href="/propiedades/%d">%s<div style="min-width:0"><b>%s</b><span class="small muted">%s · %s</span><br>'
        '<span class="pill %s">%s</span> <span class="small muted">%s</span></div></a>' % (
            r['id'], _thumb(con, a, r['id']), e(r['title']),
            e(money((r['price_cents'] // 100) if r['price_cents'] is not None else None, r['currency'])), e(r['ref']),
            e(r['status']), e(label(STATUSES, r['status'])),
            con.execute('SELECT COUNT(*) FROM photos WHERE listing_id=?', (r['id'],)).fetchone()[0] and
            '%d fotos' % con.execute('SELECT COUNT(*) FROM photos WHERE listing_id=?', (r['id'],)).fetchone()[0] or 'sin fotos')
        for r in rows)
    body = ('%s<div class="row" style="justify-content:space-between"><h1>Propiedades</h1>'
            '<a class="btn" href="/propiedades/nueva">+ Nueva</a></div><div class="list">%s</div>') % (
        flash, items or '<p class="muted">Aún no hay propiedades. Sube la primera: tarda 2 minutos.</p>')
    return layout('Propiedades', body, ctx, 'propiedades')


def _opt(pairs, cur):
    return ''.join('<option value="%s"%s>%s</option>' % (e(k), ' selected' if k == cur else '', e(v)) for k, v in pairs)


def listing_form(con, ctx, l=None, error='', ok=''):
    v = dict(l) if l else {}
    lid = v.get('id')
    price = '' if v.get('price_cents') is None else '%d' % (v['price_cents'] // 100)
    maint = '' if v.get('maintenance_cents') is None else '%d' % (v['maintenance_cents'] // 100)
    am = ', '.join(json.loads(v.get('amenities') or '[]'))

    def num(k):
        x = v.get(k)
        return '' if x is None else ('%g' % x)
    photos_html = ''
    problems = []
    if lid:
        ph = con.execute('SELECT * FROM photos WHERE listing_id=? ORDER BY position, id', (lid,)).fetchall()
        photos_html = ('<section class="card"><h2>Fotos (%d)</h2><p class="small muted">Sube varias a la vez. Las ajustamos '
                       'al tamaño ideal y quitamos los datos de ubicación de la cámara. Mínimo 600 px.</p>'
                       '<form method="post" action="/propiedades/%d/fotos" enctype="multipart/form-data" class="row">%s'
                       '<input type="file" name="fotos" accept="image/jpeg,image/png,image/webp" multiple required style="flex:1">'
                       '<button class="btn small">Subir fotos</button></form><div class="thumbs">%s</div></section>') % (
            len(ph), lid, csrf_field(ctx),
            ''.join('<figure><img src="/media/%s" alt=""><form method="post" action="/propiedades/%d/fotos/%d/borrar">%s'
                    '<button class="btn ghost small" style="width:100%%">Quitar</button></form></figure>'
                    % (e(json.loads(p['sizes'])['400']), lid, p['id'], csrf_field(ctx)) for p in ph))
        problems = validate(db.canonical(con, lid))
    site_link = ''
    if lid and v.get('status') in db.PUBLIC_STATUSES:
        site_link = '<a href="%s" target="_blank" rel="noopener">Ver en mi sitio ↗</a>' % e(db.listing_url(ctx['agency'], v))
    rp_box = ('<label class="check"><input type="checkbox" name="rentapoliza_offer" value="1"%s> '
              'Ofrecer póliza jurídica RentaPóliza (rentas)</label>' % (' checked' if v.get('rentapoliza_offer') else ''))
    body = ('%s%s<div class="row" style="justify-content:space-between"><h1>%s</h1>%s</div>%s'
            '<form class="stack" method="post" action="%s">%s'
            '<section class="card"><h2>Lo básico</h2>'
            '<label>Título<input name="title" value="%s" maxlength="100" placeholder="Departamento con terraza en Polanco" required></label>'
            '<div class="grid2"><label>Operación<select name="operation">%s</select></label>'
            '<label>Tipo<select name="property_type">%s</select></label>'
            '<label>Precio<input name="price" value="%s" inputmode="numeric" placeholder="4500000 (vacío = a consultar)"></label>'
            '<label>Moneda<select name="currency">%s</select></label>'
            '<label>Fecha del precio<input type="date" name="price_date" value="%s"></label>'
            '<label>Estado<select name="status">%s</select></label></div>'
            '<label>Descripción<textarea name="description" placeholder="Cuéntalo como se lo dirías a un cliente.">%s</textarea></label></section>'
            '<section class="card"><h2>Medidas</h2><div class="grid2">'
            '<label>m² construcción<input name="m2_built" value="%s" inputmode="decimal"></label>'
            '<label>m² terreno<input name="m2_land" value="%s" inputmode="decimal"></label>'
            '<label>Recámaras<input name="bedrooms" value="%s" inputmode="numeric"></label>'
            '<label>Baños<input name="bathrooms" value="%s" inputmode="decimal" placeholder="2.5"></label>'
            '<label>Estacionamientos<input name="parking" value="%s" inputmode="numeric"></label>'
            '<label>Mantenimiento mensual (MXN)<input name="maintenance" value="%s" inputmode="numeric"></label></div>'
            '<label>Amenidades (separadas por coma)<input name="amenities" value="%s" placeholder="Gimnasio, Alberca, Roof garden"></label>'
            '<div class="row"><label class="check"><input type="checkbox" name="furnished" value="1"%s> Amueblado</label>'
            '<label class="check"><input type="checkbox" name="pets" value="1"%s> Admite mascotas</label></div></section>'
            '<section class="card"><h2>Ubicación</h2><div class="grid2">'
            '<label>Calle<input name="street" value="%s"></label><label>Número<input name="ext_number" value="%s"></label>'
            '<label>Colonia<input name="colonia" value="%s" required></label><label>Alcaldía o municipio<input name="municipio" value="%s" required></label>'
            '<label>Estado<input name="estado" value="%s" required></label><label>C.P.<input name="cp" value="%s" inputmode="numeric"></label></div>'
            '<label class="check"><input type="checkbox" name="show_exact_location" value="1"%s> Mostrar la dirección exacta (si no, solo la colonia)</label></section>'
            '<section class="card"><h2>Compartir y extras</h2>'
            '<label class="check"><input type="checkbox" name="share_in_bolsa" value="1"%s> Compartir en la Bolsa con otros asesores</label>'
            '<label>Tu parte si otro asesor la vende (%%)<input name="share_split_pct" value="%s" inputmode="numeric"></label>'
            '<label>Comisión total (%%), privada<input name="commission_pct" value="%s" inputmode="decimal"></label>%s'
            '<label>Nota interna (nunca se publica)<textarea name="internal_note" rows="2">%s</textarea></label></section>'
            '<button class="btn">%s</button></form>%s') % (
        notice(ok), notice(error, 'err'), 'Editar propiedad' if lid else 'Nueva propiedad', site_link,
        ('<div class="notice warn"><b>Para que se vea mejor en portales:</b><br>%s</div>' % '<br>'.join(e(p) for p in problems))
        if problems else '',
        ('/propiedades/%d' % lid) if lid else '/propiedades/nueva', csrf_field(ctx),
        e(v.get('title')), _opt([('venta', 'Venta'), ('renta', 'Renta')], v.get('operation', 'venta')),
        _opt(TYPES, v.get('property_type', 'departamento')), e(price),
        _opt([('MXN', 'MXN (pesos)'), ('USD', 'USD (dólares)')], v.get('currency', 'MXN')),
        e(v.get('price_date') or ''), _opt(STATUSES, v.get('status', 'borrador')), e(v.get('description')),
        num('m2_built'), num('m2_land'), num('bedrooms'), num('bathrooms'), num('parking'), e(maint), e(am),
        ' checked' if v.get('furnished') else '', ' checked' if v.get('pets') else '',
        e(v.get('street')), e(v.get('ext_number')), e(v.get('colonia')), e(v.get('municipio')),
        e(v.get('estado') or ('Ciudad de México' if not lid else '')), e(v.get('cp')),
        ' checked' if v.get('show_exact_location') else '',
        ' checked' if v.get('share_in_bolsa') else '', e(v.get('share_split_pct', 50)), num('commission_pct'),
        rp_box, e(v.get('internal_note')), 'Guardar' if lid else 'Crear y subir fotos', photos_html)
    return layout('Propiedad', body, ctx, 'propiedades')


# ---------- leads ----------
def _leads_list(con, rows):
    out = []
    for r in rows:
        lst = con.execute('SELECT title, ref FROM listings WHERE id=?', (r['listing_id'],)).fetchone() if r['listing_id'] else None
        wa = whatsapp.wa_link(r['phone'], 'Hola %s, gracias por escribir%s.' % (
            (r['name'] or '').split(' ')[0], (' sobre ' + lst['title']) if lst else '')) if r['phone'] else ''
        out.append('<div class="card" style="gap:6px"><div class="row" style="justify-content:space-between"><b>%s</b>'
                   '<span class="pill %s">%s</span></div><span class="small muted">%s · %s · %s</span>%s'
                   '<p class="small" style="margin:0">%s</p><div class="row">%s%s</div></div>' % (
                       e(r['name'] or 'Sin nombre'), e(r['status']), e(label(LEAD_STATUSES, r['status'])),
                       e(nice_date(r['created_at'])), e(r['source']), e(lst['ref'] if lst else 'general'),
                       ('<span class="small">%s</span>' % e(lst['title'])) if lst else '', e(r['message']),
                       ('<a class="btn wa small" href="%s" target="_blank" rel="noopener">Responder por WhatsApp</a>' % e(wa)) if wa else '',
                       ('<a class="btn ghost small" href="mailto:%s">Correo</a>' % e(r['email'])) if r['email'] else ''))
    return '<div class="list">%s</div>' % ''.join(out)


def leads(con, ctx):
    a = ctx['agency']
    rows = con.execute("SELECT * FROM leads WHERE agency_id=? AND status!='descartado' ORDER BY id DESC LIMIT 200", (a['id'],)).fetchall()
    ob = con.execute("SELECT COUNT(*) FROM outbox o JOIN leads l ON o.ref='lead:'||l.id WHERE l.agency_id=?", (a['id'],)).fetchone()[0]
    body = ('<h1>Clientes</h1><p class="muted small">Cada cliente también se prepara para GoHighLevel '
            '(%d operaciones en modo prueba, nada enviado).</p>%s') % (
        ob, _leads_list(con, rows) if rows else '<p class="muted">Aún no hay clientes.</p>')
    return layout('Clientes', body, ctx, 'clientes')


# ---------- portals ----------
def portals(con, ctx, flash=''):
    a = ctx['agency']
    rows = con.execute("SELECT * FROM listings WHERE agency_id=? AND status IN ('activa','apartada') ORDER BY title", (a['id'],)).fetchall()
    base = db.site_url(a)
    open_keys = [k for k, p in registry.PORTALS.items() if p['status'] in ('open', 'api')]
    head = ''.join('<th>%s</th>' % e(registry.PORTALS[k]['name']) for k in open_keys)
    trs = []
    for r in rows:
        pubs = {p['portal']: p for p in con.execute('SELECT * FROM portal_publications WHERE listing_id=?', (r['id'],))}
        cells = []
        for k in open_keys:
            p = pubs.get(k)
            on = bool(p and p['enabled'])
            cells.append('<td><form method="post" action="/portales/%d/%s">%s<button class="btn %s small">%s</button></form>%s</td>' % (
                r['id'], k, csrf_field(ctx), '' if on else 'ghost', 'Activo' if on else 'Activar',
                ('<span class="pill %s">%s</span>' % (e(p['status']), e(p['status']))) if on else ''))
        trs.append('<tr><td><b>%s</b><br><span class="small muted">%s</span></td>%s</tr>' % (e(r['title']), e(r['ref']), ''.join(cells)))
    feeds = ''.join('<li><b>%s</b>: <code>%s/feeds/%s.xml</code></li>' % (e(p['name']), e(base), k)
                    for k, p in registry.PORTALS.items() if p['status'] == 'open')
    soon = ''.join('<li><b>%s</b>: <span class="muted">%s</span></li>' % (e(p['name']), e(p['notes']))
                   for p in registry.PORTALS.values() if p['status'] == 'needs_agreement')
    body = ('%s<h1>Portales</h1><p class="muted">Activa cada propiedad una vez. Cuando cambies precio o fotos, '
            'los portales se actualizan solos.</p>'
            '<section class="card"><div class="tbl"><table><thead><tr><th>Propiedad</th>%s</tr></thead><tbody>%s</tbody></table></div>'
            '<p class="small muted">Mercado Libre: por ahora generamos la publicación en modo prueba; '
            'para publicar de verdad conectarás tu propia cuenta.</p></section>'
            '<section class="card"><h2>Tus feeds</h2><ul class="small">%s</ul></section>'
            '<section class="card"><h2>Próximamente</h2><ul class="small">%s</ul></section>') % (
        flash, head, ''.join(trs) or '<tr><td colspan="9" class="muted">Publica una propiedad (estado Activa) para activarla en portales.</td></tr>',
        feeds, soon)
    return layout('Portales', body, ctx, 'portales')


# ---------- Bolsa ----------
def bolsa(con, ctx, q=None, flash=''):
    a = ctx['agency']
    q = q or {}
    sql = ("SELECT l.*, ag.name AS agency_name FROM listings l JOIN agencies ag ON ag.id=l.agency_id "
           "WHERE l.share_in_bolsa=1 AND l.status IN ('activa','apartada') AND l.agency_id!=?")
    args = [a['id']]
    if q.get('colonia'):
        sql += ' AND l.colonia LIKE ?'
        args.append('%' + q['colonia'] + '%')
    if q.get('operation') in ('venta', 'renta'):
        sql += ' AND l.operation=?'
        args.append(q['operation'])
    rows = con.execute(sql + ' ORDER BY l.updated_at DESC LIMIT 100', args).fetchall()
    mine = {r['listing_id']: r for r in con.execute("SELECT * FROM shares WHERE sharing_agency_id=? AND status='activa'", (a['id'],))}
    items = []
    for r in rows:
        c = db.canonical(con, r['id'])
        img = c['photos'][0]['url_400'] if c['photos'] else ''
        shared = r['id'] in mine
        items.append('<div class="item" style="grid-template-columns:84px 1fr">%s<div style="min-width:0"><b>%s</b>'
                     '<span class="small muted">%s · %s · de %s</span><br><span class="small">Comisión compartida: '
                     'tú recibes %d%%</span><form method="post" action="/bolsa/%d/%s" style="margin-top:6px">%s'
                     '<button class="btn small %s">%s</button></form></div></div>' % (
                         ('<img src="%s" alt="">' % e(img)) if img else '<span class="ph"></span>', e(c['title']),
                         e(money(c['price'], c['currency'])), e(facts_line(c)), e(r['agency_name']),
                         100 - int(r['share_split_pct'] or 50), r['id'], 'retirar' if shared else 'compartir', csrf_field(ctx),
                         'ghost' if shared else '', 'En mi sitio ✓ (quitar)' if shared else 'Mostrar en mi sitio'))
    body = ('%s<h1>Bolsa</h1><p class="muted">Propiedades que otros asesores comparten. Muéstralas en tu sitio: '
            'si tu cliente compra, la comisión se divide como indica cada una.</p>'
            '<form class="row card" method="get" action="/bolsa"><input name="colonia" placeholder="Colonia" value="%s" style="flex:2">'
            '<select name="operation" style="flex:1"><option value="">Venta y renta</option>%s</select>'
            '<button class="btn small">Buscar</button></form><div class="list">%s</div>') % (
        flash, e(q.get('colonia')), _opt([('venta', 'Venta'), ('renta', 'Renta')], q.get('operation')),
        ''.join(items) or '<p class="muted">No hay propiedades compartidas con ese filtro.</p>')
    return layout('Bolsa', body, ctx, 'bolsa')


# ---------- my site ----------
def site_settings(con, ctx, ok='', error=''):
    a = ctx['agency']
    designs = ''.join('<label class="check card" style="gap:6px"><input type="radio" name="design" value="%s"%s> '
                      '<span><b>%s</b><br><span class="small muted">%s</span></span></label>'
                      % (k, ' checked' if a['design'] == k else '', n, d) for k, n, d in DESIGNS)
    pro = a['plan'] in ('pro', 'agencia')
    domain = ('<section class="card"><h2>Tu propio dominio</h2>%s</section>' % (
        ('<form class="stack" method="post" action="/sitio/dominio">%s<label>Dominio<input name="domain" value="%s" '
         'placeholder="micasa.mx"></label><button class="btn ghost">Guardar dominio</button></form>%s' % (
             csrf_field(ctx), e(a['custom_domain']),
             ('<p class="small">Para conectarlo crea en tu proveedor de dominio un registro <b>CNAME</b> de <code>www</code> '
              'hacia <code>sites.%s</code> y un registro <b>TXT</b> <code>llave-verify=%s</code>. Estado: %s.</p>' % (
                  e(db.BASE_DOMAIN), e(a['slug']),
                  'verificado' if a['domain_verified_at'] else 'pendiente (la verificación se activa en producción)'))
             if a['custom_domain'] else ''))
        if pro else '<p class="muted">Incluido en el plan Pro. Mientras tanto tu sitio vive gratis en '
                    '<code>%s</code>.</p>' % e(db.site_url(a))))
    body = ('%s%s<div class="row" style="justify-content:space-between"><h1>Mi sitio</h1>'
            '<a class="btn ghost small" href="%s" target="_blank" rel="noopener">Ver sitio ↗</a></div>'
            '<form class="stack" method="post" action="/sitio" enctype="multipart/form-data">%s'
            '<section class="card"><h2>Diseño</h2><div class="grid2">%s</div>'
            '<label>Color principal<input type="color" name="accent" value="%s" style="height:48px"></label></section>'
            '<section class="card"><h2>Textos</h2><label>Nombre<input name="name" value="%s" required></label>'
            '<label>Frase corta<input name="tagline" value="%s" maxlength="90" placeholder="Departamentos en la Roma y la Condesa"></label>'
            '<label>Sobre nosotros<textarea name="about">%s</textarea></label>'
            '<label>WhatsApp<input name="whatsapp" value="%s" inputmode="tel" required></label>'
            '<label>Correo de contacto<input name="email" type="email" value="%s"></label>'
            '<label>Ciudad<input name="city" value="%s"></label>'
            '<label>Logo (PNG o JPG)<input type="file" name="logo" accept="image/png,image/jpeg,image/webp"></label></section>'
            '<button class="btn">Guardar cambios</button></form>%s') % (
        notice(ok), notice(error, 'err'), e(db.site_url(a)), csrf_field(ctx), designs, e(a['accent']), e(a['name']),
        e(a['tagline']), e(a['about']), e(a['whatsapp']), e(a['email']), e(a['city']), domain)
    return layout('Mi sitio', body, ctx, 'sitio')


def landing():
    body = ('<div class="auth" style="max-width:640px"><h1 style="font-size:34px">Tu sitio inmobiliario gratis. '
            'Tus propiedades en Google y en los portales. Tus clientes en WhatsApp.</h1>'
            '<p class="muted">Sube cada propiedad una vez y listo. Sin tarjeta para empezar.</p>'
            '<div class="row"><a class="btn" href="/registro">Crear mi sitio gratis</a><a class="btn ghost" href="/entrar">Entrar</a></div>'
            '<p class="small muted">Versión local de prueba. Nada aquí es público todavía.</p></div>')
    return layout('Bienvenido', body)
