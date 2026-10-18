"""Weekly social kit (DRAFT ONLY: nothing is ever posted from here). Facts come from our DB; AI may only polish wording."""
import datetime
import json
import re
import statistics

from . import client, writer
from .. import db
from ..web.common import money, nice_date

# Copy of the Academia lessons (panel.LESSONS) kept here as data on purpose; update both if lessons change.
LESSONS = [
    ('Tu primera propiedad en 10 minutos', 'Del celular a tu sitio y a los portales.'),
    ('Fotos que venden con tu celular', 'Luz, ángulos y orden: lo que más cambia una ficha.'),
    ('Aparecer en Google y en ChatGPT', 'Qué lee un buscador en tu ficha y cómo ayudarle.'),
    ('Responder en 5 minutos por WhatsApp', 'El primer mensaje y cómo agendar la visita.'),
    ('Compartir en la Bolsa sin perder comisión', 'Cómo funciona la división y qué acordar por escrito.'),
    ('Rentas seguras', 'Contrato, póliza jurídica y entrega del inmueble.'),
]
MIN_MARKET = 3
POLISH_SCHEMA = {
    'type': 'object',
    'properties': {'captions': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'index': {'type': 'integer'}, 'caption': {'type': 'string'}},
        'required': ['index', 'caption'], 'additionalProperties': False}}},
    'required': ['captions'], 'additionalProperties': False,
}
POLISH_SYSTEM = (
    'Eres community manager inmobiliario en México. Reescribe cada pie de foto en español de México, de "usted", corto, '
    'humano y con una invitación clara a escribir por WhatsApp. Conserva TODAS las cifras y datos tal cual; no agregues '
    'datos, cifras, hashtags ni emojis. Devuelve el mismo número de pies con su índice.')


def _today(today):
    if today is None:
        return datetime.date.today()
    if isinstance(today, datetime.datetime):
        return today.date()
    return today


def _tag(s):
    s = re.sub(r'[^A-Za-z0-9]', '', writer_ascii(s))
    return '#' + s if s else None


def writer_ascii(s):
    import unicodedata
    return unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()


def _hashtags(*words):
    out = []
    for w in words:
        t = _tag(w)
        if t and t not in out:
            out.append(t)
    return out[:3]


def _cta(agency):
    wa = ''.join(ch for ch in (agency['whatsapp'] or '') if ch.isdigit())
    return 'Escríbanos por WhatsApp%s para agendar su visita.' % ((' al +' + wa) if wa else '')


def _views(con):
    has = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='listing_views'").fetchone()
    if not has:
        return {}
    return {r['listing_id']: r['v'] for r in con.execute('SELECT listing_id, SUM(views) AS v FROM listing_views GROUP BY listing_id')}


def _pick_listings(con, agency_id, n=3):
    ph = ','.join('?' * len(db.PUBLIC_STATUSES))
    rows = con.execute('SELECT * FROM listings WHERE agency_id=? AND status IN (%s) ORDER BY created_at DESC, id DESC' % ph,
                       [agency_id] + list(db.PUBLIC_STATUSES)).fetchall()
    chosen = []

    def add(r):
        if r is not None and r['id'] not in {c['id'] for c in chosen} and len(chosen) < n:
            chosen.append(r)
    if rows:
        add(rows[0])  # newest public
        views = _views(con)
        add(next(iter(sorted((r for r in rows if views.get(r['id'])), key=lambda r: (-views[r['id']], r['id']))), None))
        add(next(iter(sorted((r for r in rows if r['price_date']), key=lambda r: (r['price_date'], r['id']), reverse=True)), None))
        for r in rows:  # fill up
            add(r)
    return chosen


