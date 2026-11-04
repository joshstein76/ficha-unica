"""Shared helpers for the panel and the agent sites: escaping, money, dates, forms, CSRF."""
import datetime
import hashlib
import hmac
import html
import os

from .. import db

SECRET = os.environ.get('LLAVE_SECRET', 'llave-local-dev-secret')  # prod: from config, never committed

MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
TYPES = [('departamento', 'Departamento'), ('casa', 'Casa'), ('terreno', 'Terreno'),
         ('oficina', 'Oficina'), ('local', 'Local comercial'), ('bodega', 'Bodega')]
STATUSES = [('borrador', 'Borrador'), ('activa', 'Activa'), ('apartada', 'Apartada'),
            ('pausada', 'Pausada'), ('vendida', 'Vendida'), ('rentada', 'Rentada')]
LEAD_STATUSES = [('nuevo', 'Nuevo'), ('contactado', 'Contactado'), ('cita', 'Cita'),
                 ('cerrado', 'Cerrado'), ('descartado', 'Descartado')]
DESIGNS = [('loteria', 'Lotería', 'Con color y carácter: bordes marcados y tu color de acento'),
           ('residencia', 'Residencia', 'Elegante, fotos grandes, tipografía clásica'),
           ('ciudad', 'Ciudad', 'Moderno y limpio, ideal para departamentos'),
           ('costa', 'Costa', 'Claro y luminoso, ideal para casas y playa')]
DESIGN_KEYS = tuple(k for k, _, _ in DESIGNS)


def e(s):
    return html.escape('' if s is None else str(s), quote=True)


def props(n):
    """'1 propiedad' / '25 propiedades'; a plan without a limit reads 'propiedades sin límite'."""
    if db.is_unlimited(n):
        return 'propiedades sin límite'
    return '1 propiedad' if n == 1 else '%d propiedades' % n


def money(price, currency):
    if price is None:
        return 'Precio a consultar'
    n = '{:,}'.format(int(price))
    return ('US$' + n) if currency == 'USD' else ('$' + n + ' MXN')


def nice_date(iso):
    if not iso:
        return ''
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return '%d %s %d' % (d.day, MONTHS[d.month - 1], d.year)


def label(pairs, key):
    return dict((p[0], p[1]) for p in pairs).get(key, key or '')


def facts_line(c):
    bits = []
    if c.get('m2_built'):
        bits.append('%g m²' % c['m2_built'])
    if c.get('bedrooms'):
        bits.append('%d rec.' % c['bedrooms'])
    if c.get('bathrooms'):
        bits.append('%g baño%s' % (c['bathrooms'], '' if c['bathrooms'] == 1 else 's'))
    if c.get('parking'):
        bits.append('%d est.' % c['parking'])
    return ' · '.join(bits)


def csrf_token(session_token):
    return hmac.new(SECRET.encode(), (session_token or '').encode(), hashlib.sha256).hexdigest()[:32]


def csrf_ok(session_token, sent):
    return bool(session_token) and hmac.compare_digest(csrf_token(session_token), sent or '')


def to_cents(raw):
    raw = (raw or '').replace(',', '').replace('$', '').strip()
    if not raw:
        return None
    try:
        return int(round(float(raw) * 100))
    except (ValueError, OverflowError):
        raise ValueError('El precio debe ser un número, por ejemplo 4500000')


MAX_PRICE_CENTS = 10 ** 13  # 100 mil millones: a typo with too many zeros, never a real price (also keeps SQLite's 64-bit integer safe)


def to_price_cents(raw):
    """A listing price. Empty = no price yet (the site says 'Precio a consultar'); otherwise it must be a number above 0:
    '$-5 MXN' or '$0 MXN' on a public page reads as a bug."""
    c = to_cents(raw)
    if c is None:
        return None
    if c <= 0 or c > MAX_PRICE_CENTS:
        raise ValueError('Revisa el precio: escribe solo números, mayor que 0, por ejemplo 4500000.')
    return c


def to_num(raw, kind=float):
    raw = (raw or '').replace(',', '').strip()
    if not raw:
        return None
    try:
        return kind(float(raw)) if kind is int else kind(raw)
    except ValueError:
        raise ValueError('Revisa los números (m², recámaras, baños)')
