"""Server-side "search bar" of the agent sites (LLAVE_SITE_ASK=1): Spanish free text -> filters -> the agency's OWN public listings.
There is no MLS in Mexico, so nothing outside this agency (and its shared Bolsa pool) is ever searched. No AI, no network: plain rules.
The answer has the same shape as the IDX Bloom "Ask" API ({q, kind, listings, total, summary}) so both products share one front end."""
import os
import re
import unicodedata

from . import db
from .web.common import money

MAX_CARDS, MAX_CARDS_PHONE = 6, 4
MAX_Q = 200

RENT_RE = re.compile(r'\b(rentas?|rentar|rento|rentan|alquiler|alquilar|mensual|mensuales|al mes)\b')
SALE_RE = re.compile(r'\b(venta|vender|vendo|comprar|compra)\b')
TYPE_WORDS = {
    'departamento': r'depas?|deptos?|dptos?|departamentos?|apartamentos?',
    'casa': r'casas?',
    'terreno': r'terrenos?|lotes?',
    'oficina': r'oficinas?',
    'local': r'local comercial|locales?',
    'bodega': r'bodegas?|naves?',
}
TYPE_PLURAL = {'departamento': ('departamento', 'departamentos'), 'casa': ('casa', 'casas'), 'terreno': ('terreno', 'terrenos'),
               'oficina': ('oficina', 'oficinas'), 'local': ('local', 'locales'), 'bodega': ('bodega', 'bodegas')}
NUMBER_WORDS = {'un': 1, 'una': 1, 'uno': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5, 'seis': 6}
STOP = set('''en de del la el los las un una unos unas con que busco buscando quiero quisiera necesito tiene tengan tienen hay para por
hasta menos maximo max minimo mas o y a al mes entre cerca zona precio presupuesto desde como me mi su se es lo e ver mostrar muestre muestrame
dame favor propiedad propiedades inmueble inmuebles pesos peso mxn mdp nuevo bonito bonita barato barata'''.split())
BEDS_RE = re.compile(r'\b(\d+|%s)\s*(?:recamaras?|recs?|habitaciones|habitacion|habs?|cuartos?|dormitorios?)\b' % '|'.join(NUMBER_WORDS))
BATHS_RE = re.compile(r'\b(\d+(?:\.5)?|%s)\s*(?:banos?)\b' % '|'.join(NUMBER_WORDS))
# an amount: "3.5 mdp", "3 millones", "3m", "20 mil", "$18,000", "18000". Group 2 is the unit (if any).
AMOUNT_RE = re.compile(r'(\$)?\s*(\d[\d,]*(?:\.\d+)?)\s*(millones|millon|mdp|mm|m(?![\w²])|mil(?![a-z]))?')


def norm(text):
    """Lowercase, no accents (the ñ becomes n too), single spaces."""
    t = unicodedata.normalize('NFKD', str(text or '').lower())
    return re.sub(r'\s+', ' ', ''.join(ch for ch in t if not unicodedata.combining(ch))).strip()


def _num(s):
    s = str(s)
    return NUMBER_WORDS[s] if s in NUMBER_WORDS else float(s)


def _amount(m):
    """Pesos from one AMOUNT_RE match, or None when it is not a price (a bare small number)."""
    dollar, raw, unit = m.group(1), m.group(2), m.group(3)
    raw = raw.replace(',', '')
    if not unit and re.match(r'^\d{1,3}(\.\d{3})+$', raw):
        raw = raw.replace('.', '')  # 3.500.000 / 18.000 = thousands separators
    n = float(raw)
    if unit == 'mil':
        n *= 1000
    elif unit:
        n *= 1000000
    elif not dollar and n < 1000:
        return None
    return int(round(n))


def _take(rx, text):
    m = rx.search(text)
    return (m, text[:m.start()] + ' ' + text[m.end():]) if m else (None, text)


def _colonia(text, colonias):
    """(display name, tokens, text without it). A full colonia/municipio name wins; else every word that is a word of one of them."""
    names = sorted({c.strip() for c in colonias if c and c.strip()}, key=lambda c: -len(norm(c)))
    for c in names:
        n = norm(c)
        m = re.search(r'\b%s\b' % re.escape(n), text)
        if m:
            return c, n.split(), text[:m.start()] + ' ' + text[m.end():]
    vocab = {}  # normalised word -> the word as the agent wrote it (with accents)
    for c in names:
        for w in c.split():
            if len(norm(w)) >= 3 and norm(w) not in STOP:
                vocab.setdefault(norm(w), w)
    hits = [w for w in text.split() if w in vocab]
    if not hits:
        return '', [], text
    return ' '.join(vocab[w] for w in hits), hits, ' '.join(w for w in text.split() if w not in hits)


WORD_AMOUNTS = [  # spoken amounts -> digits the AMOUNT_RE understands (2026-11-23, from IDX Bloom's "900 mil" lesson)
    (re.compile(r'\b(?:un|1) millon(?:es)? y medio\b'), ' 1.5 millones '),
    (re.compile(r'\bmedio millon\b'), ' 0.5 millones '),
    (re.compile(r'\b(%s) (millon(?:es)?|mil)\b' % '|'.join(NUMBER_WORDS)), lambda m: ' %d %s ' % (NUMBER_WORDS[m.group(1)], m.group(2))),
]
RANGE_RE = re.compile(r'\bentre\s+(\$?\s*\d[\d,.]*)\s*(millones|millon|mdp|mil)?\s+y\s+')


def _spoken(t):
    for rx, rep in WORD_AMOUNTS:
        t = rx.sub(rep, t)
    m = RANGE_RE.search(t)  # "entre 2 y 3 millones" / "entre 2 millones y 3 millones": the upper end is the ceiling
    if m:
        t = t[:m.start()] + ' ' + t[m.end():]
    return t


