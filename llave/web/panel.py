"""The agent panel (app.<base>): sign up, listings + photos, leads, portals, Bolsa, my site.
Pages are plain functions returning HTML; server.py handles routing, sessions and POSTs."""
import json

from .. import billing, db, geo, lead_watch, ml_oauth, price_check, replies, whatsapp
from ..feeds import registry, validate
from .common import (e, money, nice_date, facts_line, label, csrf_token, TYPES, STATUSES, LEAD_STATUSES, DESIGNS)
from .styles import BRAND_COLOR, FONTS, PANEL, PRECONNECT, logo

ICONS = {
    'inicio': '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    'propiedades': '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h8M8 15h5"/>',
    'clientes': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6"/>',
    'portales': '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    'bolsa': '<path d="M7 7h10l-1 13H8z"/><path d="M9 7a3 3 0 0 1 6 0"/>',
    'sitio': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
    'servicios': '<path d="M12 3l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.4 6.8 19.1l1-5.8L3.5 9.2l5.9-.9z"/>',
    'academia': '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c3 2 9 2 12 0v-5"/>',
    'estadisticas': '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    'invitar': '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M19 8v6M16 11h6"/>',
    'publicar': '<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1"/>',
}
def props(n):
    return '1 propiedad' if n == 1 else '%d propiedades' % n


TABS = [('inicio', 'Inicio', '/'), ('propiedades', 'Propiedades', '/propiedades'), ('clientes', 'Clientes', '/clientes'),
        ('portales', 'Portales', '/portales'), ('bolsa', 'Bolsa', '/bolsa'), ('sitio', 'Mi sitio', '/sitio'),
        ('estadisticas', 'Estadísticas', '/estadisticas'), ('publicar', 'Qué publicar', '/que-publicar'), ('invitar', 'Invitar', '/invitar'), ('servicios', 'Servicios', '/servicios'),
        ('academia', 'Academia', '/academia')]
DESKTOP_ONLY = {'estadisticas', 'publicar', 'invitar', 'servicios', 'academia'}  # on phones they live on Inicio


def _icon(k):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true">%s</svg>' % ICONS[k])


def layout(title, body, ctx=None, tab=None, flash=''):
    nav = ''
    top_right = '<a class="btn ghost small" href="/entrar">Entrar</a>'
    if ctx:
        nav = '<nav class="tabs" aria-label="Secciones">%s</nav>' % ''.join(
            '<a href="%s" class="%s"%s>%s<span>%s</span></a>' % (href, ('on ' if k == tab else '') + ('desk' if k in DESKTOP_ONLY else ''),
                                                                 ' aria-current="page"' if k == tab else '', _icon(k), lab)
            for k, lab, href in TABS)
        top_right = ('<span class="row small">' + ('<a href="/admin">Admin</a>' if ctx['user']['role'] == 'admin' else '') +
                     '<a href="%s" target="_blank" rel="noopener">Ver mi sitio ↗</a>'
                     '<form method="post" action="/salir" style="margin:0">%s<button class="btn ghost small">Salir</button></form></span>'
                     % (e(db.site_url(ctx['agency'])), csrf_field(ctx)))
    return ('<!doctype html><html lang="es-MX"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<title>%s · Ficha Única</title><link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="%s">'
            '<link rel="apple-touch-icon" href="/_s/apple-touch-icon.png"><meta name="apple-mobile-web-app-capable" content="yes">'
            '%s<link rel="stylesheet" href="%s"><style>%s</style></head><body>'
            '<a class="skip" href="#main">Saltar al contenido</a><header class="top"><a class="logo" href="/">%s</a>%s</header>%s'
            '<main id="main" class="wrap">%s%s</main><footer class="wrap small muted" style="padding-top:0;display:block">Ficha Única es un servicio de %s · <a href="/terminos">Términos</a> · <a href="/privacidad">Privacidad</a></footer>'
            '<script>if("serviceWorker"in navigator)navigator.serviceWorker.register("/sw.js").catch(function(){})</script></body></html>') % (
        e(title), BRAND_COLOR, PRECONNECT, FONTS, PANEL, logo('fu-top'), top_right, nav, flash, body, e(db.OWNER))


def csrf_field(ctx):
    return '<input type="hidden" name="csrf" value="%s">' % csrf_token(ctx['token'])


def notice(msg, kind=''):
    return ('<div class="notice %s" role="%s">%s</div>' % (kind, 'alert' if kind == 'err' else 'status', e(msg))) if msg else ''


# ---------- auth ----------
def signup(error='', values=None, ref=''):
    v = values or {}
    ref = v.get('ref') or ref
    body = ('<div class="auth pub"><div class="intro"><h1>Crea tu sitio gratis.</h1>'
            '<p class="muted">Sube cada propiedad una vez. Sale en tu sitio, en Google y en la IA, y quien la ve te escribe a tu WhatsApp.</p>'
            '<p class="micro"><span>Sin tarjeta</span><span>Sin plazo forzoso</span><span>Desde tu celular</span></p></div>%s'
            '<form class="stack card" method="post" action="/registro"><input type="hidden" name="ref" value="%s">'
            '<label>Tu nombre<input name="name" value="%s" autocomplete="name" required></label>'
            '<label>Nombre de tu inmobiliaria o marca<input name="agency" value="%s" placeholder="Ej. Casas Roma" required></label>'
            '<label>Tu WhatsApp<input name="whatsapp" value="%s" inputmode="tel" placeholder="55 1234 5678" required></label>'
            '<label>Correo<input name="email" type="email" value="%s" autocomplete="email" required></label>'
            '<label>Contraseña<input name="password" type="password" minlength="8" autocomplete="new-password" required></label>'
            '<label class="check"><input type="checkbox" name="terms" value="1" required> Acepto los términos y el aviso de privacidad (borrador).</label>'
            '<button class="btn">Crear mi sitio gratis</button>'
            '<p class="small muted">¿Ya tienes cuenta? <a href="/entrar">Entrar</a></p></form></div>') % (
        notice(error, 'err'), e(ref), e(v.get('name')), e(v.get('agency')), e(v.get('whatsapp')), e(v.get('email')))
    return layout('Crear cuenta', body)


def login(error=''):
    body = ('<div class="auth pub"><div class="intro"><h1>Entrar</h1><p class="muted">Tu sitio, tus propiedades y tus clientes de WhatsApp.</p></div>%s'
            '<form class="stack card" method="post" action="/entrar">'
            '<label>Correo<input name="email" type="email" autocomplete="email" required></label>'
            '<label>Contraseña<input name="password" type="password" autocomplete="current-password" required></label>'
            '<button class="btn">Entrar</button><p class="small muted">¿Nuevo? <a href="/registro">Crea tu sitio gratis</a></p>'
            '</form></div>') % notice(error, 'err')
    return layout('Entrar', body)


# ---------- dashboard ----------
PILOT_WARN_DAYS = 7


