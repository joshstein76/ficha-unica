"""Mercado Libre (site MLM) item payloads. DRY ONLY: nothing here touches the network."""
import json
import sys

from .. import db
from ..whatsapp import norm_phone

# (property_type, operation) -> leaf id, read from api.mercadolibre.com/categories on 2026-10-29.
# Venta of casa/depto/terreno/oficina has two leaves; one agent's listing is "Propiedades Individuales".
CATEGORIES = {
    ('casa', 'venta'): 'MLM170527', ('casa', 'renta'): 'MLM1467',
    ('departamento', 'venta'): 'MLM170375', ('departamento', 'renta'): 'MLM1479',
    ('terreno', 'venta'): 'MLM170363', ('terreno', 'renta'): 'MLM50741',
    ('oficina', 'venta'): 'MLM170361', ('oficina', 'renta'): 'MLM1488',
    ('local', 'venta'): 'MLM1474', ('local', 'renta'): 'MLM1473',
    ('bodega', 'venta'): 'MLM50745', ('bodega', 'renta'): 'MLM50744'}
PARENT = 'MLM1459'
OP = {'venta': 'Venta', 'renta': 'Alquiler'}
PT = {'departamento': 'Departamentos', 'casa': 'Casas', 'terreno': 'Terrenos', 'oficina': 'Oficinas',
      'local': 'Locales', 'bodega': 'Bodegas'}
COUNTRY_CODES = ('52', '1')  # Mexico first; US/Canada numbers for agents who use one


def category(c):
    return CATEGORIES.get((c['property_type'], c['operation'])) or PARENT


def split_phone(raw):
    """-> (country_code, number) as digits only, as ML asks for country_code2 / phone2; ('', '') if unknown."""
    e = norm_phone(raw)
    for cc in COUNTRY_CODES:
        if e.startswith('+' + cc):
            return cc, e[1 + len(cc):]
    return '', ''


def seller_contact(c):
    """Mandatory for Inmuebles since 2026-10-01: the WhatsApp goes in country_code2 + phone2."""
    who = c.get('agent') or {}
    ag = c.get('agency') or {}
    cc, num = split_phone(who.get('whatsapp') or ag.get('whatsapp'))
    return {'contact': who.get('name') or ag.get('name') or '', 'other_info': '',
            'country_code': cc, 'area_code': '', 'phone': num, 'country_code2': cc, 'phone2': num,
            'email': who.get('email') or ag.get('email') or '', 'webpage': ag.get('site_url') or ''}


def short_title(t, n=60):
    t = ' '.join((t or '').split())
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(' ', 1)[0]
    return cut if len(cut) >= n // 2 else t[:n]


def _n(v):
    return str(int(v)) if float(v) == int(v) else str(v)


def build_item(c):
    a, cat = c['address'], category(c)
    attrs = [{'id': 'OPERATION', 'value_name': OP.get(c['operation'], c['operation'])},
             {'id': 'PROPERTY_TYPE', 'value_name': PT.get(c['property_type'], c['property_type'])}]
    for aid, v, unit in (('ROOMS', c['bedrooms'], ''), ('BEDROOMS', c['bedrooms'], ''),
                         ('FULL_BATHROOMS', c['bathrooms'], ''), ('PARKING_LOTS', c['parking'], ''),
                         ('COVERED_AREA', c['m2_built'], ' m²'), ('TOTAL_AREA', c['m2_land'] or c['m2_built'], ' m²')):
        if v is not None:
            attrs.append({'id': aid, 'value_name': _n(v) + unit})
    todo = ['listing_type_id es un placeholder: confirmar plan de publicación de la cuenta del agente']
    if cat == PARENT:
        todo.append('TODO: confirmar categoría hoja con /categories')
    contact = seller_contact(c)
    if not contact['phone2']:
        todo.append('Falta un WhatsApp válido del agente (Mercado Libre lo exige)')
    if not c['photos']:
        todo.append('Falta al menos una foto (Mercado Libre la exige)')
    street = ' '.join(x for x in (a['street'], a['ext_number']) if x) if a['show_exact'] else ''
    item = {'site_id': 'MLM', 'category_id': cat, 'title': short_title(c['title']),
            'price': c['price'], 'currency_id': c['currency'], 'buying_mode': 'classified',
            'listing_type_id': 'silver',  # TODO: elegir según plan de la cuenta conectada
            'condition': 'not_specified',
            'pictures': [{'source': p['url']} for p in c['photos']],
            'attributes': attrs,
            'location': {'address_line': street, 'neighborhood': {'name': a['colonia'] or ''},
                         'city': {'name': a['municipio'] or ''}, 'state': {'name': a['estado'] or ''}},
            'description': {'plain_text': c['description']},
            'seller_contact': contact,
            '_dry_run': True, '_todo': todo}
    if a['show_exact'] and a['lat'] is not None and a['lng'] is not None:
        item['location']['latitude'], item['location']['longitude'] = a['lat'], a['lng']
    return item


def blockers(item):
    """What Mercado Libre would reject with HTTP 400; empty list = ready to send."""
    out = []
    if not item['seller_contact']['phone2']:
        out.append('Falta un WhatsApp válido del agente')
    if not item['pictures']:
        out.append('Falta al menos una foto')
    if item['category_id'] == PARENT:
        out.append('Tipo de propiedad sin categoría en Mercado Libre')
    return out


