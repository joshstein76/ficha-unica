"""Mercado Libre (site MLM) item payloads. DRY ONLY: nothing here touches the network."""
import json

from .. import db

CATEGORIES = {  # (property_type, operation) -> leaf/parent id; only IDs we are sure of
    ('departamento', None): 'MLM1472', ('casa', None): 'MLM1466', ('bodega', None): 'MLM50743'}
PARENT = 'MLM1459'
OP = {'venta': 'Venta', 'renta': 'Alquiler'}
PT = {'departamento': 'Departamentos', 'casa': 'Casas', 'terreno': 'Terrenos', 'oficina': 'Oficinas',
      'local': 'Locales', 'bodega': 'Bodegas'}


def category(c):
    return CATEGORIES.get((c['property_type'], None)) or CATEGORIES.get((c['property_type'], c['operation'])) or PARENT


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
            '_dry_run': True, '_todo': todo}
    if a['show_exact'] and a['lat'] is not None and a['lng'] is not None:
        item['location']['latitude'], item['location']['longitude'] = a['lat'], a['lng']
    return item


def dry_run_publish(con, listing_id):
    """DRY: store the would-be POST /items payload in the outbox and return it. No network."""
    payload = build_item(db.canonical(con, listing_id))
    con.execute("INSERT INTO outbox(kind, ref, payload, status) VALUES ('portal.mercadolibre.create', ?, ?, 'dry_run')",
                ('listing:%d' % listing_id, json.dumps(payload, ensure_ascii=False)))
    con.commit()
    return payload