def pilot_notice(agency, today=None):
    """Reminder in the last week of a free pilot plan (plan_until, set by tools/set_plan.py) and after it ends."""
    left = db.plan_days_left(agency, today)
    if left is None or left > PILOT_WARN_DAYS:
        return ''
    if left < 0:
        return '<div class="notice warn">Tu piloto terminó. <a href="/plan">Elige tu plan</a> para seguir con todo.</div>'
    when = 'hoy' if left == 0 else ('mañana' if left == 1 else 'en %d días' % left)
    return '<div class="notice warn">Tu piloto termina %s. <a href="/plan">Elige tu plan</a> para no perder nada.</div>' % when


def greeting(now=None):
    """Buenos días / tardes / noches by Mexico City time."""
    if now is None:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo('America/Mexico_City'))
        except Exception:
            from datetime import datetime
            now = datetime.utcnow()
    h = now.hour
    return 'Buenos días' if h < 12 else ('Buenas tardes' if h < 19 else 'Buenas noches')


# (icon, label, href, tag): tag '' = ready, text = shown as a small pill
HOME_TILES = [('propiedades', 'Mis propiedades', '/propiedades', ''), ('clientes', 'Mis clientes', '/clientes', ''),
              ('sitio', 'Mi sitio', '/sitio', ''), ('portales', 'Portales', '/portales', 'en camino'),
              ('publicar', 'Qué publicar', '/que-publicar', ''), ('academia', 'Academia', '/academia', 'pronto'),
              ('servicios', 'Servicios', '/servicios', ''), ('estadisticas', 'Estadísticas', '/estadisticas', '')]


def home_tiles():
    return '<nav class="tiles" aria-label="Tus herramientas">%s</nav>' % ''.join(
        '<a class="tile" href="%s">%s<b>%s</b>%s</a>' % (href, _icon(k), e(lab), ('<small>%s</small>' % e(tag)) if tag else '')
        for k, lab, href, tag in HOME_TILES)


def first_week(done, total, steps):
    pct = int(100 * done / total)
    return ('<section class="card"><div class="row" style="justify-content:space-between"><h2>Tu primera semana</h2><b>%d/%d</b></div>'
            '<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="%d" aria-valuenow="%d"><i style="width:%d%%"></i></div>'
            '<div class="list">%s</div></section>') % (done, total, total, done, pct, ''.join(
        '<a class="row" href="%s" style="text-decoration:none;color:inherit"><span class="pill %s">%s</span>%s</a>'
        % (href, 'ok' if ok else 'pendiente', '✓' if ok else '•', e(t)) for ok, t, href in steps))


def dashboard(con, ctx, welcome=False):
    a = ctx['agency']
    n_list = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status IN ('activa','apartada')", (a['id'],)).fetchone()[0]
    n_all = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status NOT IN ('vendida','rentada')", (a['id'],)).fetchone()[0]
    n_new = con.execute("SELECT COUNT(*) FROM leads WHERE agency_id=? AND status='nuevo'", (a['id'],)).fetchone()[0]
    n_feed = con.execute("SELECT COUNT(*) FROM portal_publications p JOIN listings l ON l.id=p.listing_id "
                         "WHERE l.agency_id=? AND p.enabled=1", (a['id'],)).fetchone()[0]
    limit = db.listing_limit(con, a)
    steps = [
        (n_all > 0, 'Sube tu primera propiedad', '/nueva'),
        (con.execute('SELECT COUNT(*) FROM photos p JOIN listings l ON l.id=p.listing_id WHERE l.agency_id=?', (a['id'],)).fetchone()[0] >= 5,
         'Agrega al menos 5 fotos', '/propiedades'),
        (n_list > 0, 'Publícala (estado: Activa)', '/propiedades'),
        (bool(a['tagline'] and a['about']), 'Personaliza tu sitio', '/sitio'),
        (bool(a['whatsapp']), 'Agrega tu WhatsApp para recibir clientes', '/perfil'),
    ]
    done = sum(1 for s in steps if s[0])
    leads = con.execute('SELECT * FROM leads WHERE agency_id=? ORDER BY id DESC LIMIT 5', (a['id'],)).fetchall()
    n_stale = len(price_check.stale_listings(con, a['id']))
    n_late = late_count(con, a['id'])
    body = pilot_notice(a) + (('<div class="notice err">⏰ %d cliente%s sin respuesta hace más de 5 minutos. <a href="/clientes?estado=nuevo">Respóndeles ya</a></div>'
             % (n_late, '' if n_late == 1 else 's')) if n_late else '') + (('<div class="notice warn">%d precio%s sin confirmar en 30 días. <a href="/precios">Confírmalos con un toque</a></div>'
             % (n_stale, '' if n_stale == 1 else 's')) if n_stale else '') + ('%s<div><h1>%s, %s</h1><p class="muted">Tu sitio: <a href="%s" target="_blank" rel="noopener">%s</a></p></div>'
            '<div class="stats"><div class="stat"><b>%d</b><small>Propiedades publicadas</small></div>'
            '<a class="stat" href="/plan" style="text-decoration:none;color:inherit"><b>%d/%d</b><small>Usadas en plan %s · cambiar</small></a>'
            '<div class="stat"><b>%d</b><small>Clientes nuevos</small></div>'
            '<div class="stat"><b>%d</b><small>Publicaciones en portales</small></div></div>'
            '%s%s'
            '<section class="card"><div class="row" style="justify-content:space-between"><h2>Últimos clientes</h2>'
            '<a href="/clientes">Ver todos</a></div>%s</section>'
            '<a class="card" href="/que-publicar" style="text-decoration:none;color:inherit"><h2>Qué publicar esta semana</h2>'
            '<span class="small muted">5 publicaciones listas para Instagram y Facebook.</span></a>'
            '<a class="card" href="/invitar" style="text-decoration:none;color:inherit"><h2>Invita a un colega · +%s</h2>'
            '<span class="small muted">Por cada colega que publique con tu enlace.</span></a>'
            '<section class="grid2"><a class="card" href="/estadisticas" style="text-decoration:none;color:inherit"><h2>Estadísticas</h2>'
            '<span class="small muted">Visitas, clientes y tu tiempo de respuesta.</span></a>'
            '<a class="card" href="/servicios" style="text-decoration:none;color:inherit"><h2>Servicios</h2>'
            '<span class="small muted">Póliza para rentas, clientes de lujo, Miami y marketing con IA.</span></a>'
            '<a class="card" href="/academia" style="text-decoration:none;color:inherit"><h2>Academia</h2>'
            '<span class="small muted">Clases cortas para vender y rentar más.</span></a></section>') % (
        notice('¡Listo! Tu sitio ya existe. Ahora sube tu primera propiedad.') if welcome else '',
        greeting(), e(a['name'] if ctx['user']['name'].split(' ')[0].lower() in replies.GENERIC_ACCOUNT else ctx['user']['name'].split(' ')[0]),
        e(db.site_url(a)), e(db.site_url(a).split('//')[1]),
        n_list, n_all, limit, e(a['plan']), n_new, n_feed,
        home_tiles(),
        first_week(done, len(steps), steps) if done < len(steps) else '<div class="notice">✓ Tu primera semana está completa. <a href="/nueva">Sube otra propiedad</a></div>',
        _leads_list(con, leads) if leads else '<p class="muted">Aún no tienes clientes. Cuando alguien escriba desde tu sitio, aparece aquí y en WhatsApp.</p>', props(db.REFERRAL_BONUS_LISTINGS))
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


