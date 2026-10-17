"""SQLite access + the canonical listing contract every module (site, feeds, GHL) reads from."""
import json
import os
import re
import sqlite3
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get('LLAVE_DB', os.path.join(ROOT, 'data', 'llave.db'))
MEDIA_DIR = os.environ.get('LLAVE_MEDIA', os.path.join(ROOT, 'data', 'media'))
BASE_DOMAIN = os.environ.get('LLAVE_BASE_DOMAIN', 'fichaunica.localhost')  # prod: the public brand domain
PORT = int(os.environ.get('LLAVE_PORT', '8640'))

PLAN_LIMITS = {'gratis': 10, 'pro': 50, 'agencia': 200}
PUBLIC_STATUSES = ('activa', 'apartada')  # shown on sites + fed to portals

BRAND = 'Ficha Única'                 # public name (Josh 10-17); LLAVE = internal code name
OWNER = 'Ciao Bella Marketing'        # legal owner of the platform (Josh 10-17)


def connect(path=None):
    con = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    return con


def init(con):
    with open(os.path.join(ROOT, 'llave', 'schema.sql'), encoding='utf-8') as f:
        con.executescript(f.read())
    # light migrations for databases created before a column existed
    cols = {r[1] for r in con.execute('PRAGMA table_info(agencies)')}
    for col in ('first_reply', 'first_reply_noname'):
        if col not in cols:
            con.execute('ALTER TABLE agencies ADD COLUMN %s TEXT' % col)
    con.commit()


def slugify(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:80] or 'propiedad'


def site_url(agency):
    """Public base URL of an agency site (custom domain once verified, else the free address)."""
    a = dict(agency)
    if a.get('custom_domain') and a.get('domain_verified_at'):
        return 'https://' + a['custom_domain']
    port = '' if PORT in (80, 443) else ':%d' % PORT
    return 'http://%s.%s%s' % (a['slug'], BASE_DOMAIN, port)


def listing_url(agency, listing):
    return '%s/propiedad/%s' % (site_url(agency), dict(listing)['slug'])


def photo_urls(agency, photo_row, size='1600'):
    sizes = json.loads(photo_row['sizes'])
    rel = sizes.get(size) or sizes.get('1600')
    return '%s/media/%s' % (site_url(agency), rel)


def canonical(con, listing_id):
    """THE contract. A plain dict describing one listing, used by the site, every feed adapter and GHL.
    Keys (stable): id, ref, slug, url, status, operation, property_type, title, description,
    price (int pesos/dollars or None), price_cents, currency, price_date, maintenance (int or None),
    m2_built, m2_land, bedrooms, bathrooms, parking, floor, year_built, furnished, pets, amenities[list],
    address{street, ext_number, colonia, municipio, estado, cp, country:'MX', lat, lng, show_exact},
    photos[list of {url, url_800, url_400, width, height, alt}], agency{id, slug, name, whatsapp, email, site_url},
    agent{name, whatsapp, email} or None, share_in_bolsa, share_split_pct, rentapoliza_offer, updated_at.
    Never includes internal_note or commission_pct."""
    l = con.execute('SELECT * FROM listings WHERE id=?', (listing_id,)).fetchone()
    if not l:
        return None
    a = con.execute('SELECT * FROM agencies WHERE id=?', (l['agency_id'],)).fetchone()
    u = con.execute('SELECT * FROM users WHERE id=?', (l['agent_id'],)).fetchone() if l['agent_id'] else None
    ph = con.execute('SELECT * FROM photos WHERE listing_id=? ORDER BY position, id', (listing_id,)).fetchall()
    cents = l['price_cents']
    return {
        'id': l['id'], 'ref': l['ref'], 'slug': l['slug'], 'url': listing_url(a, l),
        'status': l['status'], 'operation': l['operation'], 'property_type': l['property_type'],
        'title': l['title'], 'description': l['description'] or '',
        'price': (cents // 100) if cents is not None else None, 'price_cents': cents,
        'currency': l['currency'], 'price_date': l['price_date'],
        'maintenance': (l['maintenance_cents'] // 100) if l['maintenance_cents'] is not None else None,
        'm2_built': l['m2_built'], 'm2_land': l['m2_land'], 'bedrooms': l['bedrooms'],
        'bathrooms': l['bathrooms'], 'parking': l['parking'], 'floor': l['floor'], 'year_built': l['year_built'],
        'furnished': bool(l['furnished']), 'pets': bool(l['pets']), 'amenities': json.loads(l['amenities'] or '[]'),
        'address': {'street': l['street'], 'ext_number': l['ext_number'], 'colonia': l['colonia'],
                    'municipio': l['municipio'], 'estado': l['estado'], 'cp': l['cp'], 'country': 'MX',
                    'lat': l['lat'], 'lng': l['lng'], 'show_exact': bool(l['show_exact_location'])},
        'photos': [{'url': photo_urls(a, p, '1600'), 'url_800': photo_urls(a, p, '800'),
                    'url_400': photo_urls(a, p, '400'), 'width': p['width'], 'height': p['height'],
                    'alt': p['alt'] or l['title']} for p in ph],
        'agency': {'id': a['id'], 'slug': a['slug'], 'name': a['name'], 'whatsapp': a['whatsapp'],
                   'email': a['email'], 'site_url': site_url(a)},
        'agent': ({'name': u['name'], 'whatsapp': u['whatsapp'] or a['whatsapp'], 'email': u['email']} if u else None),
        'share_in_bolsa': bool(l['share_in_bolsa']), 'share_split_pct': l['share_split_pct'],
        'rentapoliza_offer': bool(l['rentapoliza_offer']), 'updated_at': l['updated_at'],
    }


def public_listing_ids(con, agency_id, include_shared=True):
    """Listings an agency site shows: its own public ones + active Bolsa shares."""
    q = "SELECT id FROM listings WHERE agency_id=? AND status IN ('activa','apartada') ORDER BY updated_at DESC"
    ids = [r['id'] for r in con.execute(q, (agency_id,))]
    if include_shared:
        q2 = ("SELECT l.id FROM shares s JOIN listings l ON l.id=s.listing_id WHERE s.sharing_agency_id=? "
              "AND s.status='activa' AND l.share_in_bolsa=1 AND l.status IN ('activa','apartada')")
        ids += [r['id'] for r in con.execute(q2, (agency_id,)) if r['id'] not in ids]
    return ids


def audit(con, actor, action, detail=''):
    con.execute('INSERT INTO audit(actor, action, detail) VALUES (?,?,?)', (actor, action, detail))