def parse(q, colonias=()):
    """Spanish free text -> {operation, type, beds, baths, max_price, colonia, colonia_tokens, terms}. Every key may be None/''/[]."""
    t = _spoken(' ' + norm(str(q or '')[:MAX_Q]) + ' ')
    f = {'operation': None, 'type': None, 'beds': None, 'baths': None, 'max_price': None, 'colonia': '', 'colonia_tokens': [], 'terms': []}
    m, t = _take(BEDS_RE, t)
    if m:
        f['beds'] = int(_num(m.group(1)))
    m, t = _take(BATHS_RE, t)
    if m:
        f['baths'] = _num(m.group(1))
    for m in AMOUNT_RE.finditer(t):
        amount = _amount(m)
        if amount:
            f['max_price'] = amount
            t = t[:m.start()] + ' ' + t[m.end():]
            break
    f['operation'] = 'renta' if RENT_RE.search(t) else ('venta' if SALE_RE.search(t) else None)
    t = SALE_RE.sub(' ', RENT_RE.sub(' ', t))
    for key, words in TYPE_WORDS.items():
        m, t = _take(re.compile(r'\b(?:%s)\b' % words), t)
        if m:
            f['type'] = key
            break
    f['colonia'], f['colonia_tokens'], t = _colonia(t, colonias)
    f['terms'] = [w for w in re.sub(r'[^a-z0-9 ]', ' ', t).split() if len(w) >= 3 and w not in STOP and not w.isdigit()]
    return f


def _has_filters(f):
    return any(f[k] for k in ('operation', 'type', 'beds', 'baths', 'max_price', 'colonia_tokens', 'terms'))


def _ids(con, agency):
    """The listing ids this agency's site shows: its own public ones (+ active Bolsa shares), plus the pool section when it is on."""
    ids = list(db.public_listing_ids(con, agency['id']))
    pool = getattr(db, 'pool_listing_ids', None)
    if pool:
        ids += [i for i in pool(con, agency['id'], base=ids) if i not in ids]
    return ids


def _place(c):
    a = c['address']
    return norm(' '.join(x for x in (a['colonia'], a['municipio']) if x))


def _matches(c, f):
    if f['operation'] and c['operation'] != f['operation']:
        return False
    if f['type'] and c['property_type'] != f['type']:
        return False
    if f['beds'] and (c['bedrooms'] or 0) < f['beds']:
        return False
    if f['baths'] and (c['bathrooms'] or 0) < f['baths']:
        return False
    if f['max_price'] and (c['price'] is None or c['price'] > f['max_price']):
        return False
    place = _place(c).split()
    if any(tok not in place for tok in f['colonia_tokens']):
        return False
    if f['terms']:
        hay = norm(' '.join((c['title'], c['description'][:600], _place(c))))
        if any(not re.search(r'\b%s' % re.escape(w), hay) for w in f['terms']):
            return False
    return True


def _price_short(n):
    """'$3M', '$3.5M', '$25 mil', '$18,500'."""
    if n >= 1000000:
        return '$%sM' % ('%.2f' % (n / 1000000.0)).rstrip('0').rstrip('.')
    if n >= 1000 and n % 1000 == 0:
        return '$%d mil' % (n // 1000)
    return '$' + '{:,}'.format(n)


def summary(f, total):
    """'3 propiedades en venta · 2+ rec. · hasta $3M · Roma Sur' (only the parts that apply)."""
    one, many = TYPE_PLURAL.get(f['type'], ('propiedad', 'propiedades'))
    head = '%d %s' % (total, one if total == 1 else many)
    if f['operation']:
        head += ' en ' + f['operation']
    parts = [head]
    if f['beds']:
        parts.append('%d+ rec.' % f['beds'])
    if f['baths']:
        parts.append('%g+ baños' % f['baths'])
    if f['max_price']:
        parts.append('hasta ' + _price_short(f['max_price']))
    if f['colonia']:
        parts.append(f['colonia'])
    return ' · '.join(parts)


def _item(agency, c):
    rent = c['operation'] == 'renta'
    m2 = c['m2_land'] if c['property_type'] == 'terreno' and c['m2_land'] else c['m2_built']
    price = money(c['price'], c['currency']) + (' al mes' if rent and c['price'] is not None else '')
    return {'id': c['id'], 'n': c['title'], 'u': '%s/propiedad/%s' % (db.site_url(agency), c['slug']), 'p': price, 'rent': rent,
            'label': 'En renta' if rent else 'En venta', 'beds': c['bedrooms'], 'baths': c['bathrooms'], 'm2': m2,
            'img': c['photos'][0]['url_400'] if c['photos'] else None}


def answer(con, agency, q, phone=False):
    """The /buscar JSON. Nothing found (or nothing understood) = kind 'none' and no listings."""
    q = str(q or '').strip()[:MAX_Q]
    cards = [c for c in (db.canonical(con, i) for i in _ids(con, agency)) if c]
    places = [x for c in cards for x in (c['address']['colonia'], c['address']['municipio']) if x]
    f = parse(q, places)
    found = [c for c in cards if _matches(c, f)] if _has_filters(f) else []
    if not found:
        return {'q': q, 'kind': 'none', 'listings': [], 'total': 0, 'summary': ''}
    shown = found[:MAX_CARDS_PHONE if phone else MAX_CARDS]
    return {'q': q, 'kind': 'homes', 'listings': [_item(agency, c) for c in shown], 'total': len(found), 'summary': summary(f, len(found))}


def enabled():
    return os.environ.get('LLAVE_SITE_ASK') == '1'
