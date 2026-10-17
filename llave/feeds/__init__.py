"""Portal feeds: build_feed(con, agency_id, portal) -> (content_type, bytes). Reads only db.canonical()."""
import datetime

from .. import db
from . import open_xml, stubs
from .registry import JSON_ALIAS, PORTALS

__all__ = ['build_feed', 'validate', 'PORTALS']


def validate(c):
    """Portal-quality problems (Spanish). Warnings; feeds still include them unless fatal (no photos/title)."""
    p, a = [], c['address']
    n = len(c['photos'])
    if n < 5:
        p.append('Tiene %d foto%s; los portales piden al menos 5.' % (n, '' if n == 1 else 's'))
    if c['price'] is None:
        p.append('Sin precio: se publicará como "Precio a consultar" y rinde menos en portales.')
    t = len(c['title'] or '')
    if t < 20:
        p.append('El título es muy corto (%d caracteres); usa al menos 20.' % t)
    elif t > 100:
        p.append('El título es muy largo (%d caracteres); máximo 100.' % t)
    if len(c['description'] or '') < 200:
        p.append('La descripción es corta; escribe al menos 200 caracteres.')
    for k, label in (('colonia', 'la colonia'), ('municipio', 'el municipio'), ('estado', 'el estado')):
        if not a.get(k):
            p.append('Falta %s.' % label)
    if c['property_type'] != 'terreno' and not c['m2_built']:
        p.append('Faltan los m² construidos.')
    pd = c.get('price_date')
    if c['price'] is not None and pd:
        try:
            age = (datetime.date.today() - datetime.date.fromisoformat(pd[:10])).days
            if age > 30:
                p.append('Confirma el precio (fecha %s).' % pd[:10])
        except ValueError:
            p.append('Confirma el precio (fecha %s).' % pd)
    return p


def _select(con, agency_id, portal):
    if portal in ('llave_open', JSON_ALIAS):
        rows = con.execute("SELECT id FROM listings WHERE agency_id=? AND status IN %s ORDER BY updated_at DESC"
                           % (db.PUBLIC_STATUSES,), (agency_id,)).fetchall()
    else:
        rows = con.execute("SELECT l.id FROM listings l JOIN portal_publications pp ON pp.listing_id=l.id "
                           "AND pp.portal=? AND pp.enabled=1 WHERE l.agency_id=? AND l.status IN %s "
                           "ORDER BY l.updated_at DESC" % (db.PUBLIC_STATUSES,), (portal, agency_id)).fetchall()
    out = []
    for r in rows:
        c = db.canonical(con, r['id'])
        if c and c['photos'] and (c['title'] or '').strip():
            out.append(c)
    return out


def build_feed(con, agency_id, portal):
    key = 'llave_open' if portal == JSON_ALIAS else portal
    if key not in PORTALS:
        raise ValueError('Portal desconocido: %s' % portal)
    info = PORTALS[key]
    if info['status'] == 'needs_agreement':
        return stubs.stub_feed(key)
    if info['status'] == 'api':
        raise ValueError('%s usa API, no feed; ver feeds.mercadolibre' % portal)
    canons = _select(con, agency_id, portal)
    fmt = {'trovit_xml': open_xml.trovit, 'mitula_xml': open_xml.mitula, 'llave_xml': open_xml.llave_xml}[info['format']]
    if portal == JSON_ALIAS:
        fmt = open_xml.llave_json
    result = fmt(canons)
    now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    con.executemany("UPDATE portal_publications SET status='en_feed', last_sync_at=?, last_error=NULL "
                    "WHERE listing_id=? AND portal=?", [(now, c['id'], key) for c in canons])
    con.commit()
    return result
