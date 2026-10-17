"""CSV importer: an agent switching from another system uploads/pastes a CSV and gets listings as drafts.

preview() never writes. commit() creates listings with status 'borrador' only (the agent reviews, then publishes).
Photos are NOT downloaded here: URLs come back in data['photo_urls'] / commit()['photo_urls'] for the route to handle.
Python stdlib only."""
import csv
import datetime
import io
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from llave import db

MAX_ROWS = 1000

CDMX_ALCALDIAS = {
    'alvaro obregon', 'azcapotzalco', 'benito juarez', 'coyoacan', 'cuajimalpa', 'cuajimalpa de morelos',
    'cuauhtemoc', 'gustavo a madero', 'iztacalco', 'iztapalapa', 'la magdalena contreras', 'magdalena contreras',
    'miguel hidalgo', 'milpa alta', 'tlahuac', 'tlalpan', 'venustiano carranza', 'xochimilco'}
CDMX_NAMES = {'cdmx', 'ciudad de mexico', 'distrito federal', 'df', 'd f', 'mexico city', 'ciudad de mexico cdmx'}

ALIASES = {
    'title': ['titulo', 'title', 'nombre', 'nombre de la propiedad', 'nombre propiedad', 'titulo del anuncio', 'titulo anuncio',
              'anuncio', 'listing title', 'property title', 'name', 'encabezado'],
    'description': ['descripcion', 'description', 'detalles', 'descripcion de la propiedad', 'descripcion larga', 'texto',
                    'comentarios', 'remarks', 'public remarks', 'listing description', 'descripcion del anuncio'],
    'price': ['precio', 'price', 'monto', 'valor', 'precio de venta', 'precio lista', 'list price', 'asking price',
              'precio total', 'importe', 'costo', 'precio mxn', 'precio usd'],
    'price_sale': ['precio venta', 'precio de venta', 'sale price', 'price sale', 'venta precio', 'precio_venta'],
    'price_rent': ['precio renta', 'precio de renta', 'rent price', 'price rent', 'rent', 'renta mensual',
                   'precio alquiler', 'monthly rent', 'precio_renta'],
    'currency': ['moneda', 'currency', 'divisa', 'tipo de moneda', 'currency code'],
    'operation': ['operacion', 'tipo de operacion', 'operation', 'operations', 'operation type', 'tipo operacion',
                  'transaccion', 'tipo de transaccion', 'transaction type', 'listing type', 'venta o renta', 'modalidad',
                  'servicio'],
    'property_type': ['tipo', 'tipo de propiedad', 'property type', 'property_type', 'tipo propiedad', 'tipo de inmueble',
                      'tipo inmueble', 'inmueble', 'categoria', 'category', 'propiedad'],
    'm2_built': ['m2', 'm2 construccion', 'm2 construidos', 'superficie construida', 'construccion', 'construction size',
                 'construction_size', 'construction area', 'built area', 'built size', 'area construida', 'sup construida',
                 'superficie', 'mts construccion', 'metros construccion', 'metros construidos', 'metros cuadrados',
                 'm2 de construccion', 'size', 'living area', 'm2 cubiertos', 'superficie cubierta', 'm2 interior'],
    'm2_land': ['m2 terreno', 'superficie terreno', 'superficie de terreno', 'lot size', 'lot_size', 'lot area', 'land area',
                'terreno', 'area terreno', 'sup terreno', 'mts terreno', 'metros terreno', 'm2 de terreno',
                'superficie total', 'm2 totales', 'm2 total', 'land size', 'superficie lote', 'm2 lote'],
    'bedrooms': ['recamaras', 'habitaciones', 'bedrooms', 'cuartos', 'dormitorios', 'recamara', 'habitacion', 'beds',
                 'bedroom', 'num recamaras', 'numero de recamaras', 'no recamaras', 'rooms', 'alcobas'],
    'bathrooms': ['banos', 'bathrooms', 'bano', 'bath', 'baths', 'num banos', 'numero de banos', 'no banos',
                  'banos completos', 'bano completo', 'full baths'],
    'half_baths': ['medios banos', 'medio bano', 'half baths', 'half bathrooms', 'half_bathrooms', 'half bath',
                   'banos medios', 'toilets'],
    'parking': ['estacionamientos', 'cajones', 'parking', 'estacionamiento', 'cajones de estacionamiento', 'parking spaces',
                'parking_spaces', 'garage', 'garages', 'lugares de estacionamiento', 'num estacionamientos',
                'cajon', 'carport', 'coches'],
    'colonia': ['colonia', 'neighborhood', 'neighbourhood', 'barrio', 'zona', 'col', 'fraccionamiento', 'sector',
                'district', 'suburb', 'asentamiento', 'colonia o zona'],
    'municipio': ['municipio', 'alcaldia', 'delegacion', 'city', 'ciudad', 'localidad', 'municipio alcaldia',
                  'alcaldia municipio', 'delegacion municipio', 'municipio o alcaldia', 'town', 'county', 'region'],
    'estado': ['estado', 'state', 'entidad', 'entidad federativa', 'province', 'provincia'],
    'cp': ['cp', 'codigo postal', 'zip', 'zip code', 'zipcode', 'postal code', 'c p', 'postal', 'codigo_postal'],
    'street': ['calle', 'street', 'direccion', 'address', 'street address', 'domicilio', 'avenida', 'calle y numero'],
    'ext_number': ['numero', 'num', 'numero exterior', 'num ext', 'no ext', 'exterior', 'street number', 'number',
                   'numero ext', 'ext number', 'num exterior', 'no exterior'],
    'amenities': ['amenidades', 'amenities', 'caracteristicas', 'features', 'servicios incluidos', 'extras',
                  'amenidades y servicios', 'equipamiento', 'facilities'],
    'maintenance': ['mantenimiento', 'maintenance', 'cuota de mantenimiento', 'cuota mantenimiento', 'maintenance fee',
                    'hoa', 'hoa fee', 'cuota', 'gastos comunes', 'mantenimiento mensual'],
    'source_url': ['url', 'link', 'enlace', 'liga', 'public url', 'public_url', 'listing url', 'pagina', 'sitio web',
                   'web', 'source url', 'url publica', 'url propiedad', 'permalink'],
    'photos': ['fotos', 'photos', 'imagenes', 'images', 'fotografias', 'photo urls', 'image urls', 'foto', 'imagen',
               'photo', 'image', 'pictures', 'picture', 'urls fotos', 'url fotos', 'url imagenes', 'galeria', 'gallery',
               'foto principal', 'main photo'],
}