def listing_form(con, ctx, l=None, error='', ok='', suggestion=None):
    v = dict(l) if l else {}
    if suggestion:
        v['title'], v['description'] = suggestion['title'], suggestion['description']
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
        ai_html = _ai_box(con, ctx, lid, suggestion)
    site_link = ''
    if lid and v.get('status') in db.PUBLIC_STATUSES:
        if db.plan_has(ctx['agency'], 'tools'):
            site_link = ('<span class="row small"><a href="%s" target="_blank" rel="noopener">Ver en mi sitio ↗</a>'
                         '<a href="%s/ficha" target="_blank" rel="noopener">Ficha para imprimir ↗</a>'
                         '<a href="%s/tarjeta-post.jpg" target="_blank" rel="noopener">Tarjeta Instagram ↗</a>'
                         '<a href="%s/tarjeta-historia.jpg" target="_blank" rel="noopener">Historia ↗</a></span>') % (
                (e(db.listing_url(ctx['agency'], v)),) * 4)
        else:
            site_link = ('<span class="row small"><a href="%s" target="_blank" rel="noopener">Ver en mi sitio ↗</a>'
                         '<a href="/plan">Ficha para imprimir e imágenes para Instagram: plan Pro</a></span>') % e(db.listing_url(ctx['agency'], v))
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
            '<label class="check"><input type="checkbox" name="share_in_bolsa" value="1"%s> Compartir en la Bolsa con otros asesores%s</label>'
            '<label>Tu parte si otro asesor la vende (%%)<input name="share_split_pct" value="%s" inputmode="numeric"></label>'
            '<label>Comisión total (%%), privada<input name="commission_pct" value="%s" inputmode="decimal"></label>%s'
            '<label>Nota interna (nunca se publica)<textarea name="internal_note" rows="2">%s</textarea></label></section>'
            '<button class="btn">%s</button></form>%s%s') % (
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
        ' checked' if v.get('share_in_bolsa') else '',
        '' if db.plan_has(ctx['agency'], 'tools') else ' <a class="small" href="/plan">(plan Pro)</a>',
        e(v.get('share_split_pct', 50)), num('commission_pct'),
        rp_box, e(v.get('internal_note')), 'Guardar' if lid else 'Crear y subir fotos', photos_html, ai_html if lid else '')
    return layout('Propiedad', body, ctx, 'propiedades')


