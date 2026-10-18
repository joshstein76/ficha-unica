"""Listing copy: AI when enabled (validated against the facts), otherwise a deterministic template."""
import json
import re

from . import client
from ..web.common import money, nice_date

TYPE_ES = {'departamento': 'Departamento', 'casa': 'Casa', 'terreno': 'Terreno', 'oficina': 'Oficina',
           'local': 'Local comercial', 'bodega': 'Bodega'}
TYPE_EN = {'departamento': 'Apartment', 'casa': 'House', 'terreno': 'Land', 'oficina': 'Office',
           'local': 'Commercial space', 'bodega': 'Warehouse'}
BANNED = re.compile(r'\b(el mejor|la mejor|único|unica|única|único|the best|unique|best)\b', re.I)
EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿]')
NUM_RE = re.compile(r'\d[\d,\.]*\d|\d')

SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'},
        'description': {'type': 'string'},
        'highlights': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['title', 'description', 'highlights'],
    'additionalProperties': False,
}

SYSTEM_ES = (
    'Eres redactor inmobiliario en México para Ficha Única. Escribe en español de México, de "usted", con '
    'oraciones cortas y humanas. Usa SOLO los hechos del JSON del anuncio: nunca inventes amenidades, vistas, '
    'distancias, precios, años ni afirmaciones como "el mejor" o "único". No uses emojis. '
    'Título: máximo 90 caracteres, con tipo de propiedad, operación, colonia y un dato clave. '
    'Descripción: entre 90 y 160 palabras. Entre 3 y 5 puntos destacados cortos. '
    'Cualquier cifra que escriba debe aparecer tal cual en el JSON.')
SYSTEM_EN = (
    'You are a real estate copywriter in Mexico for Ficha Unica. Write natural US English. Short, human sentences. '
    'Use ONLY facts from the listing JSON: never invent amenities, views, distances, prices, years, or claims such as '
    '"the best" or "unique". No emoji. Title: at most 90 characters with property type, operation, neighborhood and one '
    'key number. Description: 90 to 160 words. 3 to 5 short highlights. Every number you write must appear in the JSON.')


def facts(c):
    """Only what the AI may use. No contact data, no exact address, no internal notes."""
    a = c.get('address') or {}
    f = {
        'operacion': c.get('operation'), 'tipo': c.get('property_type'),
        'precio': c.get('price'), 'moneda': c.get('currency'), 'fecha_del_precio': c.get('price_date'),
        'mantenimiento': c.get('maintenance'), 'm2_construidos': c.get('m2_built'), 'm2_terreno': c.get('m2_land'),
        'recamaras': c.get('bedrooms'), 'banos': c.get('bathrooms'), 'estacionamientos': c.get('parking'),
        'piso': c.get('floor'), 'ano_construccion': c.get('year_built'),
        'amueblado': bool(c.get('furnished')), 'acepta_mascotas': bool(c.get('pets')),
        'amenidades': c.get('amenities') or [],
        'colonia': a.get('colonia'), 'municipio': a.get('municipio'), 'estado': a.get('estado'),
        'texto_del_asesor': c.get('description') or '',
    }
    return {k: v for k, v in f.items() if v not in (None, '', [])}


def _norm(tok):
    try:
        return float(tok.replace(',', ''))
    except ValueError:
        return None


def _numbers(text):
    out = set()
    for t in NUM_RE.findall(text or ''):
        v = _norm(t)
        if v is not None:
            out.add(v)
    return out


def allowed_numbers(c):
    allowed = _numbers(json.dumps(facts(c), ensure_ascii=False))
    allowed |= _numbers(c.get('title') or '')
    return allowed


def validate(c, out):
    """-> reason string if the AI output must be rejected, else None."""
    if not isinstance(out, dict):
        return 'respuesta inválida'
    title, desc, hl = out.get('title'), out.get('description'), out.get('highlights')
    if not (isinstance(title, str) and isinstance(desc, str) and isinstance(hl, list)
            and all(isinstance(h, str) for h in hl)):
        return 'estructura inválida'
    text = ' '.join([title, desc] + hl)
    if len(title) > 90:
        return 'título de más de 90 caracteres'
    if not 3 <= len(hl) <= 5:
        return 'número de puntos destacados fuera de 3-5'
    if EMOJI.search(text):
        return 'contiene emojis'
    if BANNED.search(text):
        return 'contiene afirmaciones no verificables'
    extra = _numbers(text) - allowed_numbers(c)
    if extra:
        return 'cifras que no están en la ficha: %s' % ', '.join('%g' % x for x in sorted(extra))
    return None


def _plural(n, one, many):
    return one if n == 1 else many


