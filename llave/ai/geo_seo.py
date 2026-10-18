"""FAQ blocks for Google + AI assistants, built ONLY from facts we hold (no AI, no invention)."""
from .. import db
from ..web.common import money, nice_date

TYPE_NAME = {'departamento': 'departamento', 'casa': 'casa', 'terreno': 'terreno', 'oficina': 'oficina',
             'local': 'local comercial', 'bodega': 'bodega'}
TYPE_PLURAL = {'departamento': 'departamentos', 'casa': 'casas', 'terreno': 'terrenos', 'oficina': 'oficinas',
               'local': 'locales comerciales', 'bodega': 'bodegas'}


def _join(items):
    items = list(items)
    if len(items) <= 1:
        return ''.join(items)
    return ', '.join(items[:-1]) + ' y ' + items[-1]


def _wa_digits(s):
    return ''.join(ch for ch in (s or '') if ch.isdigit())


def listing_faq(c):
    a = c.get('address') or {}
    ag = c.get('agency') or {}
    ptype = TYPE_NAME.get(c.get('property_type'), 'propiedad')
    rent = c.get('operation') == 'renta'
    out = []
    if c.get('price') is not None:
        ans = '%s de este %s es %s' % ('La renta' if rent else 'El precio', ptype, money(c['price'], c.get('currency')))
        if c.get('price_date'):
            ans += ' (precio confirmado el %s)' % nice_date(c['price_date'])
        ans += '.'
        if c.get('maintenance'):
            ans += ' El mantenimiento mensual es de %s.' % money(c['maintenance'], c.get('currency'))
        out.append({'q': '¿Cuánto cuesta %s?' % ('la renta de este ' + ptype if rent else 'este ' + ptype), 'a': ans})
    if c.get('m2_built') or c.get('m2_land'):
        bits = []
        if c.get('m2_built'):
            bits.append('%g m² de construcción' % c['m2_built'])
        if c.get('m2_land'):
            bits.append('%g m² de terreno' % c['m2_land'])
        out.append({'q': '¿Cuántos metros cuadrados tiene?', 'a': 'Tiene %s.' % ' y '.join(bits)})
    if c.get('bedrooms') or c.get('bathrooms'):
        bits = []
        if c.get('bedrooms'):
            bits.append('%d %s' % (c['bedrooms'], 'recámara' if c['bedrooms'] == 1 else 'recámaras'))
        if c.get('bathrooms'):
            bits.append('%g %s' % (c['bathrooms'], 'baño' if c['bathrooms'] == 1 else 'baños'))
        out.append({'q': '¿Cuántas recámaras y baños tiene?', 'a': 'Cuenta con %s.' % ' y '.join(bits)})
    if c.get('parking'):
        out.append({'q': '¿Tiene estacionamiento?',
                    'a': 'Sí, cuenta con %d %s.' % (c['parking'], 'lugar de estacionamiento' if c['parking'] == 1 else 'lugares de estacionamiento')})
    if c.get('pets'):
        out.append({'q': '¿Se aceptan mascotas?', 'a': 'Sí, se aceptan mascotas.'})
    if c.get('furnished'):
        out.append({'q': '¿Está amueblado?', 'a': 'Sí, se entrega amueblado.'})
    if a.get('colonia') or a.get('municipio'):
        place = ', '.join(x for x in (a.get('colonia'), a.get('municipio')) if x)
        out.append({'q': '¿Dónde está ubicado?', 'a': 'Está en %s.' % place})
    who = ag.get('name') or 'la inmobiliaria'
    wa = _wa_digits(ag.get('whatsapp'))
    ans = 'Escríbanos por WhatsApp a %s indicando el folio %s y le proponemos horarios.' % (who, c.get('ref')) if not wa else \
        'Escriba por WhatsApp a %s (+%s) indicando el folio %s y le proponemos horarios.' % (who, wa, c.get('ref'))
    out.append({'q': '¿Cómo agendo una visita?', 'a': ans})
    return out


def faq_jsonld(faqs):
    return {'@context': 'https://schema.org', '@type': 'FAQPage',
            'mainEntity': [{'@type': 'Question', 'name': f['q'],
                            'acceptedAnswer': {'@type': 'Answer', 'text': f['a']}} for f in faqs]}


def agency_faq(con, agency):
    ag = dict(agency)
    ph = ','.join('?' * len(db.PUBLIC_STATUSES))
    rows = con.execute('SELECT property_type, operation, colonia, municipio FROM listings WHERE agency_id=? AND status IN (%s)'
                       % ph, [ag['id']] + list(db.PUBLIC_STATUSES)).fetchall()
    out = []
    zones = sorted({r['colonia'] for r in rows if r['colonia']})
    if zones:
        out.append({'q': '¿En qué zonas tiene propiedades %s?' % ag['name'],
                    'a': '%s tiene propiedades publicadas en %s.' % (ag['name'], _join(zones))})
    types = sorted({r['property_type'] for r in rows})
    if types:
        ops = sorted({r['operation'] for r in rows})
        opt = _join({'venta': 'venta', 'renta': 'renta'}.get(o, o) for o in ops)
        out.append({'q': '¿Qué tipos de propiedades ofrece?',
                    'a': 'Hoy publica %s, en %s.' % (_join(TYPE_PLURAL.get(t, t) for t in types), opt)})
    wa = _wa_digits(ag.get('whatsapp'))
    how = 'Escríbanos por WhatsApp' + (' al +%s' % wa if wa else '')
    if ag.get('email'):
        how += ' o por correo a %s' % ag['email']
    out.append({'q': '¿Cómo contacto a %s?' % ag['name'], 'a': how + '. También puede dejar sus datos en el formulario de cada propiedad.'})
    return out
