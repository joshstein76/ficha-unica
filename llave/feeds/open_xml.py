"""Open feed formats: Trovit-style, Mitula-style and LLAVE's own documented XML/JSON."""
import json
import xml.etree.ElementTree as ET

CT_XML = 'application/xml; charset=utf-8'
CT_JSON = 'application/json; charset=utf-8'
NOTE = 'Formato basado en especificación pública conocida; confirmar con Lifull Connect antes de activar'

TROVIT_TYPE = {'departamento': 'Apartment', 'casa': 'House', 'terreno': 'Land', 'oficina': 'Office',
               'local': 'Commercial', 'bodega': 'Warehouse'}
TROVIT_OP = {'venta': 'For Sale', 'renta': 'For Rent'}
ES_TYPE = {'departamento': 'Departamento', 'casa': 'Casa', 'terreno': 'Terreno', 'oficina': 'Oficina',
           'local': 'Local', 'bodega': 'Bodega'}


def _num(v):
    if v is None:
        return None
    return str(int(v)) if float(v) == int(v) else str(v)


def _sub(parent, tag, text=None, **attrs):
    e = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = str(text)
    return e


def _doc(root, comment=None):
    body = ET.tostring(root, encoding='unicode')
    head = '<?xml version="1.0" encoding="UTF-8"?>\n'
    if comment:
        head += '<!-- %s -->\n' % comment
    return (head + body + '\n').encode('utf-8')


def trovit(canons):
    root = ET.Element('trovit')
    for c in canons:
        a, ad = c['address'], ET.SubElement(root, 'ad')
        _sub(ad, 'id', c['ref']); _sub(ad, 'url', c['url']); _sub(ad, 'title', c['title'])
        _sub(ad, 'type', TROVIT_OP.get(c['operation'], 'For Sale')); _sub(ad, 'content', c['description'])
        if c['price'] is not None:
            _sub(ad, 'price', c['price'], currency=c['currency'])
        _sub(ad, 'property_type', TROVIT_TYPE.get(c['property_type'], 'Apartment'))
        _sub(ad, 'address', ' '.join(x for x in (a['street'], a['ext_number']) if x) if a['show_exact'] else (a['colonia'] or ''))
        _sub(ad, 'city_area', a['colonia'] or ''); _sub(ad, 'city', a['municipio'] or '')
        _sub(ad, 'region', a['estado'] or ''); _sub(ad, 'postcode', a['cp'] or ''); _sub(ad, 'country', 'MX')
        if a['show_exact'] and a['lat'] is not None and a['lng'] is not None:
            _sub(ad, 'latitude', a['lat']); _sub(ad, 'longitude', a['lng'])
        if c['m2_built']:
            _sub(ad, 'floor_area', _num(c['m2_built']), unit='meters')
        if c['m2_land']:
            _sub(ad, 'plot_area', _num(c['m2_land']), unit='meters')
        for tag, v in (('rooms', c['bedrooms']), ('bathrooms', c['bathrooms']), ('parking', c['parking'])):
            if v is not None:
                _sub(ad, tag, _num(v))
        _sub(ad, 'is_furnished', 1 if c['furnished'] else 0)
        pics = _sub(ad, 'pictures')
        for p in c['photos']:
            pe = _sub(pics, 'picture'); _sub(pe, 'picture_url', p['url']); _sub(pe, 'picture_title', p['alt'])
        _sub(ad, 'agency', c['agency']['name']); _sub(ad, 'date', c['updated_at'])
    return CT_XML, _doc(root, NOTE)


def mitula(canons):
    root = ET.Element('Mitula')
    for c in canons:
        a, ad = c['address'], ET.SubElement(root, 'ad')
        _sub(ad, 'id', c['ref']); _sub(ad, 'url', c['url']); _sub(ad, 'title', c['title'])
        _sub(ad, 'type', c['operation']); _sub(ad, 'content', c['description'])
        if c['price'] is not None:
            _sub(ad, 'price', c['price']); _sub(ad, 'currency', c['currency'])
        _sub(ad, 'property_type', ES_TYPE.get(c['property_type'], 'Departamento'))
        for tag, v in (('rooms', c['bedrooms']), ('bathrooms', c['bathrooms']), ('floor_area', c['m2_built'])):
            if v is not None:
                _sub(ad, tag, _num(v))
        _sub(ad, 'city', a['municipio'] or ''); _sub(ad, 'region', a['estado'] or ''); _sub(ad, 'city_area', a['colonia'] or '')
        pics = _sub(ad, 'pictures')
        for p in c['photos']:
            _sub(_sub(pics, 'picture'), 'picture_url', p['url'])
        _sub(ad, 'date', c['updated_at'])
    return CT_XML, _doc(root, NOTE)


def _open_dict(c):
    d = json.loads(json.dumps(c))
    if d.get('agent'):
        d['agent'].pop('email', None)
    return d


def _to_xml(parent, tag, v):
    if isinstance(v, dict):
        e = ET.SubElement(parent, tag)
        for k, x in v.items():
            _to_xml(e, k, x)
    elif isinstance(v, list):
        e = ET.SubElement(parent, tag)
        for x in v:
            _to_xml(e, tag[:-1] if tag.endswith('s') else 'item', x)
    else:
        e = ET.SubElement(parent, tag)
        if v is not None:
            e.text = ('true' if v else 'false') if isinstance(v, bool) else str(v)


def llave_xml(canons):
    root = ET.Element('llave', version='1')
    for c in canons:
        _to_xml(root, 'listing', _open_dict(c))
    return CT_XML, _doc(root)


def llave_json(canons):
    out = {'version': 1, 'listings': [_open_dict(c) for c in canons]}
    return CT_JSON, json.dumps(out, ensure_ascii=False, indent=1).encode('utf-8')