def template(c, lang='es'):
    en = lang == 'en'
    a = c.get('address') or {}
    ptype = (TYPE_EN if en else TYPE_ES).get(c.get('property_type'), (c.get('property_type') or 'Propiedad').capitalize())
    rent = c.get('operation') == 'renta'
    op = ('for rent' if rent else 'for sale') if en else ('en renta' if rent else 'en venta')
    col = a.get('colonia') or a.get('municipio') or ''
    key = ''
    if c.get('bedrooms'):
        key = ('%d bd' % c['bedrooms']) if en else ('%d recámaras' % c['bedrooms'] if c['bedrooms'] != 1 else '1 recámara')
    elif c.get('m2_built'):
        key = '%g m²' % c['m2_built']
    title = '%s %s' % (ptype, op)
    if col:
        title += (' in ' if en else ' en ') + col
    if key:
        title += ', ' + key
    if len(title) > 90:
        title = title[:89].rstrip(' ,') + '…'
    nbits = []
    if c.get('m2_built'):
        nbits.append('%g m² %s' % (c['m2_built'], 'built' if en else 'de construcción'))
    if c.get('m2_land'):
        nbits.append('%g m² %s' % (c['m2_land'], 'of land' if en else 'de terreno'))
    if c.get('bedrooms'):
        nbits.append(('%d %s' % (c['bedrooms'], _plural(c['bedrooms'], 'bedroom', 'bedrooms'))) if en else
                     ('%d %s' % (c['bedrooms'], _plural(c['bedrooms'], 'recámara', 'recámaras'))))
    if c.get('bathrooms'):
        nbits.append(('%g %s' % (c['bathrooms'], _plural(c['bathrooms'], 'bathroom', 'bathrooms'))) if en else
                     ('%g %s' % (c['bathrooms'], _plural(c['bathrooms'], 'baño', 'baños'))))
    if c.get('parking'):
        nbits.append(('%d parking %s' % (c['parking'], _plural(c['parking'], 'space', 'spaces'))) if en else
                     ('%d %s' % (c['parking'], _plural(c['parking'], 'lugar de estacionamiento', 'lugares de estacionamiento'))))
    place = ', '.join(x for x in (a.get('colonia'), a.get('municipio')) if x)
    s = []
    if en:
        s.append('%s %s%s.' % (ptype, op, (' in ' + place) if place else ''))
        if nbits:
            s.append('It offers ' + ', '.join(nbits) + '.')
        if c.get('floor'):
            s.append('It is on floor %s.' % c['floor'])
        if c.get('year_built'):
            s.append('Built in %d.' % c['year_built'])
        if c.get('price') is not None:
            s.append('%s price: %s%s.' % ('Rent' if rent else 'Asking', money(c['price'], c.get('currency')),
                                          (', confirmed on ' + nice_date(c['price_date'])) if c.get('price_date') else ''))
        if c.get('maintenance'):
            s.append('Monthly maintenance: %s.' % money(c['maintenance'], c.get('currency')))
        if c.get('furnished'):
            s.append('It is furnished.')
        if c.get('pets'):
            s.append('Pets are welcome.')
        if c.get('amenities'):
            s.append('Amenities: ' + ', '.join(c['amenities']) + '.')
        s.append('Write to us on WhatsApp to schedule a visit or ask for the full details of this listing.')
    else:
        s.append('%s %s%s.' % (ptype, op, (' en ' + place) if place else ''))
        if nbits:
            s.append('Cuenta con ' + ', '.join(nbits) + '.')
        if c.get('floor'):
            s.append('Se ubica en el piso %s.' % c['floor'])
        if c.get('year_built'):
            s.append('Fue construido en %d.' % c['year_built'])
        if c.get('price') is not None:
            s.append('%s: %s%s.' % ('Renta' if rent else 'Precio', money(c['price'], c.get('currency')),
                                    (', confirmado el ' + nice_date(c['price_date'])) if c.get('price_date') else ''))
        if c.get('maintenance'):
            s.append('Mantenimiento mensual: %s.' % money(c['maintenance'], c.get('currency')))
        if c.get('furnished'):
            s.append('Se entrega amueblado.')
        if c.get('pets'):
            s.append('Acepta mascotas.')
        if c.get('amenities'):
            s.append('Amenidades: ' + ', '.join(c['amenities']) + '.')
        s.append('Escríbanos por WhatsApp para agendar su visita o pedir más detalles de esta propiedad.')
    hl = []
    if c.get('m2_built'):
        hl.append('%g m²' % c['m2_built'])
    if c.get('bedrooms'):
        hl.append(nbits[[i for i, b in enumerate(nbits) if ('bedroom' in b or 'recámara' in b)][0]])
    if c.get('bathrooms'):
        hl.append([b for b in nbits if ('bathroom' in b or 'baño' in b)][0])
    if c.get('parking'):
        hl.append([b for b in nbits if ('parking' in b or 'estacionamiento' in b)][0])
    if c.get('pets'):
        hl.append('Pets welcome' if en else 'Acepta mascotas')
    if c.get('furnished'):
        hl.append('Furnished' if en else 'Amueblado')
    for am in c.get('amenities') or []:
        hl.append(am)
    if place:
        hl.append(place)
    hl = hl[:5]
    return {'title': title, 'description': ' '.join(s), 'highlights': hl}


def describe(canonical, lang='es', transport=None):
    """-> {title, description, highlights, source: 'ia'|'plantilla', reason}. Never raises."""
    lang = 'en' if lang == 'en' else 'es'
    reason = None
    if client.enabled():
        try:
            user = 'Datos del anuncio (JSON):\n' + json.dumps(facts(canonical), ensure_ascii=False)
            out = client.complete_json(SYSTEM_EN if lang == 'en' else SYSTEM_ES, user, SCHEMA,
                                       effort='low', transport=transport)
            reason = validate(canonical, out)
            if reason is None:
                return {'title': out['title'].strip(), 'description': out['description'].strip(),
                        'highlights': [h.strip() for h in out['highlights']], 'source': 'ia', 'reason': None}
        except client.AIError as ex:
            reason = 'IA no disponible: %s' % ex
    else:
        reason = 'IA desactivada'
    t = template(canonical, lang)
    t['source'] = 'plantilla'
    t['reason'] = reason
    return t