def _listing_item(agency, r):
    op = 'renta' if r['operation'] == 'renta' else 'venta'
    tname = {'departamento': 'Departamento', 'casa': 'Casa', 'terreno': 'Terreno', 'oficina': 'Oficina',
             'local': 'Local comercial', 'bodega': 'Bodega'}.get(r['property_type'], 'Propiedad')
    place = r['colonia'] or r['municipio'] or ''
    head = '%s en %s%s.' % (tname, op, (' en ' + place) if place else '')
    bits = []
    if r['m2_built']:
        bits.append('%g m²' % r['m2_built'])
    if r['bedrooms']:
        bits.append('%d %s' % (r['bedrooms'], 'recámara' if r['bedrooms'] == 1 else 'recámaras'))
    if r['bathrooms']:
        bits.append('%g %s' % (r['bathrooms'], 'baño' if r['bathrooms'] == 1 else 'baños'))
    parts = [head]
    if bits:
        parts.append(', '.join(bits) + '.')
    if r['price_cents'] is not None:
        p = '%s: %s' % ('Renta' if op == 'renta' else 'Precio', money(r['price_cents'] // 100, r['currency']))
        if r['price_date']:
            p += ' (al %s)' % nice_date(r['price_date'])
        parts.append(p + '.')
    parts.append(_cta(agency))
    parts.append('Folio %s.' % r['ref'])
    return {'kind': 'listing', 'title': r['title'], 'caption': ' '.join(parts),
            'image_url': '%s/tarjeta-post.jpg' % db.listing_url(agency, r), 'listing_ref': r['ref'],
            'hashtags': _hashtags(r['colonia'] or r['municipio'] or '', 'BienesRaicesMX', 'Renta' if op == 'renta' else 'Venta')}


def _market_item(con, agency, today):
    ph = ','.join('?' * len(db.PUBLIC_STATUSES))
    mine = [r['colonia'] for r in con.execute(
        'SELECT colonia FROM listings WHERE agency_id=? AND status IN (%s) AND colonia IS NOT NULL ORDER BY id' % ph,
        [agency['id']] + list(db.PUBLIC_STATUSES))]
    seen = []
    for col in sorted(set(mine), key=lambda c: (-mine.count(c), c)):
        rows = con.execute(
            'SELECT price_cents, m2_built FROM listings WHERE status IN (%s) AND operation=\'venta\' AND currency=\'MXN\' '
            'AND lower(colonia)=lower(?) AND price_cents>0 AND m2_built>0' % ph, list(db.PUBLIC_STATUSES) + [col]).fetchall()
        if len(rows) >= MIN_MARKET:
            avg = statistics.mean((r['price_cents'] / 100.0) / r['m2_built'] for r in rows)
            line = 'Precio medio por m² en %s: $%s (%d propiedades públicas en Ficha Única, %s)' % (
                col, '{:,}'.format(int(round(avg))), len(rows), nice_date(today.isoformat()))
            return {'kind': 'market', 'title': 'Mercado en %s' % col,
                    'caption': '%s. ¿Quiere saber cuánto vale su propiedad? %s' % (line, _cta(agency)),
                    'image_url': None, 'listing_ref': None, 'hashtags': _hashtags(col, 'BienesRaicesMX', 'MercadoInmobiliario')}
    return None


def _tip_item(agency, today):
    wk = today.isocalendar()[1]
    title, desc = LESSONS[wk % len(LESSONS)]
    return {'kind': 'tip', 'title': title, 'caption': 'Tip de la semana: %s. %s Más clases gratis en la Academia de Ficha Única. %s' % (
        title, desc, _cta(agency)),
        'image_url': None, 'listing_ref': None, 'hashtags': _hashtags('FichaUnica', 'AsesorInmobiliario', 'BienesRaicesMX')}


def _polish(items, transport):
    user = json.dumps({'pies': [{'index': i, 'caption': it['caption']} for i, it in enumerate(items)]}, ensure_ascii=False)
    try:
        out = client.complete_json(POLISH_SYSTEM, user, POLISH_SCHEMA, effort='low', transport=transport)
    except client.AIError:
        return items
    caps = {c.get('index'): c.get('caption') for c in out.get('captions', []) if isinstance(c, dict)}
    new = []
    for i, it in enumerate(items):
        cap = caps.get(i)
        ok = (isinstance(cap, str) and cap.strip() and '#' not in cap and not writer.EMOJI.search(cap)
              and not writer.BANNED.search(cap) and writer._numbers(cap) <= writer._numbers(it['caption']))
        new.append(dict(it, caption=cap.strip()) if ok else it)
    return new


def weekly_kit(con, agency_id, today=None, transport=None):
    today = _today(today)
    agency = con.execute('SELECT * FROM agencies WHERE id=?', (agency_id,)).fetchone()
    y, w, _ = today.isocalendar()
    if agency is None:
        return {'week': '%d-W%02d' % (y, w), 'items': []}
    items = [_listing_item(agency, r) for r in _pick_listings(con, agency_id)]
    m = _market_item(con, agency, today)
    if m:
        items.append(m)
    items.append(_tip_item(agency, today))
    if client.enabled():
        items = _polish(items, transport)
    return {'week': '%d-W%02d' % (y, w), 'items': items}
