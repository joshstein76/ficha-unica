"""The agent panel (app.<base>): sign up, listings + photos, leads, portals, Bolsa, my site.
Pages are plain functions returning HTML; server.py handles routing, sessions and POSTs."""
import json

from .. import db, geo, ml_oauth, price_check, replies, whatsapp
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
    'servicios': '<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z"/>',
    'academia': '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/>',
}
TABS = [('inicio', 'Inicio', '/'), ('propiedades', 'Propiedades', '/propiedades'), ('clientes', 'Clientes', '/clientes'),
        ('portales', 'Portales', '/portales'), ('bolsa', 'Bolsa', '/bolsa'), ('sitio', 'Mi sitio', '/sitio'),
        ('servicios', 'Servicios', '/servicios'), ('academia', 'Academia', '/academia')]
DESKTOP_ONLY = {'servicios', 'academia'}  # on phones they live on Inicio


def _icon(k):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true">%s</svg>' % ICONS[k])


def layout(title, body, ctx=None, tab=None, flash=''):
    nav = ''
    top_right = '<a class="btn ghost small" href="/entrar">Entrar</a>'
    if ctx:
        nav = '<nav class="tabs">%s</nav>' % ''.join(
            '<a href="%s" class="%s">%s<span>%s</span></a>' % (href, ('on ' if k == tab else '') + ('desk' if k in DESKTOP_ONLY else ''), _icon(k), lab)
            for k, lab, href in TABS)
        top_right = ('<span class="row small"><a href="%s" target="_blank" rel="noopener">Ver mi sitio ↗</a>'
                     '<form method="post" action="/salir" style="margin:0">%s<button class="btn ghost small">Salir</button></form></span>'
                     % (e(db.site_url(ctx['agency'])), csrf_field(ctx)))
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>%s · Ficha Única</title><link rel="stylesheet" href="%s"><style>%s</style></head><body>'
            '<header class="top"><a class="logo" href="/">Ficha <span>Única</span></a>%s</header>%s'
            '<main class="wrap">%s%s</main><footer class="wrap small muted" style="padding-top:0">Ficha Única es un servicio de %s · <a href="/terminos">Términos</a> · <a href="/privacidad">Privacidad</a></footer></body></html>') % (
        e(title), FONTS, PANEL, top_right, nav, flash, body, e(db.OWNER))


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
        (n_all > 0, 'Sube tu primera propiedad', '/nueva'),
        (con.execute('SELECT COUNT(*) FROM photos p JOIN listings l ON l.id=p.listing_id WHERE l.agency_id=?', (a['id'],)).fetchone()[0] >= 5,
         'Agrega al menos 5 fotos', '/propiedades'),
        (n_list > 0, 'Publícala (estado: Activa)', '/propiedades'),
        (n_feed > 0, 'Actívala en los portales', '/portales'),
        (bool(a['tagline'] and a['about']), 'Personaliza tu sitio', '/sitio'),
    ]
    done = sum(1 for s in steps if s[0])
    leads = con.execute('SELECT * FROM leads WHERE agency_id=? ORDER BY id DESC LIMIT 5', (a['id'],)).fetchall()
    n_stale = len(price_check.stale_listings(con, a['id']))
    body = (('<div class="notice warn">%d precio%s sin confirmar en 30 días. <a href="/precios">Confírmalos con un toque</a></div>'
             % (n_stale, '' if n_stale == 1 else 's')) if n_stale else '') + ('%s<div><h1>Hola, %s</h1><p class="muted">Tu sitio: <a href="%s" target="_blank" rel="noopener">%s</a></p></div>'
            '<div class="stats"><div class="stat"><b>%d</b><small>Propiedades publicadas</small></div>'
            '<div class="stat"><b>%d/%d</b><small>Usadas en plan %s</small></div>'
            '<div class="stat"><b>%d</b><small>Clientes nuevos</small></div>'
            '<div class="stat"><b>%d</b><small>Publicaciones en portales</small></div></div>'
            '%s'
            '<section class="card"><div class="row" style="justify-content:space-between"><h2>Últimos clientes</h2>'
            '<a href="/clientes">Ver todos</a></div>%s</section>'
            '<section class="grid2"><a class="card" href="/servicios" style="text-decoration:none;color:inherit"><h2>Servicios</h2>'
            '<span class="small muted">Póliza para rentas, clientes de lujo, Miami y marketing con IA.</span></a>'
            '<a class="card" href="/academia" style="text-decoration:none;color:inherit"><h2>Academia</h2>'
            '<span class="small muted">Clases cortas para vender y rentar más.</span></a></section>') % (
        notice('¡Listo! Tu sitio ya existe. Ahora sube tu primera propiedad.') if welcome else '',
        e(a['name'] if ctx['user']['name'].split(' ')[0].lower() in replies.GENERIC_ACCOUNT else ctx['user']['name'].split(' ')[0]),
        e(db.site_url(a)), e(db.site_url(a).split('//')[1]),
        n_list, n_all, limit, e(a['plan']), n_new, n_feed,
        ('<section class="card"><h2>Tu sitio listo en 5 pasos (%d/5)</h2><div class="list">%s</div></section>' % (done, ''.join(
            '<a class="row" href="%s" style="text-decoration:none;color:inherit"><span class="pill %s">%s</span>%s</a>'
            % (href, 'ok' if ok else 'pendiente', '✓' if ok else '•', e(t)) for ok, t, href in steps)))
        if done < 5 else '<div class="notice">✓ Tu sitio está completo. <a href="/nueva">Sube otra propiedad</a></div>',
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
            '<span class="row"><a class="btn ghost small" href="/propiedades/importar">Importar CSV</a>'
            '<a class="btn" href="/nueva">+ Nueva</a></span></div><div class="list">%s</div>'
            '<a class="btn fab" href="/nueva" aria-label="Nueva propiedad">+</a>') % (
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
        site_link = ('<span class="row small"><a href="%s" target="_blank" rel="noopener">Ver en mi sitio ↗</a>'
                     '<a href="%s/ficha" target="_blank" rel="noopener">Ficha para imprimir ↗</a></span>') % (
            e(db.listing_url(ctx['agency'], v)), e(db.listing_url(ctx['agency'], v)))
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
            '<label>Ubicación en el mapa: pega el enlace de Google Maps<input name="maps" value="%s" placeholder="https://www.google.com/maps/@19.43,-99.19,17z"></label>'
            '<label class="check"><input type="checkbox" name="show_exact_location" value="1"%s> Mostrar la dirección exacta (si no, solo la colonia y un punto aproximado)</label></section>'
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
        ('%s, %s' % (v['lat'], v['lng'])) if v.get('lat') is not None else '',
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
            '%s<section class="card"><h2>Tus feeds</h2><ul class="small">%s</ul></section>'
            '<section class="card"><h2>Próximamente</h2><ul class="small">%s</ul></section>') % (
        flash, head, ''.join(trs) or '<tr><td colspan="9" class="muted">Publica una propiedad (estado Activa) para activarla en portales.</td></tr>',
        _ml_card(con, ctx), feeds, soon)
    return layout('Portales', body, ctx, 'portales')


