"""Home on the shared agent dashboard kit (functions/agent-dashboard, AgentDashKit 1.1.0). Off unless LLAVE_KIT_HOME=1.
Every number comes from the database; nothing is invented (no events, no app card, no rewards that don't exist)."""
import json
import os

KIT_VERSION = '1.1.0'  # cache-buster for /_s/agent-dash.* (static files are cached a year)

from . import db, lead_watch, novedades, price_check, replies


def enabled():
    return os.environ.get('LLAVE_KIT_HOME') == '1'


# Five tabs, same order as IDX Bloom: Home, Leads, My site, Grow, Account. Old nav keys -> tab.
KIT_TABS = [('inicio', 'Inicio', '/'), ('clientes', 'Clientes', '/clientes'), ('sitio', 'Mi sitio', '/sitio'),
            ('crecer', 'Crecer', '/servicios'), ('cuenta', 'Cuenta', '/plan')]
TAB_OF = {'inicio': 'inicio', 'clientes': 'clientes', 'propiedades': 'sitio', 'portales': 'sitio', 'bolsa': 'sitio', 'sitio': 'sitio',
          'formatos': 'sitio', 'operaciones': 'sitio', 'calculadoras': 'sitio', 'estadisticas': 'crecer', 'publicar': 'crecer',
          'invitar': 'crecer', 'servicios': 'crecer', 'academia': 'crecer', 'cuenta': 'cuenta'}


def tools():
    return [('plus', 'Subir propiedad', 'Del celular a tu sitio', '/nueva'), ('home', 'Mis propiedades', 'Fotos, precio y estado', '/propiedades'),
            ('users', 'Mis clientes', 'Mensajes y seguimiento', '/clientes'), ('globe', 'Mi sitio', 'Diseño, color y logo', '/sitio'),
            ('share', 'Bolsa', 'Comparte con colegas', '/bolsa'), ('list', 'Qué publicar', 'Ideas de la semana', '/que-publicar'),
            ('calc', 'Calculadoras', 'Para tus clientes', '/calculadoras'), ('file', 'Formatos', 'Documentos para imprimir', '/formatos'),
            ('tag', 'Operaciones', 'Tus negocios en curso', '/operaciones'), ('bolt', 'Academia', '6 clases cortas', '/academia')]


def build(con, ctx, steps, services, welcome=False):
    """steps = [(done, text, href)] as the old Home computes them; services = panel.SERVICES."""
    a = ctx['agency']
    uid = a['id']
    n_list = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status IN ('activa','apartada')", (uid,)).fetchone()[0]
    n_new = con.execute("SELECT COUNT(*) FROM leads WHERE agency_id=? AND status='nuevo'", (uid,)).fetchone()[0]
    lead_watch.ensure_columns(con)
    n_late = con.execute("SELECT COUNT(*) FROM leads WHERE agency_id=? AND status='nuevo' AND first_response_at IS NULL "
                         "AND created_at < datetime('now','-5 minutes')", (uid,)).fetchone()[0]
    n_fu = lead_watch.follow_up_count(con, uid)
    n_stale = len(price_check.stale_listings(con, uid))
    views = con.execute("SELECT COALESCE(SUM(v.views),0) FROM listing_views v JOIN listings l ON l.id=v.listing_id WHERE l.agency_id=? "
                        "AND v.day >= date('now','-7 days')", (uid,)).fetchone()[0]
    first = ctx['user']['name'].split(' ')[0]
    name = a['name'] if (not first or first.lower() in replies.GENERIC_ACCOUNT) else first
    stats = [{'label': 'Clientes nuevos', 'value': str(n_new), 'sub': ('%d sin respuesta hace más de 5 min' % n_late) if n_late else 'Al día',
              'cta': {'label': 'Responder', 'href': '/clientes?estado=nuevo'} if n_new else None},
             {'label': 'Propiedades publicadas', 'value': str(n_list), 'sub': 'En tu sitio'}]
    if views:
        stats.insert(1, {'label': 'Visitas esta semana', 'value': '{:,}'.format(views), 'sub': 'A tus propiedades'})
    data = {'user': {'name': name, 'href': '/perfil'}, 'notifications': {'count': n_late + n_fu} if (n_late or n_fu) else {},
            'tabs': [{'label': l, 'href': h, 'current': k == 'inicio'} for k, l, h in KIT_TABS],
            'primary': {'label': 'Subir propiedad', 'href': '/nueva'}, 'search': False, 'arrange': False, 'help': {'href': '/academia'},
            'stats': [dict((k, v) for k, v in s.items() if v) for s in stats],
            'tools': [{'icon': i, 'label': l, 'hint': h, 'href': u} for i, l, h, u in tools()],
            'services': [{'name': b, 'mono': ''.join(w[0] for w in b.split()[:2]).upper(), 'text': d,
                          'cta': {'label': c, 'href': u} if u else None} for t, b, d, u, c in services],
            'news': [{'title': t, 'date': d, 'href': h or '/novedades'} for d, t, _b, h in novedades.latest(3)],
            'referral': {'title': 'Invita a un colega', 'body': 'Por cada colega que publique con tu enlace, tú ganas propiedades extra.',
                         'code': a['slug'], 'shareText': 'Arma tu sitio inmobiliario gratis con Ficha Única: %s/registro?ref=%s' % (db.origin('app'), a['slug'])}}
    for sv in data['services']:
        if sv['cta'] is None:
            sv.pop('cta')
    # Urgent things go in the kit's 'alerts' (1.1.0), all at once instead of only the first one.
    alerts = []
    if n_late:
        alerts.append({'tone': 'warn', 'icon': 'chat', 'title': '%d cliente%s sin respuesta hace más de 5 min' % (n_late, '' if n_late == 1 else 's'),
                       'body': 'Responder rápido es lo que más ayuda a avanzar.', 'cta': {'label': 'Responder', 'href': '/clientes?estado=nuevo'}})
    if n_fu:
        alerts.append({'icon': 'cal', 'title': 'Hoy toca dar seguimiento a %d cliente%s' % (n_fu, '' if n_fu == 1 else 's'),
                       'cta': {'label': 'Verlos', 'href': '/clientes?estado=hoy'}})
    if n_stale:
        alerts.append({'icon': 'tag', 'title': '%d precio%s sin confirmar en 30 días' % (n_stale, '' if n_stale == 1 else 's'),
                       'cta': {'label': 'Confirmar', 'href': '/precios'}})
    if alerts:
        data['alerts'] = alerts
    # First week = the kit's 'checklist' while steps are open; the next-step card points at the first open one.
    pend = [(t, h) for ok, t, h in steps if not ok]
    nxt = None
    if pend:
        data['checklist'] = {'title': 'Tu primera semana',
                             'items': [{'label': t, 'done': True} if ok else {'label': t, 'href': h} for ok, t, h in steps]}
        if not steps[0][0]:  # no property yet: lesson 1 first (same link the old first-week card had)
            nxt = {'title': 'Tu primera propiedad en 10 minutos', 'body': 'Clase 1 de Academia: del celular a tu sitio.',
                   'icon': 'bolt', 'cta': {'label': 'Ver la clase', 'href': '/academia/primera-propiedad'}}
        else:
            nxt = {'title': pend[0][0], 'body': '%d de %d pasos listos.' % (len(steps) - len(pend), len(steps)),
                   'cta': {'label': 'Ir', 'href': pend[0][1]}}
    if nxt:
        data['next'] = nxt
    return data


def js(obj):
    return json.dumps(obj, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