def _norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', s)).strip()


_ALIAS_MAP = {}
for _f, _al in ALIASES.items():
    for _a in _al:
        _ALIAS_MAP.setdefault(_norm(_a), _f)
# price_sale / price_rent must win over the generic aliases they overlap
for _a in ALIASES['price_sale']:
    _ALIAS_MAP[_norm(_a)] = 'price_sale'
for _a in ALIASES['price_rent']:
    _ALIAS_MAP[_norm(_a)] = 'price_rent'
ALIAS_COUNT = len(_ALIAS_MAP)
_UNIT_TOKENS = {'m2', 'mxn', 'usd', 'mn', 'mts', 'mt2'}


def detect_field(header):
    n = _norm(header)
    if n in _ALIAS_MAP:
        return _ALIAS_MAP[n]
    toks = [t for t in n.split() if t not in _UNIT_TOKENS]
    n2 = ' '.join(toks)
    if n2 and n2 != n and n2 in _ALIAS_MAP:
        return _ALIAS_MAP[n2]
    return None


# ---------- value parsers ----------

def _decimal_from(numtxt, has_mult):
    """'4,500,000' / '4.500.000' / '4.5' / '4,5' / '1,234.56' / '1.234,56' -> Decimal."""
    t = numtxt.strip().strip('.,')
    if not t:
        return None
    if ',' in t and '.' in t:
        dec = ',' if t.rfind(',') > t.rfind('.') else '.'
        thou = '.' if dec == ',' else ','
        t = t.replace(thou, '').replace(dec, '.')
    elif ',' in t or '.' in t:
        sep = ',' if ',' in t else '.'
        parts = t.split(sep)
        if len(parts) > 2:
            t = ''.join(parts)  # 4,500,000
        else:
            after = parts[1]
            if len(after) == 3 and not has_mult and parts[0] not in ('0', ''):
                t = parts[0] + after  # 4,500 -> thousands
            else:
                t = parts[0] + '.' + after
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