def dry_run_publish(con, listing_id):
    """DRY: store the would-be POST /items payload in the outbox and return it. No network."""
    payload = build_item(db.canonical(con, listing_id))
    con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('portal.mercadolibre.create', ?, ?, 'dry_run')",
                ('listing:%d' % listing_id, json.dumps(payload, ensure_ascii=False)))
    con.commit()
    return payload


# Status/price changes for a listing already on Mercado Libre (PUT /items/{id}). DRY ONLY, like publish.
STATUS = {'pause': 'paused', 'reactivate': 'active', 'close': 'closed'}


def build_update(c, action, external_id):
    """-> PUT /items/{external_id} body for 'pause' | 'reactivate' | 'close' | 'price'. Raises ValueError if it can't be sent."""
    if not external_id:
        raise ValueError('La propiedad aún no está publicada en Mercado Libre')
    if action in STATUS:
        body = {'status': STATUS[action]}
    elif action == 'price':
        if c['price'] is None:
            raise ValueError('Precio a consultar: Mercado Libre pide un precio')
        body = {'price': c['price']}
    else:
        raise ValueError('Acción desconocida: %s' % action)
    return {'method': 'PUT', 'path': '/items/%s' % external_id, 'body': body, '_dry_run': True}


def dry_run_update(con, listing_id, action):
    """DRY: store the would-be PUT in the outbox using the external_id saved in portal_publications."""
    row = con.execute("SELECT external_id FROM portal_publications WHERE listing_id=? AND portal='mercadolibre'",
                      (listing_id,)).fetchone()
    req = build_update(db.canonical(con, listing_id), action, row['external_id'] if row else None)
    con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES (?, ?, ?, 'dry_run')",
                ('portal.mercadolibre.' + action, 'listing:%d' % listing_id, json.dumps(req, ensure_ascii=False)))
    con.commit()
    return req


def sync_plan_limit(con, agency_id):
    """DRY: after a plan change (Pro -> Gratis, or back), queue 'pause' for published, still-public ML items the plan no longer shows
    and 'reactivate' for ones it shows again. Idempotent: the last queued pause/reactivate per listing is the memory.
    -> {'pause': [listing_id], 'reactivate': [listing_id]}"""
    shown = set(db.public_listing_ids(con, agency_id, include_shared=False))
    rows = con.execute("SELECT pp.listing_id FROM portal_publications pp JOIN listings l ON l.id=pp.listing_id "
                       "WHERE l.agency_id=? AND pp.portal='mercadolibre' AND pp.external_id IS NOT NULL "
                       "AND pp.external_id<>'' AND l.status IN %s ORDER BY pp.listing_id" % (db.PUBLIC_STATUSES,),
                       (agency_id,)).fetchall()
    out = {'pause': [], 'reactivate': []}
    for r in rows:
        lid = r['listing_id']
        last = con.execute("SELECT kind FROM outbox WHERE ref=? AND kind IN ('portal.mercadolibre.pause',"
                           "'portal.mercadolibre.reactivate') ORDER BY id DESC LIMIT 1", ('listing:%d' % lid,)).fetchone()
        paused = bool(last) and last['kind'].endswith('.pause')
        if lid not in shown and not paused:
            dry_run_update(con, lid, 'pause')
            out['pause'].append(lid)
        elif lid in shown and paused:
            dry_run_update(con, lid, 'reactivate')
            out['reactivate'].append(lid)
    return out


def sync_plan_limit_safe(con, agency_id):
    """What every place that changes a plan calls, AFTER it has committed the change: sync_plan_limit, but it never raises, so a problem
    here can never undo or fail a plan change or a Stripe webhook. A failure is rolled back, written to stderr, reported through
    llave.alerts (no personal data in it) and left for the next sweep (tools/ml_plan_sync_run.py), because sync_plan_limit is idempotent.
    Still dry-run: the only effect is outbox rows. -> the sync_plan_limit result, or None when it failed."""
    try:
        return sync_plan_limit(con, agency_id)
    except Exception as ex:
        try:
            con.rollback()
        except Exception:
            pass
        sys.stderr.write('[llave] mercadolibre plan sync agency:%s: %s: %s\n' % (agency_id, type(ex).__name__, str(ex)[:200]))
        try:
            from .. import alerts
            alerts.report(ex, {'path': 'mercadolibre.sync_plan_limit'})
        except Exception:
            pass
        return None


def sync_all(con):
    """The sweep behind the cron: sync_plan_limit_safe for every agency that has a published Mercado Libre item, so a sync that failed once,
    or a limit that moved without a plan change (referral bonus, RentaPóliza credit), is caught within the hour.
    -> {agency_id: {'pause': [...], 'reactivate': [...]}} for the agencies where something was queued."""
    ids = [r['agency_id'] for r in con.execute(
        "SELECT DISTINCT l.agency_id FROM portal_publications pp JOIN listings l ON l.id=pp.listing_id "
        "WHERE pp.portal='mercadolibre' AND pp.external_id IS NOT NULL AND pp.external_id<>'' ORDER BY l.agency_id")]
    out = {}
    for aid in ids:
        r = sync_plan_limit_safe(con, aid)
        if r and (r['pause'] or r['reactivate']):
            out[aid] = r
    return out
