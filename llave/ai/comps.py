"""Orientative price range from OUR OWN database only (public listings of any agency). Never scrapes portals."""
import statistics

from .. import db

TOL = 0.35
MIN_COMPS = 3
NO_DATA = 'No hay suficientes comparables públicos en Ficha Única para sugerir precio'
SOURCES = 'Fuente: propiedades públicas de Ficha Única (todas las inmobiliarias), misma operación, tipo, moneda y zona, con superficie similar.'


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def _candidates(con, me, field, value):
    ph = ','.join('?' * len(db.PUBLIC_STATUSES))
    q = ('SELECT l.*, a.name AS agency_name FROM listings l JOIN agencies a ON a.id=l.agency_id '
         'WHERE l.status IN (%s) AND l.id<>? AND l.operation=? AND l.property_type=? AND l.currency=? '
         'AND l.price_cents IS NOT NULL AND l.price_cents>0 AND l.m2_built IS NOT NULL AND l.m2_built>0 '
         'AND lower(l.%s)=lower(?) AND l.m2_built BETWEEN ? AND ?' % (ph, field))
    args = list(db.PUBLIC_STATUSES) + [me['id'], me['operation'], me['property_type'], me['currency'], value,
                                       me['m2_built'] * (1 - TOL), me['m2_built'] * (1 + TOL)]
    return con.execute(q, args).fetchall()


def suggest_price(con, listing_id):
    me = con.execute('SELECT * FROM listings WHERE id=?', (listing_id,)).fetchone()
    return _suggest(con, dict(me) if me else None)


def estimate(con, operation, property_type, currency, colonia, municipio, m2_built):
    """Owner valuation request (no listing yet): same comps rules as suggest_price."""
    return _suggest(con, {'id': -1, 'operation': operation, 'property_type': property_type, 'currency': currency or 'MXN',
                          'colonia': colonia, 'municipio': municipio, 'm2_built': m2_built})


def _suggest(con, me):
    base = {'ok': False, 'n': 0, 'price_per_m2_median': None, 'range_low': None, 'range_high': None,
            'currency': me['currency'] if me else None, 'comps': [], 'note': NO_DATA}
    if not me or not me['m2_built'] or me['m2_built'] <= 0:
        return base
    rows = []
    scope = None
    if me['colonia']:
        rows = _candidates(con, me, 'colonia', me['colonia'])
        scope = 'colonia %s' % me['colonia']
    if len(rows) < MIN_COMPS and me['municipio']:
        rows = _candidates(con, me, 'municipio', me['municipio'])
        scope = 'municipio %s' % me['municipio']
    if len(rows) < MIN_COMPS:
        base['n'] = len(rows)
        return base
    comps, ppm = [], []
    for r in rows:
        price = r['price_cents'] // 100
        pm = price / float(r['m2_built'])
        ppm.append(pm)
        comps.append({'ref': r['ref'], 'title': r['title'], 'url': None, 'price': price, 'm2': r['m2_built'],
                      'price_per_m2': round(pm), 'agency': r['agency_name'], '_a': r['agency_id'], '_s': r['slug']})
    for c in comps:
        a = con.execute('SELECT * FROM agencies WHERE id=?', (c.pop('_a'),)).fetchone()
        c['url'] = db.listing_url(a, {'slug': c.pop('_s')})
    comps.sort(key=lambda c: (abs(c['m2'] - me['m2_built']), c['ref']))
    s = sorted(ppm)
    m2 = float(me['m2_built'])
    sym = 'US$' if me['currency'] == 'USD' else '$'
    return {'ok': True, 'n': len(comps), 'price_per_m2_median': round(statistics.median(s)),
            'range_low': round(percentile(s, 0.25) * m2), 'range_high': round(percentile(s, 0.75) * m2),
            'currency': me['currency'], 'comps': comps,
            'note': 'Rango orientativo, no es un avalúo. Basado en %d propiedades públicas de la %s (%s por m² de mediana). %s'
                    % (len(comps), scope, '%s%s' % (sym, '{:,}'.format(round(statistics.median(s)))), SOURCES)}
