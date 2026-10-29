"""Mercado Libre (site MLM) item payloads. DRY ONLY: nothing here touches the network."""
import json

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