def _ml_card(con, ctx):
    st = ml_oauth.status(con, ctx['agency']['id'])
    if st.get('status') in ('conectada', 'demo'):
        inner = ('<p style="margin:0">Cuenta: <b>%s</b> <span class="pill %s">%s</span></p>'
                 '<form method="post" action="/portales/mercadolibre/desconectar">%s<button class="btn ghost small">Desconectar</button></form>') % (
            e(st.get('nickname') or ''), 'ok' if st['status'] == 'conectada' else 'pendiente',
            'conectada' if st['status'] == 'conectada' else 'demo, sin publicar de verdad', csrf_field(ctx))
    else:
        inner = ('<p class="small muted" style="margin:0">Publica en Mercado Libre Inmuebles con tu propia cuenta. '
                 'Tus precios y fotos se actualizan solos.</p><div class="row"><a class="btn small" href="/portales/mercadolibre/conectar">Conectar mi cuenta</a>'
                 '%s</div>') % ('' if st.get('configured') else
                                '<form method="post" action="/portales/mercadolibre/conectar">%s<input type="hidden" name="demo" value="1">'
                                '<button class="btn ghost small">Ver demo</button></form>' % csrf_field(ctx))
    return '<section class="card"><h2>Mercado Libre</h2>%s</section>' % inner


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
    if q.get('property_type') in dict(TYPES):
        sql += ' AND l.property_type=?'
        args.append(q['property_type'])
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
    rows = con.execute(sql + ' ORDER BY l.updated_at DESC LIMIT 100', args).fetchall()
    pins = []
    mine = {r['listing_id']: r for r in con.execute("SELECT * FROM shares WHERE sharing_agency_id=? AND status='activa'", (a['id'],))}
    items = []
    for r in rows:
        c = db.canonical(con, r['id'])
        img = c['photos'][0]['url_400'] if c['photos'] else ''
        shared = r['id'] in mine
        if r['lat'] is not None and r['lng'] is not None:
            la, ln = geo.approx(r['lat'], r['lng'], exact=bool(r['show_exact_location']))
            pins.append({'lat': la, 'lng': ln, 't': c['title'], 'p': money(c['price'], c['currency']), 'a': r['agency_name']})
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
            '<form class="card filters" method="get" action="/bolsa"><input name="colonia" placeholder="Colonia" value="%s">'
            '<select name="operation"><option value="">Venta y renta</option>%s</select>'
            '<select name="property_type"><option value="">Cualquier tipo</option>%s</select>'
            '<select name="beds"><option value="">Recámaras</option>%s</select>'
            '<input name="min" inputmode="numeric" placeholder="Precio mín." value="%s">'
            '<input name="max" inputmode="numeric" placeholder="Precio máx." value="%s">'
            '<select name="currency"><option value="">MXN o USD</option>%s</select>'
            '<button class="btn small">Buscar</button></form>'
            '<p class="small muted">%d resultado%s · ubicaciones aproximadas</p>%s<div class="list">%s</div>') % (
        flash, e(q.get('colonia')), _opt([('venta', 'Venta'), ('renta', 'Renta')], q.get('operation')),
        _opt(TYPES, q.get('property_type')), _opt([(str(n), '%d+' % n) for n in (1, 2, 3, 4)], q.get('beds')),
        e(q.get('min')), e(q.get('max')), _opt([('MXN', 'MXN'), ('USD', 'USD')], q.get('currency')),
        len(rows), '' if len(rows) == 1 else 's', map_block(pins),
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
            '<section class="card"><h2>Primer mensaje a tus clientes</h2><p class="small muted">Es lo primero que recibe por WhatsApp '
            'quien te escribe. Puedes usar {nombre}, {propiedad}, {asesor} e {inmobiliaria}. Déjalo vacío para usar el mensaje recomendado.</p>'
            '<label>Cuando sabemos su nombre<textarea name="first_reply" rows="3" placeholder="%s">%s</textarea></label>'
            '<label>Cuando no sabemos su nombre<textarea name="first_reply_noname" rows="3" placeholder="%s">%s</textarea></label>'
            '<p class="small"><b>Así se verá:</b> %s</p></section>'
            '<button class="btn">Guardar cambios</button></form>%s') % (
        notice(ok), notice(error, 'err'), e(db.site_url(a)), csrf_field(ctx), designs, e(a['accent']), e(a['name']),
        e(a['tagline']), e(a['about']), e(a['whatsapp']), e(a['email']), e(a['city']),
        e(replies.DEFAULT_FIRST_REPLY), e(a['first_reply']), e(replies.DEFAULT_FIRST_REPLY_NONAME), e(a['first_reply_noname']),
        e(replies.render(a, 'Ana Pérez', 'Departamento con terraza en la Roma Norte', ctx['user']['name'])), domain)
    return layout('Mi sitio', body, ctx, 'sitio')