# ---------- leads ----------
def _age_min(created_at):
    import datetime as _dt
    try:
        t = _dt.datetime.strptime(created_at[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None
    return int((_dt.datetime.utcnow() - t).total_seconds() // 60)


def _leads_list(con, rows, ctx=None):
    out = []
    for r in rows:
        lst = con.execute('SELECT title, ref FROM listings WHERE id=?', (r['listing_id'],)).fetchone() if r['listing_id'] else None
        keys = r.keys()
        waiting = r['status'] == 'nuevo' and ('first_response_at' not in keys or not r['first_response_at'])
        age = _age_min(r['created_at']) if waiting else None
        late = waiting and age is not None and age >= 5
        badge = ('<span class="pill error">⏰ sin respuesta · %s</span>' % ('%d min' % age if age < 120 else '%d h' % (age // 60))) if late else ''
        chips = ''
        if ctx:
            chips = '<form class="row" method="post" action="/clientes/%d/estado">%s%s</form>' % (r['id'], csrf_field(ctx), ''.join(
                '<button class="btn small %s" name="status" value="%s">%s</button>' % ('' if k == r['status'] else 'ghost', k, v)
                for k, v in LEAD_STATUSES))
        out.append('<div class="card%s" style="gap:6px"><div class="row" style="justify-content:space-between"><b>%s</b>'
                   '<span class="row">%s<span class="pill %s">%s</span></span></div><span class="small muted">%s · %s · %s</span>%s'
                   '<p class="small" style="margin:0">%s</p><div class="row">%s%s</div>%s</div>' % (
                       ' late' if late else '', e(r['name'] or 'Sin nombre'), badge, e(r['status']), e(label(LEAD_STATUSES, r['status'])),
                       e(nice_date(r['created_at'])), e(r['source']), e(lst['ref'] if lst else 'general'),
                       ('<span class="small">%s</span>' % e(lst['title'])) if lst else '', e(r['message']),
                       ('<a class="btn wa small" href="/clientes/%d/whatsapp" target="_blank" rel="noopener">Responder por WhatsApp</a>' % r['id'])
                       if r['phone'] else '',
                       ('<a class="btn ghost small" href="mailto:%s">Correo</a>' % e(r['email'])) if r['email'] else '', chips))
    return '<div class="list">%s</div>' % ''.join(out)


def late_count(con, agency_id):
    """Leads still unanswered after 5 minutes (reminded or not): the number that must be zero."""
    lead_watch.ensure_columns(con)
    return con.execute("SELECT COUNT(*) FROM leads WHERE agency_id=? AND status='nuevo' AND first_response_at IS NULL "
                       "AND created_at < datetime('now','-5 minutes')", (agency_id,)).fetchone()[0]


def leads(con, ctx, estado=None):
    a = ctx['agency']
    lead_watch.ensure_columns(con)
    q, args = "SELECT * FROM leads WHERE agency_id=?", [a['id']]
    if estado in dict(LEAD_STATUSES):
        q += ' AND status=?'
        args.append(estado)
    else:
        q += " AND status!='descartado'"
    rows = con.execute(q + ' ORDER BY id DESC LIMIT 200', args).fetchall()
    late = late_count(con, a['id'])
    tabs = '<div class="row">%s</div>' % ''.join(
        '<a class="btn small %s" href="/clientes%s">%s</a>' % ('' if (estado or '') == k else 'ghost', ('?estado=' + k) if k else '', v)
        for k, v in [('', 'Todos')] + LEAD_STATUSES)
    body = ('<h1>Clientes</h1>%s<p class="muted small">Respóndeles en menos de 5 minutos: es lo que más cierra. '
            'Al tocar "Responder por WhatsApp" se abre tu mensaje listo y lo marcamos como contactado.</p>%s%s') % (
        notice('Tienes %d cliente%s esperando respuesta hace más de 5 minutos.' % (late, '' if late == 1 else 's'), 'err') if late else '',
        tabs, _leads_list(con, rows, ctx) if rows else '<p class="muted">No hay clientes en esta vista.</p>')
    return layout('Clientes', body, ctx, 'clientes')


def stats_page(ctx, st):
    rows = ''.join('<tr><td>%s<br><span class="small muted">%s</span></td><td>%d</td><td>%d</td></tr>' % (
        e(x['title']), e(x['ref']), x['views'], x['leads']) for x in st['views_by_listing'])
    weeks = st['leads_by_week']
    mx = max([w['leads'] for w in weeks] + [1])
    bars = ''.join('<div class="bar" title="%s: %d"><span style="height:%d%%"></span><small>%s</small></div>' % (
        e(w['week']), w['leads'], int(100 * w['leads'] / mx), e(w['week'][-3:])) for w in weeks)
    med = st['median_first_response_min']
    body = ('<h1>Estadísticas</h1><p class="muted">Últimos 30 días.</p><div class="stats">'
            '<div class="stat"><b>%d</b><small>Visitas a tus propiedades</small></div>'
            '<div class="stat"><b>%d</b><small>Clientes nuevos</small></div>'
            '<div class="stat"><b>%s</b><small>Tiempo de respuesta (mediana)</small></div>'
            '<div class="stat"><b>%s</b><small>Respondidos en ≤5 min</small></div></div>'
            '%s<section class="card"><h2>Clientes por semana</h2><div class="bars">%s</div></section>'
            '<section class="card"><h2>Tus propiedades</h2><div class="tbl" tabindex="0" role="region" aria-label="Visitas y clientes por propiedad"><table><thead><tr><th scope="col">Propiedad</th><th scope="col">Visitas</th>'
            '<th scope="col">Clientes</th></tr></thead><tbody>%s</tbody></table></div></section>'
            '<section class="card"><h2>De dónde llegan</h2><p class="small">%s</p><h2>Colonias con más interés</h2><p class="small">%s</p></section>') % (
        st['views_total'], st['leads_total'], ('%g min' % med) if med is not None else '—',
        ('%g%%' % st['pct_answered_5min']) if st['pct_answered_5min'] is not None else '—',
        notice('%d cliente%s sin respuesta ahora.' % (st['unanswered_now'], '' if st['unanswered_now'] == 1 else 's'), 'warn')
        if st['unanswered_now'] else '', bars,
        rows or '<tr><td colspan="3" class="muted">Aún sin datos.</td></tr>',
        e(', '.join('%s: %d' % kv for kv in st['leads_by_source'].items()) or 'Aún sin datos.'),
        e(', '.join('%s (%d)' % kv for kv in st['top_colonias']) or 'Aún sin datos.'))
    return layout('Estadísticas', body, ctx, 'estadisticas')


# ---------- portals ----------
def portals(con, ctx, flash=''):
    a = ctx['agency']
    rows = con.execute("SELECT * FROM listings WHERE agency_id=? AND status IN ('activa','apartada') ORDER BY title", (a['id'],)).fetchall()
    base = db.site_url(a)
    open_keys = [k for k, p in registry.PORTALS.items() if p['status'] in ('open', 'api')]
    head = ''.join('<th scope="col">%s</th>' % e(registry.PORTALS[k]['name']) for k in open_keys)
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
            '<section class="card"><div class="tbl" tabindex="0" role="region" aria-label="Publicaciones por portal"><table><thead><tr><th scope="col">Propiedad</th>%s</tr></thead><tbody>%s</tbody></table></div>'
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
    pro = db.plan_has(a, 'domain')
    domain = ('<section class="card"><h2>Tu propio dominio</h2>%s</section>' % (
        ('<form class="stack" method="post" action="/sitio/dominio">%s<label>Dominio<input name="domain" value="%s" '
         'placeholder="micasa.mx"></label><button class="btn ghost">Guardar dominio</button></form>%s' % (
             csrf_field(ctx), e(a['custom_domain']),
             ('<p class="small">Para conectarlo crea en tu proveedor de dominio un registro <b>CNAME</b> de <code>www</code> '
              'hacia <code>sites.%s</code> y un registro <b>TXT</b> <code>llave-verify=%s</code>. Estado: %s.</p>' % (
                  e(db.BASE_DOMAIN), e(a['slug']),
                  'verificado' if a['domain_verified_at'] else 'pendiente (la verificación se activa en producción)'))
             if a['custom_domain'] else ''))
        if pro else '<p class="muted">Incluido en el plan <a href="/plan">Pro</a>. Mientras tanto tu sitio vive gratis en '
                    '<code>%s</code>.</p>' % e(db.site_url(a))))
    body = ('%s%s<div class="row" style="justify-content:space-between"><h1>Mi sitio</h1>'
            '<span class="row"><a class="btn ghost small" href="/perfil">Mi perfil</a><a class="btn ghost small" href="/equipo">Equipo</a>'
            '<a class="btn ghost small" href="/plan">Tu plan</a>'
            '<a class="btn ghost small" href="%s" target="_blank" rel="noopener">Ver sitio ↗</a></span></div>'
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


def landing(ref=''):
    from . import landing as _l
    return _l.landing(ref)


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
                    '<div class="tbl" tabindex="0" role="region" aria-label="Vista previa de la importación"><table><thead><tr><th scope="col">Fila</th><th scope="col">Título</th><th scope="col">Precio</th><th scope="col"></th></tr></thead><tbody>%s</tbody></table></div>'
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
    ('Tu primera propiedad en 10 minutos', 'Del celular a tu sitio y a Google.'),
    ('Fotos que venden con tu celular', 'Luz, ángulos y orden: lo que más cambia una ficha.'),
    ('Aparecer en Google y en ChatGPT', 'Qué lee un buscador en tu ficha y cómo ayudarle.'),
    ('Responder en 5 minutos por WhatsApp', 'El primer mensaje y cómo agendar la visita.'),
    ('Compartir en la Bolsa sin perder comisión', 'Cómo funciona la división y qué acordar por escrito.'),
    ('Rentas seguras', 'Contrato, póliza jurídica y entrega del inmueble.'),
]


def services(ctx, con=None, ok='', error=''):
    from .. import eco
    a = ctx['agency']
    bal = eco.balance(con, a['id']) if con else 0
    cards = ''.join('<div class="card"><span class="small muted">%s</span><h2>%s</h2><p style="margin:0">%s</p>%s</div>' % (
        e(brand), e(t), e(d), ('<a class="btn small ghost" href="%s" target="_blank" rel="noopener">%s</a>' % (e(url), e(cta)))
        if url else '<span class="pill pendiente">%s</span>' % e(cta)) for t, brand, d, url, cta in SERVICES)
    earn = ''.join('<li>%s: <b>+%d</b></li>' % (e(r['label']), r['credits']) for r in eco.RULES.values())
    mine = con.execute("SELECT id, title FROM listings WHERE agency_id=? AND status IN ('activa','apartada') ORDER BY title", (a['id'],)).fetchall() if con else []
    opts = ''.join('<option value="%d">%s</option>' % (r['id'], e(r['title'])) for r in mine)
    redeem = ''.join('<form class="row card" method="post" action="/servicios/canjear/%s" style="gap:8px">%s<div style="flex:1;min-width:200px"><b>%s</b>'
                     '<br><span class="small muted">%d créditos</span></div>%s<button class="btn small"%s>Canjear</button></form>' % (
                         k, csrf_field(ctx), e(v['label']), v['cost'],
                         ('<label class="vh" for="r-%s">Propiedad</label><select id="r-%s" name="listing" style="max-width:240px">%s</select>' % (k, k, opts))
                         if v['kind'] == 'destacada' else '', '' if bal >= v['cost'] else ' disabled') for k, v in eco.CATALOG.items())
    body = ('%s%s<h1>Servicios y Ecosistema</h1><p class="muted">Empresas de la misma familia que Ficha Única. Úsalas y gana créditos.</p>'
            '<div class="stats"><div class="stat"><b>%d</b><small>Tus créditos</small></div></div>'
            '<div class="grid2 wide">%s</div>'
            '<section class="card"><h2>Cómo ganas créditos</h2><ul class="small">%s</ul>'
            '<p class="small muted">Los créditos se suman cuando la otra empresa confirma (no basta con avisarnos).</p></section>'
            '<section class="card"><h2>Canjea tus créditos</h2>%s<p class="small muted"><b>Sobre los leads gratis:</b> %s</p></section>') % (
        notice(ok), notice(error, 'err'), bal, cards, earn, redeem, e(eco.FREE_LEADS_DEFINITION))
    return layout('Servicios', body, ctx, 'servicios')


def academy(ctx):
    items = ''.join('<div class="card" style="gap:4px"><b>%d. %s</b><span class="small muted">%s</span><span class="pill pendiente">%s</span></div>'
                    % (i + 1, e(t), e(d), 'Video en preparación' if i == 0 else 'Próximamente') for i, (t, d) in enumerate(LESSONS))
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
    body = ('<div class="auth pub" style="max-width:720px"><h1>%s</h1><p>%s</p><p class="notice warn"><b>BORRADOR</b>: texto de trabajo; '
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
            '<span aria-live="polite">📷 Elegir fotos</span><small class="muted">Del celular o la computadora · mínimo 600 px</small></label>'
            '<fieldset><legend class="vh">Operación</legend><div class="seg"><label><input type="radio" name="operation" value="venta" checked><span>Venta</span></label>'
            '<label><input type="radio" name="operation" value="renta"><span>Renta</span></label></div></fieldset>'
            '<fieldset><legend class="vh">Tipo de propiedad</legend><div class="chips">%s</div></fieldset><button class="btn">Siguiente</button></form>'
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
            '%s'
            '<a class="btn ghost" href="/nueva">Subir otra</a></div>') % (e(url), e(share),
        ('<a class="btn ghost" href="%s/tarjeta-post.jpg" target="_blank" rel="noopener">Tarjeta para Instagram</a>' % e(url))
        if db.plan_has(ctx['agency'], 'tools') else '')
    return layout('¡Publicada!', body, ctx, 'propiedades')


DRAFT_TITLE = 'Propiedad nueva (borrador)'


LEAFLET = ('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">'
           '<script defer src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>')


def map_block(pins, height=280):
    """Leaflet + OpenStreetMap tiles. Pins are already snapped to a ~250 m grid unless the agent chose exact."""
    if not pins:
        return ''
    return ('%s<div id="map" class="map" style="height:%dpx" role="region" aria-label="Mapa de ubicación aproximada"></div>'
            '<noscript><p class="muted small">El mapa necesita JavaScript. Las ubicaciones son aproximadas.</p></noscript>'
            '<script>document.addEventListener("DOMContentLoaded",function(){var P=%s;if(!window.L)return;var m=L.map("map",{scrollWheelZoom:false});'
            'L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:18,attribution:"© OpenStreetMap"}).addTo(m);'
            'var g=[];P.forEach(function(p){var c=L.circleMarker([p.lat,p.lng],{radius:9,weight:2,color:"#F2501F",fillOpacity:.6}).addTo(m);'
            'var d=document.createElement("div");var b=document.createElement("b");b.textContent=p.t;d.appendChild(b);'
            'd.appendChild(document.createElement("br"));d.appendChild(document.createTextNode(p.p+" · "+p.a));c.bindPopup(d);g.push([p.lat,p.lng]);});'
            'm.fitBounds(g,{padding:[30,30],maxZoom:15});});</script>') % (LEAFLET, height, json.dumps(pins, ensure_ascii=False).replace('</', '<\\/'))


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


# ---------- my public profile ----------
def profile(ctx, ok='', error=''):
    u, a = ctx['user'], ctx['agency']
    url = ('%s/asesor/%s' % (db.site_url(a), u['slug'])) if u['slug'] else ''
    body = ('%s%s<div class="row" style="justify-content:space-between"><h1>Mi perfil</h1>%s</div>'
            '<p class="muted">Tu página como asesor, dentro de tu sitio. Sale en tus propiedades y en Google.</p>'
            '<form class="stack card" method="post" action="/perfil" enctype="multipart/form-data">%s'
            '%s<label for="pf-name">Nombre<input id="pf-name" name="name" value="%s" required autocomplete="name"></label>'
            '<label for="pf-wa">WhatsApp<input id="pf-wa" name="whatsapp" value="%s" inputmode="tel" autocomplete="tel"></label>'
            '<label for="pf-zones">Zonas donde trabajas<input id="pf-zones" name="zones" value="%s" placeholder="Polanco, Lomas, Condesa"></label>'
            '<label for="pf-bio">Sobre ti (2 o 3 frases)<textarea id="pf-bio" name="bio" maxlength="600">%s</textarea></label>'
            '<label for="pf-photo">Tu foto (cuadrada de preferencia)<input id="pf-photo" type="file" name="photo" accept="image/*"></label>'
            '<label class="check"><input type="checkbox" name="public" value="1"%s> Mostrar mi perfil en el sitio</label>'
            '<button class="btn">Guardar perfil</button></form>') % (
        notice(ok), notice(error, 'err'),
        ('<a class="btn ghost small" href="%s" target="_blank" rel="noopener">Ver mi perfil ↗</a>' % e(url)) if url else '',
        csrf_field(ctx),
        ('<img src="/media/%s" alt="Tu foto actual" width="96" height="96" style="border-radius:50%%;object-fit:cover">' % e(u['photo_path']))
        if u['photo_path'] else '',
        e(u['name']), e(u['whatsapp']), e(u['zones']), e(u['bio']), ' checked' if u['slug'] else '')
    return layout('Mi perfil', body, ctx, 'sitio')


# ---------- plans (TEST MODE until llave/billing.py is configured; then Stripe takes the payment) ----------
PLANS = [
    ('gratis', 'Gratis', 0, ['Tu sitio en una dirección gratis', '1 propiedad', 'Portales y buscadores gratuitos', 'Clientes directo a tu WhatsApp']),
    ('pro', 'Pro', 499, ['Todo lo de Gratis', '5 propiedades', 'Tu propio dominio', 'Imágenes para Instagram y ficha para imprimir',
                         'Importa tus propiedades desde Excel', 'Bolsa 50/50 con otros asesores', 'Estadísticas completas']),
    ('ia', 'Pro + IA', 999, ['Todo lo de Pro', '25 propiedades', 'Títulos y descripciones con IA, en español e inglés', 'Revisión y orden de tus fotos',
                             'Precio sugerido con propiedades parecidas', 'Qué publicar cada semana en tus redes']),
]
COMING_SOON = set()  # Josh 10-19: Pro + IA is on sale from launch day


STRIPE_NOTE = ('Pago seguro con tarjeta, procesado por Stripe para %s. Precios en pesos mexicanos (MXN), IVA incluido. '
               'Cancelas cuando quieras.')


def plans(con, ctx, ok='', error=''):
    a = ctx['agency']
    paid = billing.enabled()
    n = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status NOT IN ('vendida','rentada')", (a['id'],)).fetchone()[0]
    cards = ''.join(
        '<div class="card plan%s"><h2>%s</h2><p class="price"><b>%s</b>%s</p><ul class="small">%s</ul>%s</div>' % (
            ' current' if k == a['plan'] else '', e(name), 'Gratis' if not price else '$%d MXN' % price,
            '' if not price else ' <span class="muted small">al mes, IVA incluido</span>',
            ''.join('<li>%s</li>' % e(f) for f in feats),
            '<span class="pill ok">Tu plan</span>' if k == a['plan'] else
            '<span class="pill pendiente">Próximamente</span>' if k in COMING_SOON else
            '<a class="btn %s" href="/plan/%s">%s</a>' % ('' if price else 'ghost', k, 'Cambiar a %s' % name))
        for k, name, price, feats in PLANS)
    manage = ''
    if paid and billing.is_paying(a):
        manage = ('<form class="card" method="post" action="/plan/portal">%s<p class="small muted">Cambia de plan, actualiza tu tarjeta '
                  'o cancela desde tu pago.</p><button class="btn ghost">Administrar mi pago</button></form>') % csrf_field(ctx)
    foot = (STRIPE_NOTE % e(db.OWNER)) if paid else 'Precios en pesos mexicanos con IVA. Sin plazo forzoso: cambias o cancelas cuando quieras.'
    body = ('%s%s<h1>Tu plan</h1><p class="muted">Usas %d de %d propiedades.</p><div class="grid2 wide plans">%s</div>%s'
            '<p class="small muted">%s</p>') % (notice(ok), notice(error, 'err'), n, db.listing_limit(con, a), cards, manage, foot)
    return layout('Tu plan', body, ctx, 'sitio')


UPSELL = {
    'tools': ('Pro', 'Esta herramienta viene en el plan Pro: imágenes para Instagram, ficha para imprimir, importar desde Excel, '
                     'Bolsa 50/50 y estadísticas completas, con 5 propiedades y tu propio dominio.'),
    'ai': ('Pro + IA', 'Esta herramienta viene en el plan Pro + IA: textos con IA en español e inglés, revisión y orden de fotos, '
                       'precio sugerido y qué publicar cada semana, con 25 propiedades.'),
}


def upsell(ctx, feature, title, tab='inicio'):
    plan, text = UPSELL[feature]
    body = ('<div class="auth"><h1>%s</h1><p class="muted">%s</p><a class="btn" href="/plan">Ver el plan %s</a>'
            '<a class="btn ghost" href="/">Volver al inicio</a></div>') % (e(title), e(text), e(plan))
    return layout(title, body, ctx, tab)


def payments_soon(ctx, key):
    name = next((x[1] for x in PLANS if x[0] == key), key)
    body = ('<div class="auth"><h1>%s llega muy pronto</h1><p class="muted">Estamos activando los pagos con tarjeta. '
            'Mientras tanto sigues en tu plan actual, con todo lo que ya tienes.</p><a class="btn ghost" href="/plan">Volver a planes</a></div>') % e(name)
    return layout('Pagos muy pronto', body, ctx, 'sitio')


def plan_checkout(ctx, key, error=''):
    p = next((x for x in PLANS if x[0] == key), None)
    if billing.enabled():
        return _plan_checkout_paid(ctx, key, p, error)
    body = ('<div class="auth"><div class="notice warn"><b>MODO PRUEBA</b>: no se cobra nada. En producción aquí va el pago con tarjeta '
            '(procesado por Stripe para %s).</div><h1>Cambiar a %s</h1><p class="price"><b>%s</b>%s</p>%s'
            '<form method="post" action="/plan/%s">%s<button class="btn">Confirmar cambio (prueba)</button></form>'
            '<a class="btn ghost" href="/plan">Volver</a></div>') % (
        e(db.OWNER), e(p[1]), 'Gratis' if not p[2] else '$%d MXN' % p[2], '' if not p[2] else ' <span class="muted small">al mes</span>',
        notice(error, 'err'), e(key), csrf_field(ctx))
    return layout('Cambiar de plan', body, ctx, 'sitio')


def _plan_checkout_paid(ctx, key, p, error):
    """Real payment screens (Stripe configured): no test notice. Payment itself happens on Stripe's page."""
    a = ctx['agency']
    price = '<p class="price"><b>%s</b>%s</p>' % ('Gratis' if not p[2] else '$%d MXN' % p[2],
                                                  '' if not p[2] else ' <span class="muted small">al mes, IVA incluido</span>')
    portal = ('<form method="post" action="/plan/portal">%s<button class="btn">Administrar mi pago</button></form>' % csrf_field(ctx))
    if key == db.plan_of(a):
        action = '<p class="muted">Este ya es tu plan.</p>' + (portal if billing.is_paying(a) else '')
    elif billing.is_paying(a):
        action = ('<p class="muted">Ya tienes un plan de pago. Para cambiar de plan, actualizar tu tarjeta o cancelar, entra a tu pago: '
                  'ahí lo haces tú mismo en un minuto.</p>%s') % portal
    elif key == 'gratis':
        action = '<form method="post" action="/plan/gratis">%s<button class="btn">Pasar a Gratis</button></form>' % csrf_field(ctx)
    else:
        action = ('<p class="small muted">%s</p><form method="post" action="/plan/%s">%s<button class="btn">Pagar con tarjeta</button></form>'
                  % (e(STRIPE_NOTE % db.OWNER), e(key), csrf_field(ctx)))
    body = '<div class="auth"><h1>Cambiar a %s</h1>%s%s%s<a class="btn ghost" href="/plan">Volver</a></div>' % (
        e(p[1]), price, notice(error, 'err'), action)
    return layout('Cambiar de plan', body, ctx, 'sitio')


# ---------- invite a colleague (referral loop) ----------
def invite(con, ctx):
    a = ctx['agency']
    link = '%s/registro?ref=%s' % (db.origin('app'), a['slug'])
    msg = ('Oye, estoy usando Ficha Única: sitio web inmobiliario gratis, tus propiedades en Mercado Libre y en Google, '
           'y tus clientes directo a tu WhatsApp. Crea el tuyo aquí: ' + link)
    rows = con.execute("SELECT a.name, a.created_at, (SELECT COUNT(*) FROM listings l WHERE l.agency_id=a.id AND l.status IN ('activa','apartada')) AS pub "
                       "FROM agencies a WHERE a.referred_by=? ORDER BY a.id DESC", (a['id'],)).fetchall()
    q = db.qualified_referrals(con, a['id'])
    lst = ''.join('<div class="item" style="grid-template-columns:1fr auto"><div><b>%s</b><br><span class="small muted">desde %s</span></div>'
                  '<span class="pill %s">%s</span></div>' % (e(r['name']), e(nice_date(r['created_at'])), 'ok' if r['pub'] else 'pendiente',
                                                            'publicó ✓' if r['pub'] else 'aún sin publicar') for r in rows)
    body = ('<h1>Invita a un colega</h1><p class="muted">Por cada colega que cree su sitio con tu enlace y publique su primera propiedad, '
            'te damos <b>%s más</b> en tu plan, para siempre.</p>'
            '<section class="card"><label for="ref-link">Tu enlace<input id="ref-link" value="%s" readonly onclick="this.select()"></label>'
            '<div class="row"><a class="btn wa" href="%s" target="_blank" rel="noopener">Compartir por WhatsApp</a>'
            '<button class="btn ghost" type="button" onclick="navigator.clipboard&&navigator.clipboard.writeText(document.getElementById(\'ref-link\').value);this.textContent=\'Copiado ✓\'">Copiar enlace</button></div></section>'
            '<div class="stats"><div class="stat"><b>%d</b><small>Colegas invitados</small></div><div class="stat"><b>%d</b><small>Ya publicaron</small></div>'
            '<div class="stat"><b>+%d</b><small>Propiedades extra ganadas</small></div></div><div class="list">%s</div>') % (
        props(db.REFERRAL_BONUS_LISTINGS), e(link), e(whatsapp.wa_link('', msg)), len(rows), q, q * db.REFERRAL_BONUS_LISTINGS,
        lst or '<p class="muted">Aún no invitas a nadie. Comparte tu enlace en tus grupos de asesores.</p>')
    return layout('Invita a un colega', body, ctx, 'invitar')


# ---------- admin (Josh / Samantha): every agency, leads at risk ----------
def _mask_phone(p):
    d = ''.join(ch for ch in (p or '') if ch.isdigit())
    return ('•••• ' + d[-4:]) if d else '—'


def admin(con, ctx):
    lead_watch.ensure_columns(con)
    tot = lambda q, *a: con.execute(q, a).fetchone()[0]
    risk = con.execute(
        "SELECT l.*, a.name AS agency_name, a.slug, a.whatsapp AS agency_wa, li.ref, li.title FROM leads l "
        "JOIN agencies a ON a.id=l.agency_id LEFT JOIN listings li ON li.id=l.listing_id "
        "WHERE l.status='nuevo' AND l.first_response_at IS NULL AND l.created_at < datetime('now','-5 minutes') "
        "ORDER BY l.created_at LIMIT 100").fetchall()
    agencies = con.execute(
        "SELECT a.*, (SELECT COUNT(*) FROM listings x WHERE x.agency_id=a.id AND x.status IN ('activa','apartada')) AS pub, "
        "(SELECT COUNT(*) FROM leads x WHERE x.agency_id=a.id AND x.created_at >= datetime('now','-30 days')) AS leads30, "
        "(SELECT COUNT(*) FROM leads x WHERE x.agency_id=a.id AND x.status='nuevo' AND x.first_response_at IS NULL "
        "  AND x.created_at < datetime('now','-5 minutes')) AS late, "
        "(SELECT MAX(at) FROM audit x WHERE x.actor IN (SELECT 'user:'||u.id FROM users u WHERE u.agency_id=a.id)) AS last_seen, "
        "(SELECT name FROM agencies r WHERE r.id=a.referred_by) AS ref_by "
        "FROM agencies a ORDER BY late DESC, a.id DESC LIMIT 500").fetchall()
    ob = con.execute("SELECT kind, status, COUNT(*) AS n FROM outbox GROUP BY kind, status ORDER BY n DESC").fetchall()
    risk_rows = ''.join(
        '<tr><td><b>%s</b><br><span class="small muted">%s · %s</span></td><td>%s<br><span class="small muted">%s</span></td>'
        '<td><span class="pill error">%s min</span></td><td>%s</td></tr>' % (
            e(r['agency_name']), e(r['slug']), e(_mask_phone(r['agency_wa'])), e((r['name'] or 'Sin nombre').split(' ')[0]),
            e(r['ref'] or 'general'), _age_min(r['created_at']) or 0, e(r['source'])) for r in risk)
    ag_rows = ''.join(
        '<tr><td><b>%s</b><br><a class="small" href="%s" target="_blank" rel="noopener">%s</a></td><td>%s</td><td>%d</td><td>%d</td>'
        '<td>%s</td><td>%s</td><td class="small">%s</td></tr>' % (
            e(a['name']), e(db.site_url(a)), e(a['slug']), e(a['plan']), a['pub'], a['leads30'],
            ('<span class="pill error">%d</span>' % a['late']) if a['late'] else '0', e(a['ref_by'] or '—'),
            e(nice_date(a['last_seen'])) if a['last_seen'] else '—') for a in agencies)
    body = ('<h1>Admin · Ficha Única</h1><p class="muted small">Solo lectura. Visible para cuentas con rol admin.</p>'
            '<div class="stats"><div class="stat"><b>%d</b><small>Agencias</small></div><div class="stat"><b>%d</b><small>Propiedades públicas</small></div>'
            '<div class="stat"><b>%d</b><small>Clientes (30 días)</small></div><div class="stat"><b>%d</b><small>Clientes en riesgo (&gt;5 min)</small></div></div>'
            '<section class="card"><h2>Clientes en riesgo</h2>%s</section>'
            '<section class="card"><h2>Agencias</h2><div class="tbl" tabindex="0" role="region" aria-label="Agencias"><table><thead><tr>'
            '<th scope="col">Agencia</th><th scope="col">Plan</th><th scope="col">Públicas</th><th scope="col">Clientes 30 d</th>'
            '<th scope="col">En riesgo</th><th scope="col">Invitada por</th><th scope="col">Última actividad</th></tr></thead><tbody>%s</tbody></table></div></section>'
            '<section class="card"><h2>Ecosistema (30 días)</h2>%s</section>'
            '<section class="card"><h2>Salida (modo prueba)</h2><p class="small">%s</p></section>') % (
        tot('SELECT COUNT(*) FROM agencies'), tot("SELECT COUNT(*) FROM listings WHERE status IN ('activa','apartada')"),
        tot("SELECT COUNT(*) FROM leads WHERE created_at >= datetime('now','-30 days')"), len(risk),
        ('<div class="tbl" tabindex="0" role="region" aria-label="Clientes en riesgo"><table><thead><tr><th scope="col">Agencia</th>'
         '<th scope="col">Cliente</th><th scope="col">Esperando</th><th scope="col">Origen</th></tr></thead><tbody>%s</tbody></table></div>' % risk_rows)
        if risk else notice('✓ Ningún cliente esperando más de 5 minutos.'),
        ag_rows, _eco_admin(con), e(' · '.join('%s/%s: %d' % (o['kind'], o['status'], o['n']) for o in ob) or 'Sin operaciones.'))
    return layout('Admin', body, ctx, 'admin')


def _eco_admin(con):
    from .. import eco
    eco.ensure_tables(con)
    rep = eco.owner_report(con)
    if not rep['by_brand']:
        return '<p class="muted small">Aún sin referidos entre empresas.</p>'
    brands = ''.join('<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td></tr>' % (e(b), v['events'], v['confirmed'], v['credits'])
                     for b, v in sorted(rep['by_brand'].items()))
    pairs = ' · '.join('%s: %d' % kv for kv in sorted(rep['by_pair'].items()))
    return ('<div class="tbl" tabindex="0" role="region" aria-label="Ecosistema"><table><thead><tr><th scope="col">Empresa</th>'
            '<th scope="col">Eventos</th><th scope="col">Confirmados</th><th scope="col">Créditos</th></tr></thead><tbody>%s</tbody></table></div>'
            '<p class="small">Referidos entre empresas: %s</p>') % (brands, e(pairs))


# ---------- team (Agencia plan) ----------
def team(con, ctx, link='', error=''):
    a = ctx['agency']
    users = con.execute('SELECT name, email, role, created_at FROM users WHERE agency_id=? ORDER BY id', (a['id'],)).fetchall()
    can = db.plan_has(a, 'team')
    rows = ''.join('<div class="item" style="grid-template-columns:1fr auto"><div><b>%s</b><br><span class="small muted">%s</span></div>'
                   '<span class="pill %s">%s</span></div>' % (e(u['name']), e(u['email']), 'ok' if u['role'] in ('owner', 'admin') else '',
                                                             'dueño' if u['role'] in ('owner', 'admin') else 'asesor') for u in users)
    body = ('<h1>Equipo</h1>%s<p class="muted">Tus asesores comparten las propiedades, los clientes y el sitio de la inmobiliaria.</p>%s'
            '<div class="list">%s</div>') % (
        notice(error, 'err'),
        ('<form method="post" action="/equipo">%s<button class="btn">Crear enlace de invitación</button></form>%s' % (
            csrf_field(ctx), ('<section class="card"><label for="team-link">Enlace (vale 7 días, un solo uso)<input id="team-link" value="%s" readonly onclick="this.select()"></label>'
                              '<a class="btn wa" href="%s" target="_blank" rel="noopener">Enviar por WhatsApp</a></section>' % (
                                  e(link), e(whatsapp.wa_link('', 'Te invito a %s en Ficha Única: %s' % (a['name'], link))))) if link else ''))
        if can and ctx['user']['role'] in ('owner', 'admin') else
        ('<p class="notice">Los equipos de asesores llegan pronto.</p>' if not can else ''),
        rows)
    return layout('Equipo', body, ctx, 'sitio')


def join(agency, token, error='', values=None):
    v = values or {}
    body = ('<div class="auth pub"><h1>Únete a %s</h1><p class="muted">Crea tu acceso de asesor en Ficha Única.</p>%s'
            '<form class="stack card" method="post" action="/unirse/%s">'
            '<label for="j-name">Tu nombre<input id="j-name" name="name" value="%s" required autocomplete="name"></label>'
            '<label for="j-wa">Tu WhatsApp<input id="j-wa" name="whatsapp" value="%s" inputmode="tel" required autocomplete="tel"></label>'
            '<label for="j-email">Correo<input id="j-email" name="email" type="email" value="%s" required autocomplete="email"></label>'
            '<label for="j-pw">Contraseña<input id="j-pw" name="password" type="password" minlength="8" required autocomplete="new-password"></label>'
            '<button class="btn">Unirme</button></form></div>') % (
        e(agency['name']), notice(error, 'err'), e(token), e(v.get('name')), e(v.get('whatsapp')), e(v.get('email')))
    return layout('Únete', body)


# ---------- AI helpers in the listing editor ----------
def _ai_box(con, ctx, lid, suggestion=None):
    if not db.plan_has(ctx['agency'], 'ai'):
        return ('<section class="card"><h2>Ayuda inteligente</h2><p class="small muted">Con <b>Pro + IA</b> escribimos el título y la descripción '
                'en español e inglés, revisamos y ordenamos tus fotos y te sugerimos un precio con propiedades parecidas.</p>'
                '<a class="btn ghost small" href="/plan">Ver Pro + IA</a></section>')
    from ..ai import client, comps, photo_qa
    qa = photo_qa.analyze(con, lid)
    cp = comps.suggest_price(con, lid)
    live = client.enabled()
    tips = ''.join('<li>%s</li>' % e(t) for t in qa.get('tips', []))
    price = ('<p><b>%s – %s</b> <span class="muted small">(%d comparables)</span></p><p class="small muted">%s</p>' % (
        e(money(cp['range_low'], cp['currency'])), e(money(cp['range_high'], cp['currency'])), cp['n'], e(cp['note']))
        if cp.get('ok') else '<p class="small muted">%s</p>' % e(cp.get('note')))
    en = ''
    if suggestion and suggestion.get('en'):
        en = '<details><summary class="small">Versión en inglés</summary><p class="small"><b>%s</b><br>%s</p></details>' % (
            e(suggestion['en']['title']), e(suggestion['en']['description']))
    return ('<section class="card"><h2>Ayuda inteligente</h2>'
            '<form method="post" action="/propiedades/%d/ia-texto">%s<button class="btn ghost small">Escribir título y descripción%s</button></form>'
            '%s<h3 class="small" style="margin:0">Fotos</h3><ul class="small">%s</ul>%s'
            '<h3 class="small" style="margin:0">Precio sugerido</h3>%s</section>') % (
        lid, csrf_field(ctx), ' con IA' if live else '', en, tips or '<li>Tus fotos se ven bien.</li>',
        ('<form method="post" action="/propiedades/%d/ordenar-fotos">%s<button class="btn ghost small">Usar el orden sugerido (portada primero, planos al final)</button></form>'
         % (lid, csrf_field(ctx))) if qa.get('suggested_order') else '', price)


def social_kit_page(ctx, kit):
    items = ''.join('<div class="card" style="gap:8px"><span class="pill">%s</span><b>%s</b>%s<p class="small" style="margin:0;white-space:pre-line">%s</p>'
                    '<p class="small muted" style="margin:0">%s</p><button class="btn ghost small" type="button" onclick="navigator.clipboard&&navigator.clipboard.writeText(this.dataset.t);this.textContent=\'Copiado ✓\'" data-t="%s">Copiar texto</button></div>' % (
                        {'listing': 'Propiedad', 'market': 'Mercado', 'tip': 'Consejo'}.get(it['kind'], it['kind']), e(it['title']),
                        ('<a href="%s" target="_blank" rel="noopener"><img src="%s" alt="" style="width:100%%;max-width:320px;border-radius:8px"></a>' % (e(it['image_url']), e(it['image_url'])))
                        if it.get('image_url') else '', e(it['caption']), e(' '.join(it.get('hashtags') or [])),
                        e(it['caption'] + ('\n\n' + ' '.join(it.get('hashtags') or []) if it.get('hashtags') else ''))) for it in kit['items'])
    body = ('<h1>Qué publicar esta semana</h1><p class="muted">Semana %s. Borradores listos: copia el texto y descarga la imagen. '
            'Nada se publica solo.</p><div class="grid2 wide">%s</div>') % (e(kit['week']), items or '<p class="muted">Publica una propiedad para recibir tu kit.</p>')
    return layout('Qué publicar', body, ctx, 'publicar')