_MULT = [(r'\b(mdp|mdd|millones|millon|mill|mm|mxn m|mdp)\b', 1000000), (r'\b(mil|k)\b', 1000)]


def parse_price(text, default_currency='MXN'):
    """-> (cents|None, currency, note|None). Understands $4,500,000 / 4.5 mdp / 4,5 millones / 28 mil / US$699,000 / 699000 USD."""
    cur = default_currency if default_currency in ('MXN', 'USD') else 'MXN'
    raw = (text or '').strip()
    if not raw:
        return None, cur, None
    low = unicodedata.normalize('NFKD', raw.lower())
    low = ''.join(c for c in low if not unicodedata.combining(c))
    if re.search(r'us\s?\$|u\$s|\busd\b|\bdls\b|\bdlls\b|dolar|dollar|\bmdd\b|\bus\b', low):
        cur = 'USD'
    elif re.search(r'\bmxn\b|\bmn\b|peso|m\.n\.|\bmdp\b', low):
        cur = 'MXN'
    mult = 1
    for pat, m in _MULT:
        if re.search(pat, low):
            mult = m
            break
    m = re.search(r'\d[\d.,]*', low)
    if not m:
        return None, cur, 'No entendimos el precio "%s".' % raw[:40]
    d = _decimal_from(m.group(0), mult != 1)
    if d is None:
        return None, cur, 'No entendimos el precio "%s".' % raw[:40]
    cents = int((d * mult * 100).to_integral_value())
    if cents <= 0:
        return None, cur, None
    return cents, cur, None


def parse_number(text):
    t = (text or '').lower()
    m = re.search(r'\d[\d.,]*', t)
    if not m:
        return None
    d = _decimal_from(m.group(0), False)
    return float(d) if d is not None else None


def parse_int(text):
    n = parse_number(text)
    if n is None or n < 0 or n > 999:
        return None
    return int(n)