def landing():
    body = ('<div class="auth" style="max-width:640px"><h1 style="font-size:34px">Tu sitio inmobiliario gratis. '
            'Tus propiedades en Google y en los portales. Tus clientes en WhatsApp.</h1>'
            '<p class="muted">Sube cada propiedad una vez y listo. Sin tarjeta para empezar.</p>'
            '<div class="row"><a class="btn" href="/registro">Crear mi sitio gratis</a><a class="btn ghost" href="/entrar">Entrar</a></div>'
            '<p class="small muted">Versión local de prueba. Nada aquí es público todavía.</p></div>')
    return layout('Bienvenido', body)


# ---------- import ----------
def import_page(ctx, preview=None, csv_text='', error='', done=None):
    body = ['<h1>Importar propiedades</h1><p class="muted">¿Vienes de otro sistema? Exporta tus propiedades a CSV o Excel '
            '(guárdalo como CSV) y súbelo aquí. Entran como borrador para que las revises antes de publicar.</p>',
            notice(error, 'err')]
    if done:
        body.append(notice('Listo: %d propiedades importadas como borrador.%s%s' % (
            len(done['created']), (' %d omitidas.' % len(done['skipped'])) if done['skipped'] else '',
            (' Estamos bajando %d fotos de tus enlaces; aparecen en cada propiedad en unos minutos.' % done['photos_queued'])
            if done.get('photos_queued') else '')))
        body.append('<p><a class="btn" href="/propiedades">Ver mis propiedades</a></p>')
    if preview:
        n = sum(1 for r in preview['rows'] if r['action'] == 'crear')
        cols = ', '.join('%s ← "%s"' % (e(k), e(v)) for k, v in preview['columns_detected'].items())
        trs = ''.join('<tr><td>%d</td><td>%s</td><td>%s</td><td><span class="pill %s">%s</span><br><span class="small">%s</span></td></tr>' % (
            r['line'], e(r['data'].get('title') or '—'),
            e(money((r['data']['price_cents'] // 100) if r['data'].get('price_cents') is not None else None, r['data'].get('currency', 'MXN'))),
            'ok' if r['action'] == 'crear' else 'error', 'se crea' if r['action'] == 'crear' else 'se omite',
            e('; '.join(r['problems']))) for r in preview['rows'][:300])
        body.append('<section class="card"><h2>Vista previa: %d de %d filas se crean</h2>%s<p class="small muted">Columnas reconocidas: %s</p>'
                    '<div class="tbl"><table><thead><tr><th>Fila</th><th>Título</th><th>Precio</th><th></th></tr></thead><tbody>%s</tbody></table></div>'
                    '<form method="post" action="/propiedades/importar">%s<input type="hidden" name="step" value="commit">'
                    '<textarea name="csv" hidden>%s</textarea><button class="btn"%s>Importar %d propiedades</button></form>'
                    '<p class="small muted">Si tu archivo trae enlaces de fotos, las bajamos solas (máximo 20 por propiedad).</p></section>' % (
                        n, preview['total'], ''.join(notice(w, 'warn') for w in preview['warnings']), cols, trs, csrf_field(ctx),
                        e(csv_text), '' if n else ' disabled', n))
    body.append('<form class="stack card" method="post" action="/propiedades/importar" enctype="multipart/form-data">%s'
                '<input type="hidden" name="step" value="preview"><label>Archivo CSV<input type="file" name="archivo" accept=".csv,text/csv"></label>'
                '<label>…o pega el contenido<textarea name="csv" placeholder="titulo,precio,colonia,municipio,estado&#10;Depto en la Roma,4500000,Roma Norte,Cuauhtémoc,CDMX"></textarea></label>'
                '<button class="btn ghost">Ver vista previa</button></form>' % csrf_field(ctx))
    return layout('Importar', ''.join(body), ctx, 'propiedades')


# ---------- Servicios + Academia ----------
SERVICES = [
    ('Póliza jurídica para rentas', 'RentaPóliza',
     'Protege a tus propietarios en cada renta. Actívala en la propiedad (casilla "Ofrecer póliza jurídica").', None, 'Próximamente'),
    ('¿Tienes un cliente o una propiedad de lujo en Polanco?', 'VIVE Polanco',
     'Refiérenos compradores o propiedades de lujo en CDMX. Te contactamos para acordar la comisión.',
     'https://wa.me/525578358858?text=' + 'Hola%2C%20soy%20asesor%20en%20Ficha%20%C3%9Anica%20y%20quiero%20referir%20un%20cliente%20o%20propiedad%20de%20lujo.',
     'Referir por WhatsApp'),
    ('¿Vendes en Miami?', 'IDX Bloom', 'Sitio web con búsqueda MLS (IDX) para asesores en Florida.', 'https://idxbloom.com', 'Conocer IDX Bloom'),
    ('Marketing con IA y SEO', 'Ciao Bella Marketing', 'Campañas, contenido y posicionamiento en Google y en asistentes de IA.',
     'https://ciaobellamarketing.com', 'Conocer Ciao Bella'),
]
LESSONS = [
    ('Tu primera propiedad en 10 minutos', 'Del celular a tu sitio y a los portales.'),
    ('Fotos que venden con tu celular', 'Luz, ángulos y orden: lo que más cambia una ficha.'),
    ('Aparecer en Google y en ChatGPT', 'Qué lee un buscador en tu ficha y cómo ayudarle.'),
    ('Responder en 5 minutos por WhatsApp', 'El primer mensaje y cómo agendar la visita.'),
    ('Compartir en la Bolsa sin perder comisión', 'Cómo funciona la división y qué acordar por escrito.'),
    ('Rentas seguras', 'Contrato, póliza jurídica y entrega del inmueble.'),
]


def services(ctx):
    cards = ''.join('<div class="card"><span class="small muted">%s</span><h2>%s</h2><p style="margin:0">%s</p>%s</div>' % (
        e(brand), e(t), e(d), ('<a class="btn small ghost" href="%s" target="_blank" rel="noopener">%s</a>' % (e(url), e(cta)))
        if url else '<span class="pill pendiente">%s</span>' % e(cta)) for t, brand, d, url, cta in SERVICES)
    body = ('<h1>Servicios</h1><p class="muted">Todo lo que tu negocio necesita, con empresas de la misma familia que Ficha Única.</p>'
            '<div class="grid2 wide">%s</div>') % cards
    return layout('Servicios', body, ctx, 'servicios')


def academy(ctx):
    items = ''.join('<div class="card" style="gap:4px"><b>%s</b><span class="small muted">%s</span><span class="pill pendiente">Próximamente</span></div>'
                    % (e(t), e(d)) for t, d in LESSONS)
    body = ('<h1>Academia</h1><p class="muted">Clases cortas, en video y en español, para vender y rentar más con Ficha Única. '
            'Gratis para todos los asesores.</p><div class="grid2">%s</div>') % items
    return layout('Academia', body, ctx, 'academia')


# ---------- legal drafts (platform) ----------
def legal(kind):
    if kind == 'terminos':
        title, text = 'Términos de uso', (
            'Ficha Única es un servicio de %s. Al crear tu cuenta aceptas publicar solo propiedades que tienes derecho a '
            'anunciar, con información verdadera y precios con fecha. Eres responsable del contenido y de las fotos que subes. '
            'Podemos retirar anuncios falsos, duplicados o que infrinjan derechos de terceros. El plan Gratis puede cambiar con aviso previo.' % db.OWNER)
    else:
        title, text = 'Aviso de privacidad (asesores)', (
            '%s es responsable de los datos de tu cuenta (nombre, correo, WhatsApp, datos de tu inmobiliaria). Los usamos para '
            'darte el servicio, soporte y avisos de tu cuenta. Los datos de los clientes que te escriben desde tu sitio los tratamos '
            'por cuenta tuya, como encargado. Derechos ARCO: escríbenos desde tu cuenta.' % db.OWNER)
    body = ('<div class="auth" style="max-width:720px"><h1>%s</h1><p>%s</p><p class="notice warn"><b>BORRADOR</b>: texto de trabajo; '
            'lo revisa un abogado (Ley Federal de Protección de Datos Personales en Posesión de los Particulares, 2025) antes de publicarse.</p></div>') % (
        e(title), e(text))
    return layout(title, body)


# ---------- first-listing wizard (3 taps) ----------
def _steps(n):
    labels = ['Fotos', 'Dónde y cuánto', 'Publicar']
    return '<div class="wsteps">%s</div>' % ''.join(
        '<span class="%s">%d · %s</span>' % ('on' if i + 1 == n else ('done' if i + 1 < n else ''), i + 1, l)
        for i, l in enumerate(labels))


def wizard_1(ctx, welcome=False, error=''):
    chips = ''.join('<label class="chip"><input type="radio" name="property_type" value="%s"%s><span>%s</span></label>'
                    % (k, ' checked' if k == 'departamento' else '', e(v)) for k, v in TYPES)
    body = ('%s%s<h1>%s</h1><p class="muted">Empieza con las fotos. Las ajustamos solas.</p>%s'
            '<form class="stack card" method="post" action="/nueva" enctype="multipart/form-data">%s'
            '<label class="bigpick"><input type="file" name="fotos" accept="image/*" multiple required '
            'onchange="var n=this.files.length;this.nextElementSibling.textContent=n?(n+(n==1?\' foto elegida\':\' fotos elegidas\')):\'📷 Elegir fotos\'">'
            '<span>📷 Elegir fotos</span><small class="muted">Del celular o la computadora · mínimo 600 px</small></label>'
            '<div class="seg"><label><input type="radio" name="operation" value="venta" checked><span>Venta</span></label>'
            '<label><input type="radio" name="operation" value="renta"><span>Renta</span></label></div>'
            '<div class="chips">%s</div><button class="btn">Siguiente</button></form>'
            '<p class="small muted">¿Prefieres el formulario completo? <a href="/propiedades/nueva">Ábrelo aquí</a> · '
            '¿Vienes de otro sistema? <a href="/propiedades/importar">Importa tu CSV</a></p>') % (
        notice('¡Listo! Tu sitio ya existe. Sube tu primera propiedad: son 3 pasos.') if welcome else '',
        _steps(1), 'Tu primera propiedad' if welcome else 'Nueva propiedad', notice(error, 'err'), csrf_field(ctx), chips)
    return layout('Nueva propiedad', body, ctx, 'propiedades')


def wizard_2(con, ctx, l, error=''):
    n = con.execute('SELECT COUNT(*) FROM photos WHERE listing_id=?', (l['id'],)).fetchone()[0]
    v = dict(l)
    num = lambda k: '' if v.get(k) is None else ('%g' % v[k])
    body = ('%s<h1>Dónde y cuánto</h1><p class="muted">%d fotos listas.</p>%s'
            '<form class="stack card" method="post" action="/nueva/%d/2">%s'
            '<div class="grid2"><label>Precio<input name="price" inputmode="numeric" value="%s" placeholder="4500000" autofocus></label>'
            '<label>Moneda<select name="currency">%s</select></label>'
            '<label>Colonia<input name="colonia" value="%s" required placeholder="Roma Norte"></label>'
            '<label>Alcaldía o municipio<input name="municipio" value="%s" required placeholder="Cuauhtémoc"></label>'
            '<label>Estado<input name="estado" value="%s" required></label>'
            '<label>m² construcción<input name="m2_built" inputmode="decimal" value="%s"></label>'
            '<label>Recámaras<input name="bedrooms" inputmode="numeric" value="%s"></label>'
            '<label>Baños<input name="bathrooms" inputmode="decimal" value="%s"></label></div>'
            '<button class="btn">Siguiente</button></form>') % (
        _steps(2), n, notice(error, 'err'), l['id'], csrf_field(ctx),
        '' if v.get('price_cents') is None else '%d' % (v['price_cents'] // 100),
        _opt([('MXN', 'MXN (pesos)'), ('USD', 'USD (dólares)')], v.get('currency') or 'MXN'),
        e(v.get('colonia')), e(v.get('municipio')), e(v.get('estado') or 'Ciudad de México'),
        num('m2_built'), num('bedrooms'), num('bathrooms'))
    return layout('Nueva propiedad', body, ctx, 'propiedades')


def suggested_title(l):
    v = dict(l)
    t = label(TYPES, v.get('property_type') or 'departamento')
    bits = ['%s en %s en %s' % (t, v.get('operation') or 'venta', v.get('colonia') or '')]
    if v.get('m2_built'):
        bits.append('%g m²' % v['m2_built'])
    if v.get('bedrooms'):
        bits.append('%d recámara%s' % (v['bedrooms'], '' if v['bedrooms'] == 1 else 's'))
    return ', '.join(bits)[:100]


def suggested_description(l):
    v = dict(l)
    parts = ['%s en %s en %s, %s.' % (label(TYPES, v.get('property_type')), v.get('operation'), v.get('colonia') or '',
                                     v.get('municipio') or '')]
    facts = []
    if v.get('m2_built'):
        facts.append('%g m² de construcción' % v['m2_built'])
    if v.get('bedrooms'):
        facts.append('%d recámara%s' % (v['bedrooms'], '' if v['bedrooms'] == 1 else 's'))
    if v.get('bathrooms'):
        facts.append('%g baño%s' % (v['bathrooms'], '' if v['bathrooms'] == 1 else 's'))
    if facts:
        parts.append(', '.join(facts).capitalize() + '.')
    parts.append('Escríbenos por WhatsApp para más información o para agendar una visita.')
    return ' '.join(parts)


def wizard_3(ctx, l, error=''):
    body = ('%s<h1>Revisa y publica</h1>%s<form class="stack card" method="post" action="/nueva/%d/3">%s'
            '<label>Título<input name="title" value="%s" maxlength="100" required></label>'
            '<label>Descripción<textarea name="description">%s</textarea></label>'
            '<label class="check"><input type="checkbox" name="portales" value="1" checked> También en portales y buscadores gratuitos</label>'
            '<button class="btn">Publicar en mi sitio</button></form>'
            '<p class="small muted">Podrás cambiar todo después en Propiedades.</p>') % (
        _steps(3), notice(error, 'err'), l['id'], csrf_field(ctx),
        e(l['title'] if l['title'] != DRAFT_TITLE else suggested_title(l)),
        e(l['description'] or suggested_description(l)))
    return layout('Nueva propiedad', body, ctx, 'propiedades')


def wizard_done(ctx, l):
    url = db.listing_url(ctx['agency'], l)
    share = whatsapp.wa_link('', 'Mira esta propiedad: %s %s' % (l['title'], url))
    body = ('<div class="auth" style="text-align:center"><div style="font-size:48px">🎉</div><h1>¡Publicada!</h1>'
            '<p class="muted">Ya está en tu sitio. Compártela con tus clientes.</p>'
            '<a class="btn" href="%s" target="_blank" rel="noopener">Ver en mi sitio</a>'
            '<a class="btn wa" href="%s" target="_blank" rel="noopener">Compartir por WhatsApp</a>'
            '<a class="btn ghost" href="/nueva">Subir otra</a></div>') % (e(url), e(share))
    return layout('¡Publicada!', body, ctx, 'propiedades')


DRAFT_TITLE = 'Propiedad nueva (borrador)'


LEAFLET = ('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">'
           '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>')


def map_block(pins, height=280):
    """Leaflet + OpenStreetMap tiles. Pins are already snapped to a ~250 m grid unless the agent chose exact."""
    if not pins:
        return ''
    return ('%s<div id="map" class="map" style="height:%dpx" role="img" aria-label="Mapa de propiedades (aproximado)"></div>'
            '<script>(function(){var P=%s;if(!window.L)return;var m=L.map("map",{scrollWheelZoom:false});'
            'L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:18,attribution:"© OpenStreetMap"}).addTo(m);'
            'var g=[];P.forEach(function(p){var c=L.circleMarker([p.lat,p.lng],{radius:9,weight:2,color:"#0f5c4c",fillOpacity:.6}).addTo(m);'
            'var d=document.createElement("div");var b=document.createElement("b");b.textContent=p.t;d.appendChild(b);'
            'd.appendChild(document.createElement("br"));d.appendChild(document.createTextNode(p.p+" · "+p.a));c.bindPopup(d);g.push([p.lat,p.lng]);});'
            'm.fitBounds(g,{padding:[30,30],maxZoom:15});})();</script>') % (LEAFLET, height, json.dumps(pins, ensure_ascii=False).replace('</', '<\\/'))


# ---------- prices: one-tap confirm ----------
def prices(con, ctx, flash=''):
    stale = price_check.stale_listings(con, ctx['agency']['id'])
    rows = ''.join('<div class="card" style="gap:6px"><b>%s</b><span class="small muted">%s · %s</span>'
                   '<span>%s <span class="muted small">%s</span></span><div class="row">'
                   '<form method="post" action="/precios/%d">%s<button class="btn small">Sigue igual</button></form>'
                   '<a class="btn ghost small" href="/propiedades/%d">Cambiar precio</a></div></div>' % (
                       e(s['title']), e(s['ref']), 'sin fecha' if not s['price_date'] else 'desde ' + nice_date(s['price_date']),
                       e(money(s['price'], s['currency'])), '(%s días)' % s['days'] if s.get('days') is not None else '',
                       s['listing_id'], csrf_field(ctx), s['listing_id']) for s in stale)
    body = ('%s<h1>Confirma tus precios</h1><p class="muted">Los portales y tus clientes confían más en precios recientes. '
            'Cada 30 días te pedimos confirmarlos: un toque y listo.</p>%s') % (
        flash, rows or notice('✓ Todos tus precios están al día.'))
    return layout('Precios', body, ctx, 'propiedades')