def parse_baths(text):
    """'2' '2.5' '2,5' '2 1/2' '2 y medio' '2½' 'medio baño' -> float|None."""
    t = _norm_keep(text)
    if not t:
        return None
    t = t.replace('½', ' 1/2')
    t = re.sub(r'\b(y|and|con)\b', ' ', t)
    t = re.sub(r'\b(medio|media|half)\b', ' 1/2 ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    m = re.match(r'^(\d+)\s+(\d+)\s*/\s*(\d+)', t)
    if m and int(m.group(3)):
        v = int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    else:
        m = re.match(r'^(\d+)\s*/\s*(\d+)', t)
        if m and int(m.group(2)):
            v = int(m.group(1)) / int(m.group(2))
        else:
            v = parse_number(t)
    if v is None or v < 0 or v > 99:
        return None
    return round(v * 2) / 2 if abs(v * 2 - round(v * 2)) < 0.26 else v


def _norm_keep(s):
    return unicodedata.normalize('NFC', (s or '').strip().lower())


def _tokens(s):
    return _norm(s).split()


def parse_operation(text):
    toks = _tokens(text)
    for t in toks:
        if t in ('venta', 'sale', 'sell', 'vender', 'sold', 'vende', 'comprar', 'buy'):
            return 'venta'
        if t in ('renta', 'rent', 'alquiler', 'lease', 'rental', 'rentar', 'arrendamiento', 'alquilar', 'rents'):
            return 'renta'
    return None


_TYPE_TOKENS = [
    ('departamento', ('departamento', 'departamentos', 'depto', 'deptos', 'dpto', 'apartment', 'apartamento', 'condo',
                      'condominio', 'penthouse', 'ph', 'loft', 'studio', 'estudio', 'flat', 'dept')),
    ('casa', ('casa', 'casas', 'house', 'villa', 'townhouse', 'residencia', 'home', 'chalet', 'quinta', 'rancho')),
    ('terreno', ('terreno', 'terrenos', 'lote', 'lotes', 'land', 'predio', 'parcela', 'lot')),
    ('oficina', ('oficina', 'oficinas', 'office', 'consultorio', 'coworking')),
    ('local', ('local', 'locales', 'retail', 'comercial', 'commercial', 'tienda', 'restaurante', 'shop', 'store')),
    ('bodega', ('bodega', 'bodegas', 'warehouse', 'nave', 'industrial', 'naves')),
]


def parse_type(text):
    toks = _tokens(text)
    for t in toks:  # earliest matching word wins ("local comercial" -> local; "casa en condominio" -> casa)
        for ptype, words in _TYPE_TOKENS:
            if t in words:
                return ptype
    return None


def parse_currency_cell(text):
    low = _norm(text)
    if not low:
        return None
    if re.search(r'\b(usd|us|dls|dlls|dolares|dolar|dollars|dollar|u s d)\b', low):
        return 'USD'
    if re.search(r'\b(mxn|mn|peso|pesos|mx|mex)\b', low):
        return 'MXN'
    return None


def split_list(text):
    return [x.strip() for x in re.split(r'[|;,\n]+', text or '') if x.strip()]


def split_urls(text):
    return [u for u in re.split(r'[\s|,;]+', text or '') if re.match(r'^https?://', u, re.I)][:60]


def clean_estado(estado, municipio):
    e, m = _norm(estado), _norm(municipio)
    if e in CDMX_NAMES:
        return 'Ciudad de México'
    if not e and (m in CDMX_ALCALDIAS):
        return 'Ciudad de México'
    return (estado or '').strip()


# ---------- CSV reading ----------

def _to_text(csv_text):
    if isinstance(csv_text, (bytes, bytearray)):
        try:
            csv_text = bytes(csv_text).decode('utf-8-sig')
        except UnicodeDecodeError:
            csv_text = bytes(csv_text).decode('latin-1')
    t = (csv_text or '').lstrip('﻿')
    return t.replace('\r\n', '\n').replace('\r', '\n')


def sniff_delimiter(text):
    for line in text.split('\n'):
        if line.strip():
            counts = {d: line.count(d) for d in (',', ';', '\t', '|')}
            best = max(counts, key=lambda d: counts[d])
            return best if counts[best] else ','
    return ','


def read_rows(csv_text):
    """-> (headers, [(line, [cells])], truncated)."""
    text = _to_text(csv_text)
    delim = sniff_delimiter(text)
    rd = csv.reader(io.StringIO(text), delimiter=delim)
    headers, rows, prev, truncated = None, [], 0, False
    for rec in rd:
        start = prev + 1
        prev = rd.line_num
        if not any((c or '').strip() for c in rec):
            continue
        if headers is None:
            headers = [c.strip() for c in rec]
            continue
        if len(rows) >= MAX_ROWS:
            truncated = True
            break
        rows.append((start, rec))
    return headers or [], rows, truncated


# ---------- core ----------

def _plan_limit(con, agency_id):
    ag = con.execute('SELECT id, plan FROM agencies WHERE id=?', (agency_id,)).fetchone()
    limit = db.listing_limit(con, ag) if ag else db.PLAN_LIMITS['gratis']
    used = con.execute("SELECT COUNT(*) FROM listings WHERE agency_id=? AND status NOT IN ('vendida','rentada')",
                       (agency_id,)).fetchone()[0]
    return limit, used


def _analyze(con, agency_id, csv_text):
    headers, raw, truncated = read_rows(csv_text)
    cols = {}  # field -> [column index]
    detected = {}
    for i, h in enumerate(headers):
        f = detect_field(h)
        if f:
            cols.setdefault(f, []).append(i)
            detected.setdefault(f, h)

    def cell(rec, f):
        for i in cols.get(f, []):
            if i < len(rec) and (rec[i] or '').strip():
                return rec[i].strip()
        return ''

    limit, used = _plan_limit(con, agency_id)
    slots = max(limit - used, 0)
    seen = set()
    out = []
    for line, rec in raw:
        problems, reason = [], None
        d = {}
        title = re.sub(r'\s+', ' ', cell(rec, 'title'))[:100]
        d['title'] = title
        d['description'] = cell(rec, 'description')[:8000]
        # operation
        op_txt = cell(rec, 'operation')
        op = parse_operation(op_txt) if op_txt else None
        if op_txt and not op:
            problems.append('No entendimos la operación "%s"; se pone venta.' % op_txt[:30])
        # price
        cur_cell = parse_currency_cell(cell(rec, 'currency'))
        p_sale, p_rent, p_gen = cell(rec, 'price_sale'), cell(rec, 'price_rent'), cell(rec, 'price')
        if op is None:
            if p_rent and not p_sale and not p_gen:
                op = 'renta'
        price_txt = (p_rent if op == 'renta' else p_sale) or p_gen or p_sale or p_rent
        cents, cur, note = parse_price(price_txt, cur_cell or 'MXN')
        if cur_cell and cur != cur_cell and re.search(r'\d', price_txt or '') and not re.search(
                r'us|usd|dls|dolar|mxn|peso|mn|mdd', _norm(price_txt)):
            cur = cur_cell
        if note:
            problems.append(note)
        if cents is None:
            problems.append('Precio a consultar (no trae precio).')
        d['operation'] = op or 'venta'
        d['price_cents'], d['currency'] = cents, cur
        mt, _c, mnote = parse_price(cell(rec, 'maintenance'), cur)
        d['maintenance_cents'] = mt
        if mnote:
            problems.append('Mantenimiento: ' + mnote)
        # type
        t_txt = cell(rec, 'property_type')
        ptype = parse_type(t_txt) if t_txt else None
        if not ptype:
            ptype = parse_type(title) or 'departamento'
            if t_txt:
                problems.append('No entendimos el tipo "%s"; se pone %s.' % (t_txt[:30], ptype))
        d['property_type'] = ptype
        # numbers
        d['m2_built'] = parse_number(cell(rec, 'm2_built'))
        d['m2_land'] = parse_number(cell(rec, 'm2_land'))
        d['bedrooms'] = parse_int(cell(rec, 'bedrooms'))
        b_txt = cell(rec, 'bathrooms')
        baths = parse_baths(b_txt) if b_txt else None
        if b_txt and baths is None:
            problems.append('No entendimos los baños "%s".' % b_txt[:20])
        hb = parse_int(cell(rec, 'half_baths'))
        if hb:
            baths = (baths or 0) + 0.5 * hb
        d['bathrooms'] = baths
        d['parking'] = parse_int(cell(rec, 'parking'))
        # address
        col, mun = cell(rec, 'colonia'), cell(rec, 'municipio')
        est = clean_estado(cell(rec, 'estado'), mun)
        d.update(colonia=col, municipio=mun, estado=est, cp=cell(rec, 'cp')[:10], street=cell(rec, 'street'),
                 ext_number=cell(rec, 'ext_number')[:20])
        d['amenities'] = split_list(cell(rec, 'amenities'))[:40]
        d['source_url'] = cell(rec, 'source_url')
        d['photo_urls'] = split_urls(cell(rec, 'photos'))
        # required
        if len(title) < 8:
            reason = 'Falta el título (mínimo 8 letras).'
        elif not (col and mun and est):
            missing = [n for n, v in (('colonia', col), ('municipio', mun), ('estado', est)) if not v]
            reason = 'Falta ' + ', '.join(missing) + '.'
        key = (title.lower(), cents)
        if not reason:
            if key in seen:
                reason = 'Ya existe (repetido en el archivo).'
            elif con.execute('SELECT 1 FROM listings WHERE agency_id=? AND lower(title)=? AND price_cents IS ?',
                             (agency_id, title.lower(), cents)).fetchone():
                reason = 'Ya existe en tus propiedades.'
        if not reason:
            if slots <= 0:
                reason = 'Límite de tu plan'
            else:
                slots -= 1
                seen.add(key)
        if reason:
            problems.insert(0, reason)
        out.append({'line': line, 'data': d, 'problems': problems, 'action': 'omitir' if reason else 'crear',
                    'reason': reason})
    warnings = []
    if headers and 'title' not in cols:
        warnings.append('No encontramos la columna del título (prueba "titulo" o "title").')
    if truncated:
        warnings.append('Solo leímos las primeras %d filas.' % MAX_ROWS)
    if not headers:
        warnings.append('El archivo está vacío.')
    return out, detected, warnings, truncated


def preview(con, agency_id, csv_text):
    rows, detected, warnings, truncated = _analyze(con, agency_id, csv_text)
    pub = [{k: v for k, v in r.items() if k != 'reason'} for r in rows]
    return {'rows': pub, 'columns_detected': detected, 'total': len(rows), 'warnings': warnings,
            'truncated': truncated, 'ok': any(r['action'] == 'crear' for r in rows)}


def _next_ref_slug(con, agency, title):
    n = con.execute('SELECT COUNT(*) FROM listings WHERE agency_id=?', (agency['id'],)).fetchone()[0] + 1
    prefix = re.sub(r'[^A-Z]', '', agency['slug'].upper())[:4] or 'LLV'
    ref = '%s-%04d' % (prefix, n)
    while con.execute('SELECT 1 FROM listings WHERE agency_id=? AND ref=?', (agency['id'], ref)).fetchone():
        n += 1
        ref = '%s-%04d' % (prefix, n)
    slug, k = db.slugify(title), 2
    base = slug
    while con.execute('SELECT 1 FROM listings WHERE agency_id=? AND slug=?', (agency['id'], slug)).fetchone():
        slug, k = '%s-%d' % (base, k), k + 1
    return ref, slug


def commit(con, agency_id, user_id, csv_text):
    agency = con.execute('SELECT * FROM agencies WHERE id=?', (agency_id,)).fetchone()
    if not agency:
        raise ValueError('Agencia no encontrada.')
    rows, _det, _w, _t = _analyze(con, agency_id, csv_text)
    created, skipped, photos = [], [], {}
    today = datetime.date.today().isoformat()
    for r in rows:
        if r['action'] != 'crear':
            skipped.append((r['line'], r['reason']))
            continue
        d = r['data']
        ref, slug = _next_ref_slug(con, agency, d['title'])
        vals = dict(
            agency_id=agency_id, agent_id=user_id, ref=ref, slug=slug, status='borrador', operation=d['operation'],
            property_type=d['property_type'], title=d['title'], description=d['description'],
            price_cents=d['price_cents'], currency=d['currency'], price_date=today if d['price_cents'] else None,
            maintenance_cents=d['maintenance_cents'], m2_built=d['m2_built'], m2_land=d['m2_land'],
            bedrooms=d['bedrooms'], bathrooms=d['bathrooms'], parking=d['parking'],
            amenities=json.dumps(d['amenities'], ensure_ascii=False), street=d['street'], ext_number=d['ext_number'],
            colonia=d['colonia'], municipio=d['municipio'], estado=d['estado'], cp=d['cp'],
            source_url=d['source_url'] or None)
        lid = con.execute('INSERT INTO listings(%s) VALUES (%s)' % (', '.join(vals), ','.join('?' * len(vals))),
                          list(vals.values())).lastrowid
        created.append(lid)
        if d['photo_urls']:
            photos[lid] = d['photo_urls']
    db.audit(con, 'user:%s' % user_id, 'listing_import',
             'agency:%s created:%d skipped:%d' % (agency_id, len(created), len(skipped)))
    con.commit()
    return {'created': created, 'skipped': skipped, 'photo_urls': photos}
